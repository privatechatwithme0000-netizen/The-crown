// Live Commentary Engine.
//
// Every line is triggered by a real event and references real arena data:
// crown values, deltas, durations, viewer swings, defense counts, records.
// No "Congratulations." No "Nice." Ever.

import { AGENT_DEFS, ROLE_FOR_EVENT } from './agents.js';

const agentById = Object.fromEntries(AGENT_DEFS.map((a) => [a.id, a]));

const usd = (n) =>
  '$' + Math.round(n).toLocaleString('en-US');
const num = (n) => Math.round(n).toLocaleString('en-US');
const pct = (n) => `${n >= 0 ? '+' : ''}${Math.round(n)}%`;

function duration(hours) {
  if (hours == null) return 'an unknown stretch';
  if (hours < 1) return `${Math.max(1, Math.round(hours * 60))} minutes`;
  if (hours < 48) return `${Math.round(hours)} hours`;
  const days = hours / 24;
  return `${days.toFixed(days < 10 ? 1 : 0)} days`;
}

function maybeCatchphrase(agent, chance = 0.18) {
  if (Math.random() < chance && agent.catchphrases?.length) {
    return ' ' + agent.catchphrases[Math.floor(Math.random() * agent.catchphrases.length)];
  }
  return '';
}

// Template pools keyed by event type. Each is (ctx, agent) => string.
// ctx carries the live numbers for the event.
const TEMPLATES = {
  bid: [
    (c) => `${c.boardName} Crown just took a ${usd(c.amount)} bid from ${c.bidderName}.`,
    (c) => `New bid on ${c.boardName}: ${usd(c.amount)}. Crown value now ${usd(c.value)}.`,
    (c) =>
      c.prevValue
        ? `Crown value on ${c.boardName} climbed from ${usd(c.prevValue)} to ${usd(c.value)} on that bid.`
        : `${c.boardName} crown marked at ${usd(c.value)} after the latest bid.`,
    (c) => `${c.bidderName} is pressing ${c.boardName} — ${usd(c.amount)} on the board.`,
    (c) =>
      c.topChallengerBid
        ? `Leading challenger on ${c.boardName} now sits at ${usd(c.topChallengerBid)}.`
        : `${c.boardName} is heating up — bids stacking fast.`,
  ],
  challenge: [
    (c) => `Challenger incoming on ${c.boardName}: ${c.bidderName} stakes ${usd(c.amount)}.`,
    (c) => `${c.bidderName} is openly challenging for the ${c.boardName} Crown at ${usd(c.amount)}.`,
    (c) => `A new name enters the ${c.boardName} fight — ${c.bidderName}, ${usd(c.amount)} committed.`,
    (c) => `The ${c.boardName} holder is being tested. ${c.bidderName} just moved.`,
  ],
  transfer: [
    (c) =>
      `CROWN TRANSFER on ${c.boardName}: ${c.toName} unseats ${c.fromName} at ${usd(c.value)}.`,
    (c) =>
      `${c.fromName} held ${c.boardName} for ${duration(c.durationHours)} — ${c.toName} now wears it.`,
    (c) => `The ${c.boardName} Crown changes hands. ${c.toName} claims it at ${usd(c.value)}.`,
    (c) =>
      c.coup
        ? `A decisive coup on ${c.boardName} — ${c.toName} overthrows ${c.fromName} outright.`
        : `Timer expired on ${c.boardName}. ${c.toName} takes the throne from ${c.fromName}.`,
  ],
  defense: [
    (c) =>
      c.defenses === 1
        ? `${c.holderName} records a first successful defense of the ${c.boardName} Crown.`
        : `${c.holderName} defends ${c.boardName} again — ${c.defenses} successful defenses now.`,
    (c) => `The ${c.boardName} Crown holds. ${c.holderName} turns away the challenge at ${usd(c.value)}.`,
    (c) => `${c.holderName} refuses to yield ${c.boardName}. The reset clock starts again.`,
    (c) => `Defense confirmed on ${c.boardName}. ${c.holderName}'s reign extends another 48 hours.`,
  ],
  viewerSpike: [
    (c) => `Viewer count on ${c.boardName} just jumped ${pct(c.changePct)} to ${num(c.viewers)} watching.`,
    (c) => `${num(c.viewers)} now watching ${c.boardName} — the room is filling fast.`,
    (c) => `Audience surge on ${c.boardName}: ${pct(c.changePct)} in minutes. Energy is building.`,
    (c) => `${c.boardName} is pulling a crowd — ${num(c.viewers)} live and climbing.`,
  ],
  momentum: [
    (c) => `${c.boardName} momentum shifts to ${c.level.toUpperCase()} — score ${c.score}/100.`,
    (c) =>
      c.level === 'Explosive'
        ? `${c.boardName} just went EXPLOSIVE. Momentum ${c.score}/100 and accelerating.`
        : `Momentum on ${c.boardName} reads ${c.level} at ${c.score}/100.`,
    (c) => `The tempo on ${c.boardName} is changing — momentum now ${c.level}.`,
    (c) => `I price ${c.boardName} momentum at ${c.score}/100. ${c.level} regime.`,
  ],
  record: [
    (c) => `RECORD on ${c.boardName}: ${c.record}.`,
    (c) => `The board remembers this — ${c.record} on ${c.boardName}.`,
    (c) => `History on ${c.boardName}. ${c.record}.`,
  ],
  halloffame: [
    (c) =>
      `Hall of Fame entry on ${c.boardName}: ${c.name}, ${usd(c.value)}, held ${duration(c.durationHours)}.`,
    (c) => `${c.name} is now permanent on the ${c.boardName} Hall of Fame. The record can't be deleted.`,
    (c) => `Engraved into ${c.boardName} legacy — ${c.name}, reputation ${c.reputation}.`,
  ],
  reputation: [
    (c) => `${c.name}'s reputation on the arena moves to ${c.reputation} (${c.tier}).`,
    (c) => `Reputation shift: ${c.name} re-rated to ${c.tier} at ${c.reputation}.`,
  ],
  idle: [
    (c) =>
      c.topChallenger
        ? `${c.boardName} holder is quiet while ${c.topChallenger} sits at ${usd(c.topChallengerBid)}. Silence is a strategy.`
        : `${c.boardName} sits at ${usd(c.value)} with ${num(c.viewers)} watching. The board is waiting.`,
    (c) =>
      c.timerHours != null
        ? `${duration(c.timerHours)} left on the ${c.boardName} Crown. The window is narrowing.`
        : `The ${c.boardName} Crown is in open contention.`,
    (c) => `${num(c.viewers)} watching ${c.boardName}. Crowd activity ${c.cpm} comments per minute.`,
    (c) =>
      c.defenses > 0
        ? `${c.holderName} has defended ${c.boardName} ${c.defenses} time${c.defenses === 1 ? '' : 's'}. Pressure is mounting.`
        : `${c.holderName} holds ${c.boardName} without a defense yet. Untested.`,
    (c) => `I'd put the next ${c.boardName} transfer inside the hour at even odds.`,
  ],
};

// Pick an agent in character for the event, avoiding the one who just spoke.
function pickAgent(eventType, board, lastAgentId) {
  const roles = ROLE_FOR_EVENT[eventType] || ROLE_FOR_EVENT.idle;
  let pool = AGENT_DEFS.filter((a) => roles.includes(a.role));
  if (pool.length === 0) pool = AGENT_DEFS;

  // Weight agents who prefer this board, and avoid immediate repeats.
  const weighted = [];
  for (const a of pool) {
    if (a.id === lastAgentId && pool.length > 1) continue;
    let w = 1;
    if (a.prefersBoards?.includes(board.slug)) w += 2;
    for (let i = 0; i < w; i++) weighted.push(a);
  }
  return weighted[Math.floor(Math.random() * weighted.length)] || pool[0];
}

/**
 * Build a single commentary line for an event.
 * @returns {{agentId,agentName,avatar,accent,role,text,kind,ts}}
 */
export function generateCommentary(event, board, opts = {}) {
  const type = TEMPLATES[event.type] ? event.type : 'idle';
  const agent = event.agentId
    ? agentById[event.agentId]
    : pickAgent(type, board, opts.lastAgentId);

  const ctx = buildContext(event, board);
  const pool = TEMPLATES[type];
  const tpl = pool[Math.floor(Math.random() * pool.length)];
  let text = tpl(ctx, agent);
  text += maybeCatchphrase(agent);

  return {
    agentId: agent.id,
    agentName: agent.name,
    avatar: agent.avatar,
    accent: agent.accent,
    role: agent.role,
    text,
    kind: type,
    ts: Date.now(),
  };
}

function buildContext(event, board) {
  const holder = board.crown.holder;
  const timerHours = board.crown.timerEndsAt
    ? Math.max(0, (board.crown.timerEndsAt - Date.now()) / 3600000)
    : null;
  return {
    boardName: board.name,
    boardSlug: board.slug,
    value: board.crown.value,
    holderName: holder?.name ?? 'the holder',
    defenses: board.crown.defenses ?? 0,
    viewers: board.viewersNow,
    cpm: board.commentsPerMinute,
    timerHours,
    topChallenger: board.topChallenger?.name ?? null,
    topChallengerBid: board.topChallenger?.bid ?? null,
    // event-specific (may be undefined)
    ...event,
  };
}

export { usd, num, pct, duration };
