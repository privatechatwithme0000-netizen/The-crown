// The Arena Engine.
//
// A real-time simulation loop that keeps every board alive 24/7: viewers ebb and
// flow, AI challengers place bids, crowns are defended or transferred when their
// 48-hour timers expire, records fall, and agents narrate it all. User actions
// (challenge / defend) flow through the same event pipeline.

import { generateCommentary } from './commentary.js';
import { recomputeDerived, rebuildHolders, snapshot, CROWN_TTL, HOUR, initials, pick, randInt, rand, COMPETITORS } from './state.js';
import { boardLite, boardFull } from './views.js';
import { appendLedger, saveWorld } from './store.js';
import { AGENT_DEFS } from './agents.js';

const TICK_MS = 2500;
const COMMENT_WINDOW = 60000; // rolling window for comments-per-minute

let world = null;
let broadcast = () => {};
let timer = null;
let ticks = 0;

export function initEngine(w, broadcastFn) {
  world = w;
  broadcast = broadcastFn || (() => {});
}

export function startEngine() {
  if (timer) return;
  timer = setInterval(tick, TICK_MS);
  console.log('[engine] arena live — tick every %dms', TICK_MS);
}

export function stopEngine() {
  if (timer) clearInterval(timer);
  timer = null;
}

function tick() {
  ticks++;
  const boards = Object.values(world.boards);
  for (const board of boards) {
    updateViewers(board);
    rollComments(board);
    maybeAiBid(board);
    checkCrownTimer(board);
    detectMomentumShift(board);
    maybeIdleCommentary(board);
    decay(board);
  }

  if (ticks % 4 === 0) {
    recomputeDerived(world);
    pushPulse();
  }
  if (ticks % 8 === 0) {
    rebuildHolders(world);
    recomputeDerived(world);
  }
  if (ticks % 12 === 0) {
    saveWorld(snapshot(world));
  }
}

// ---- Live counters -------------------------------------------------------

function updateViewers(board) {
  const prev = board.viewersNow;
  // Random walk biased by momentum and excitement.
  const momentumBias = (board.momentum.score - 50) / 1000; // -0.05..0.05
  const drift = rand(-0.06, 0.06) + momentumBias;
  let next = Math.max(120, Math.round(prev * (1 + drift)));

  // Occasional organic surge.
  if (Math.random() < 0.04) next = Math.round(next * rand(1.08, 1.32));

  board.viewersNow = next;
  board._viewerTrend = clampTrend((next - prev) / Math.max(1, prev));
  if (next > board.peakToday) board.peakToday = next;
  if (next > board.peakEver) {
    board.peakEver = next;
    fireEvent(board, { type: 'record', record: `New all-time peak audience — ${next.toLocaleString()} watching` });
  }

  // Detect a genuine spike worth narrating.
  const changePct = ((next - prev) / Math.max(1, prev)) * 100;
  if (changePct >= 16 && next > 1500 && Math.random() < 0.6) {
    fireEvent(board, { type: 'viewerSpike', viewers: next, changePct });
  }

  // Active agents drift slowly.
  if (Math.random() < 0.2) {
    board.activeAgents = Math.max(3, board.activeAgents + randInt(-2, 3));
  }
  board._prevViewers = prev;
}

function clampTrend(t) {
  return Math.max(-1, Math.min(1, t * 4));
}

function rollComments(board) {
  const now = Date.now();
  board._commentTimes = board._commentTimes.filter((t) => now - t < COMMENT_WINDOW);
  board.commentsPerMinute = board._commentTimes.length;
}

function decay(board) {
  board._recentBidVolume = Math.max(0, (board._recentBidVolume || 0) * 0.92);
  board._recentVisits = Math.max(0, (board._recentVisits || 0) * 0.95 + rand(0, 1.2));
  if (Math.random() < 0.5) {
    board.visits += randInt(0, 6);
    if (Math.random() < 0.4) board.returnVisitors += randInt(0, 3);
  }
}

// ---- AI competition ------------------------------------------------------

function maybeAiBid(board) {
  // Boards closer to expiry and with more momentum attract more bids.
  const hoursLeft = (board.crown.timerEndsAt - Date.now()) / HOUR;
  let p = 0.05 + board.momentum.score / 1200;
  if (hoursLeft < 6) p += 0.06;
  if (board.excitement === 'EXPLOSIVE') p += 0.05;
  if (Math.random() > p) return;

  const valueBefore = board.crown.value;
  const isAgent = Math.random() < 0.45;
  const bidder = isAgent ? pick(AGENT_DEFS).name : pick(COMPETITORS);
  const factor = rand(1.02, 1.45);
  const amount = Math.round(Math.max(valueBefore * factor, valueBefore + randInt(25, 250)));

  applyBid(board, { name: bidder, type: isAgent ? 'agent' : 'human', amount }, valueBefore);

  const challenge = !board.topChallenger || amount > (board.topChallenger.bid || 0);
  fireEvent(board, {
    type: challenge ? 'challenge' : 'bid',
    bidderName: bidder,
    amount,
    value: board.crown.value,
    prevValue: valueBefore,
    topChallengerBid: board.topChallenger?.bid,
  });
}

function applyBid(board, bid, valueBefore) {
  board.bidHistory.unshift({ ...bid, ts: Date.now() });
  if (board.bidHistory.length > 60) board.bidHistory.pop();
  board.crown.value = Math.max(board.crown.value, bid.amount);
  board._recentBidVolume = (board._recentBidVolume || 0) + 1;
  world.stats.totalBids = (world.stats.totalBids || 0) + 1;

  if (bid.name !== board.crown.holder.name) {
    if (!board.topChallenger || bid.amount > board.topChallenger.bid) {
      board.topChallenger = { name: bid.name, type: bid.type, bid: bid.amount };
    }
  }

  // Bids pull a crowd.
  board.viewersNow = Math.round(board.viewersNow * rand(1.0, 1.04));
}

// ---- Crown resolution ----------------------------------------------------

function checkCrownTimer(board) {
  if (Date.now() < board.crown.timerEndsAt) return;
  resolveCrown(board);
}

function resolveCrown(board, opts = {}) {
  const holder = board.crown.holder;
  const challenger = board.topChallenger;
  const valueNow = board.crown.value;

  // Holder strength scales with reputation; challenger must clearly exceed it.
  const holderStrength = valueNow * (0.78 + (holder.reputation ?? 50) / 350);
  const challengerWins =
    opts.force === 'transfer' ||
    (challenger && (opts.force === 'coup' || challenger.bid >= holderStrength));

  if (challengerWins && challenger) {
    transferCrown(board, challenger, opts);
  } else {
    defendCrown(board);
  }
}

function transferCrown(board, challenger, opts = {}) {
  const old = board.crown.holder;
  const heldHours = (Date.now() - board.crown.wonAt) / HOUR;
  const finalValue = Math.max(board.crown.value, challenger.bid);

  // Record the outgoing reign — permanently.
  const historyEntry = {
    name: old.name, type: old.type, avatar: old.avatar,
    value: finalValue, wonAt: board.crown.wonAt, lostAt: Date.now(),
    durationHours: heldHours,
  };
  board.crownHistory.unshift(historyEntry);

  const hofEntry = {
    name: old.name, type: old.type, avatar: old.avatar,
    wonAt: board.crown.wonAt, lostAt: Date.now(),
    durationHours: heldHours, value: finalValue,
    reputation: old.reputation ?? 50,
    achievements: deriveAchievements(board, heldHours, old),
  };
  board.hallOfFame.push(hofEntry);
  appendLedger({ kind: 'transfer', board: board.slug, boardName: board.name, ...hofEntry, to: challenger.name });

  // Install the new holder.
  const newHolder = {
    name: challenger.name,
    type: challenger.type,
    avatar: challenger.type === 'agent'
      ? (AGENT_DEFS.find((a) => a.name === challenger.name)?.avatar ?? initials(challenger.name))
      : initials(challenger.name),
    accent: challenger.type === 'agent'
      ? (AGENT_DEFS.find((a) => a.name === challenger.name)?.accent ?? '#d4af37')
      : '#d4af37',
    reputation: challenger.reputation ?? randInt(45, 90),
  };
  board.crown.holder = newHolder;
  board.crown.value = finalValue;
  board.crown.wonAt = Date.now();
  board.crown.timerEndsAt = Date.now() + CROWN_TTL;
  board.crown.defenses = 0;
  board.topChallenger = null;
  world.stats.totalTransfers = (world.stats.totalTransfers || 0) + 1;

  // Transfers electrify the room.
  board.viewersNow = Math.round(board.viewersNow * rand(1.1, 1.5));
  if (board.viewersNow > board.peakToday) board.peakToday = board.viewersNow;

  fireEvent(board, {
    type: 'transfer',
    fromName: old.name, toName: newHolder.name,
    value: finalValue, durationHours: heldHours,
    coup: opts.force === 'coup',
  }, { notable: true });

  fireEvent(board, {
    type: 'halloffame',
    name: old.name, value: finalValue, durationHours: heldHours,
    reputation: old.reputation ?? 50,
  });

  // Longest-reign record check.
  const longest = Math.max(...board.crownHistory.map((h) => h.durationHours), 0);
  if (heldHours >= longest && heldHours > 24) {
    fireEvent(board, { type: 'record', record: `${old.name} set the longest reign on this board at ${Math.round(heldHours)} hours` });
  }

  rebuildHolders(world);
}

function defendCrown(board) {
  board.crown.defenses += 1;
  board.crown.wonAt = Date.now();
  board.crown.timerEndsAt = Date.now() + CROWN_TTL;
  board.crown.value = Math.round(board.crown.value * rand(1.0, 1.06));
  const survived = board.topChallenger;
  board.topChallenger = null;

  fireEvent(board, {
    type: 'defense',
    holderName: board.crown.holder.name,
    defenses: board.crown.defenses,
    value: board.crown.value,
  }, { notable: board.crown.defenses >= 3 });

  if ([1, 3, 5, 10].includes(board.crown.defenses)) {
    fireEvent(board, { type: 'record', record: `${board.crown.holder.name} reaches ${board.crown.defenses} successful defense${board.crown.defenses === 1 ? '' : 's'} on ${board.name}` });
  }
}

function deriveAchievements(board, heldHours, holder) {
  const out = [];
  if (board.crown.defenses >= 3) out.push('Iron Defense');
  if (board.crown.defenses === 0) out.push('Hostile Takeover');
  if (heldHours >= 96) out.push('Marathon Reign');
  if (board.crown.value >= 4000) out.push('Record Value');
  if ((holder.reputation ?? 0) >= 90) out.push('Untouchable');
  if (out.length === 0) out.push('Crowd Favorite');
  return out;
}

// ---- Momentum & idle narration ------------------------------------------

function detectMomentumShift(board) {
  const prevLevel = board._momentumLevel;
  const level = board.momentum.level;
  if (prevLevel && prevLevel !== level) {
    fireEvent(board, { type: 'momentum', level, score: board.momentum.score },
      { notable: level === 'Explosive' });
  }
  board._momentumLevel = level;
}

function maybeIdleCommentary(board) {
  const now = Date.now();
  const quietFor = now - (board._lastIdleAt || 0);
  // The hotter the board, the more often agents chime in.
  const interval = board.excitement === 'EXPLOSIVE' ? 9000
    : board.excitement === 'HIGH' ? 16000
    : board.excitement === 'MEDIUM' ? 28000 : 45000;
  if (quietFor < interval) return;
  if (Math.random() < 0.5) {
    fireEvent(board, { type: 'idle' });
  }
  board._lastIdleAt = now;
}

// ---- Event pipeline ------------------------------------------------------

function fireEvent(board, event, opts = {}) {
  const comment = generateCommentary(event, board, { lastAgentId: board._lastAgentId });

  // Record commentary on the board feed.
  board.comments.unshift(comment);
  if (board.comments.length > 80) board.comments.pop();
  board._commentTimes.push(Date.now());
  board._lastAgentId = comment.agentId;

  // Agent bookkeeping.
  const agent = world.agents[comment.agentId];
  if (agent) {
    agent.commentsToday = (agent.commentsToday || 0) + 1;
    agent.lastSpokeAt = Date.now();
  }

  broadcast({ kind: 'comment', boardSlug: board.slug, comment, eventType: event.type });

  // Notable events feed the global ticker / homepage activity.
  if (opts.notable || ['transfer', 'record', 'halloffame'].includes(event.type)) {
    const item = {
      type: event.type,
      boardSlug: board.slug,
      boardName: board.name,
      accent: board.accent,
      text: comment.text,
      agentName: comment.agentName,
      ts: Date.now(),
    };
    world.globalEvents.unshift(item);
    if (world.globalEvents.length > 80) world.globalEvents.pop();
    broadcast({ kind: 'activity', item });
  }

  // Always push a light board update so subscribers animate counters.
  broadcast({ kind: 'board', board: boardLite(board) });
}

function pushPulse() {
  broadcast({ kind: 'pulse', ts: Date.now() });
}

// ---- User actions --------------------------------------------------------

/**
 * A human challenges a board's crown. Returns the outcome and the live board.
 */
export function challenge(slug, { name, amount, type = 'human' }) {
  const board = world.boards[slug];
  if (!board) return { error: 'Board not found', status: 404 };
  amount = Number(amount);
  if (!name || !name.trim()) return { error: 'A challenger name is required', status: 400 };
  if (!Number.isFinite(amount) || amount <= 0) return { error: 'Bid must be a positive amount', status: 400 };

  const holder = board.crown.holder;
  if (name.trim() === holder.name) {
    return defend(slug, { name, amount });
  }

  const valueBefore = board.crown.value;
  applyBid(board, { name: name.trim(), type, amount }, valueBefore);
  board.viewersNow = Math.round(board.viewersNow * rand(1.02, 1.12));
  board._recentVisits = (board._recentVisits || 0) + 4;

  // Decisive coup: an overwhelming bid takes the crown immediately.
  const coupThreshold = valueBefore * 1.75;
  let outcome;
  if (amount >= coupThreshold) {
    board.topChallenger = { name: name.trim(), type, bid: amount, reputation: randInt(45, 80) };
    resolveCrown(board, { force: 'coup' });
    outcome = 'coup';
  } else {
    fireEvent(board, {
      type: 'challenge',
      bidderName: name.trim(),
      amount,
      value: board.crown.value,
      prevValue: valueBefore,
      topChallengerBid: board.topChallenger?.bid,
    }, { notable: amount >= valueBefore });
    outcome = board.topChallenger?.name === name.trim() ? 'leading' : 'placed';
  }

  recomputeDerived(world);
  saveWorld(snapshot(world));
  return { outcome, board: boardFull(board), coupThreshold: Math.ceil(coupThreshold) };
}

/**
 * The current holder reinforces / defends their crown, resetting the timer.
 */
export function defend(slug, { name, amount }) {
  const board = world.boards[slug];
  if (!board) return { error: 'Board not found', status: 404 };
  amount = Number(amount) || 0;
  const holder = board.crown.holder;
  if (!name || name.trim() !== holder.name) {
    return { error: 'Only the current Crown Holder can defend this board', status: 403 };
  }

  board.crown.value = Math.round(board.crown.value + Math.max(0, amount));
  board.crown.defenses += 1;
  board.crown.wonAt = Date.now();
  board.crown.timerEndsAt = Date.now() + CROWN_TTL;
  board.topChallenger = null;
  board.viewersNow = Math.round(board.viewersNow * rand(1.0, 1.06));

  fireEvent(board, {
    type: 'defense',
    holderName: holder.name,
    defenses: board.crown.defenses,
    value: board.crown.value,
  }, { notable: true });

  recomputeDerived(world);
  saveWorld(snapshot(world));
  return { outcome: 'defended', board: boardFull(board) };
}

/** Community vote — nudges a holder's reputation and reaction. */
export function cheer(slug) {
  const board = world.boards[slug];
  if (!board) return { error: 'Board not found', status: 404 };
  board.viewersNow = Math.round(board.viewersNow * rand(1.0, 1.03));
  board._recentVisits = (board._recentVisits || 0) + 2;
  board._commentTimes.push(Date.now());
  return { ok: true };
}

export { TICK_MS };
