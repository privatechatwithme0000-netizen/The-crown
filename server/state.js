// World state: the live model of every Board, Agent, and Crown Holder.
//
// createWorld() seeds a believable, already-alive arena. hydrateWorld() restores
// a persisted snapshot. recomputeDerived() refreshes attention/momentum/rankings.

import { BOARD_DEFS } from './boards.js';
import { AGENT_DEFS } from './agents.js';
import {
  attentionScore,
  reputationRating,
  momentumScore,
  excitementLevel,
} from './scoring.js';

const HOUR = 3600000;
const CROWN_TTL = 48 * HOUR;

const rand = (min, max) => min + Math.random() * (max - min);
const randInt = (min, max) => Math.floor(rand(min, max + 1));
const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];

// A pool of competitor handles — the humans of the arena.
const COMPETITORS = [
  'Nova Group', 'KingMidas', 'ApexZero', 'Solenne', 'Vortex', 'Halcyon',
  'NeoRegent', 'Mercer', 'Lux Aeterna', 'Draven', 'Sable', 'Ronin',
  'Cardinal', 'Onyx Syndicate', 'Vanta', 'Seraph', 'Maelstrom', 'Quorra',
  'Augustus', 'Cassia', 'Zephyr', 'Helios Capital', 'Indigo', 'Wraith',
  'Marquis', 'Castellan', 'Phoenix Reign', 'Solaris', 'Aurum', 'Tempest',
];

const ACHIEVEMENTS = [
  'First Blood', 'Iron Defense', 'Comeback Crown', 'Crowd Favorite',
  'Record Value', 'Marathon Reign', 'Flawless Defense', 'Hostile Takeover',
  'People\'s Champion', 'Untouchable', 'Last Stand', 'Dynasty',
];

function makeHolderRef(name, isAgent) {
  const agent = isAgent ? AGENT_DEFS.find((a) => a.name === name) : null;
  return {
    name,
    type: isAgent ? 'agent' : 'human',
    avatar: agent ? agent.avatar : initials(name),
    accent: agent ? agent.accent : pick(['#d4af37', '#3da9fc', '#23e0a8', '#ff5c8a', '#b58cff']),
    reputation: randInt(38, 96),
  };
}

function initials(name) {
  const parts = name.replace(/[^a-zA-Z ]/g, '').trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function seedHallOfFame(boardName) {
  const count = randInt(2, 4);
  const entries = [];
  let cursor = Date.now() - randInt(40, 120) * 24 * HOUR;
  for (let i = 0; i < count; i++) {
    const isAgent = Math.random() < 0.4;
    const name = isAgent ? pick(AGENT_DEFS).name : pick(COMPETITORS);
    const heldHours = randInt(12, 120);
    const wonAt = cursor;
    const lostAt = cursor + heldHours * HOUR;
    cursor = lostAt + randInt(2, 24) * HOUR;
    entries.push({
      name,
      type: isAgent ? 'agent' : 'human',
      avatar: isAgent ? AGENT_DEFS.find((a) => a.name === name).avatar : initials(name),
      wonAt,
      lostAt,
      durationHours: heldHours,
      value: randInt(300, 5200),
      reputation: randInt(40, 98),
      achievements: pickMany(ACHIEVEMENTS, randInt(1, 3)),
    });
  }
  return entries;
}

function pickMany(arr, n) {
  const copy = [...arr];
  const out = [];
  for (let i = 0; i < n && copy.length; i++) {
    out.push(copy.splice(Math.floor(Math.random() * copy.length), 1)[0]);
  }
  return out;
}

function seedBoard(def) {
  const isAgentHolder = Math.random() < 0.35;
  const holderName = isAgentHolder ? pick(AGENT_DEFS).name : pick(COMPETITORS);
  const holder = makeHolderRef(holderName, isAgentHolder);
  const value = randInt(220, 4200);

  // Vary timers so some boards are in the final hours (live crown battles).
  const remaining = Math.random() < 0.3 ? rand(0.2, 4) * HOUR : rand(6, 47) * HOUR;
  const wonAt = Date.now() - (CROWN_TTL - remaining);

  const viewers = randInt(800, 16000);
  const peakEver = viewers + randInt(2000, 30000);

  const board = {
    slug: def.slug,
    name: def.name,
    category: def.category,
    entity: def.entity,
    accent: def.accent,
    glow: def.glow,
    tagline: def.tagline,

    crown: {
      holder,
      value,
      wonAt,
      timerEndsAt: wonAt + CROWN_TTL,
      defenses: randInt(0, 5),
    },
    topChallenger: Math.random() < 0.6
      ? { name: pick(COMPETITORS), type: 'human', bid: Math.round(value * rand(0.5, 0.95)) }
      : null,

    viewersNow: viewers,
    peakToday: viewers + randInt(0, 4000),
    peakEver,
    peakTodayDate: todayKey(),

    activeAgents: randInt(8, 52),
    commentsPerMinute: randInt(4, 30),
    _commentTimes: [],

    excitement: 'MEDIUM',
    momentum: { score: 50, level: 'Medium' },
    attention: 500,

    bidHistory: seedBids(value),
    crownHistory: seedCrownHistory(),
    hallOfFame: seedHallOfFame(def.name),
    comments: [],

    visits: randInt(4000, 90000),
    returnVisitors: randInt(1500, 40000),
    _recentVisits: randInt(2, 25),
    _recentBidVolume: randInt(0, 4),
    _viewerTrend: rand(-0.3, 0.6),
    _prevViewers: viewers,

    reputationRank: 0,
    activityRank: 0,
    leaderboardPosition: 0,
    _lastAgentId: null,
    _lastIdleAt: Date.now(),
  };
  return board;
}

function seedBids(value) {
  const bids = [];
  let v = value;
  const n = randInt(3, 8);
  for (let i = 0; i < n; i++) {
    bids.unshift({
      name: pick(COMPETITORS),
      type: Math.random() < 0.4 ? 'agent' : 'human',
      amount: Math.round(v),
      ts: Date.now() - i * randInt(2, 40) * 60000,
    });
    v = v * rand(0.7, 0.95);
  }
  return bids;
}

function seedCrownHistory() {
  const n = randInt(2, 5);
  const out = [];
  let cursor = Date.now() - randInt(20, 80) * 24 * HOUR;
  for (let i = 0; i < n; i++) {
    const isAgent = Math.random() < 0.4;
    const name = isAgent ? pick(AGENT_DEFS).name : pick(COMPETITORS);
    const held = randInt(8, 96);
    out.push({
      name,
      type: isAgent ? 'agent' : 'human',
      value: randInt(250, 4800),
      wonAt: cursor,
      lostAt: cursor + held * HOUR,
      durationHours: held,
    });
    cursor += (held + randInt(1, 12)) * HOUR;
  }
  return out.reverse();
}

function todayKey() {
  return new Date().toISOString().slice(0, 10);
}

function seedAgents() {
  const agents = {};
  for (const def of AGENT_DEFS) {
    agents[def.id] = {
      ...def,
      reputation: randInt(55, 97),
      accuracy: rand(0.55, 0.95),
      commentsToday: randInt(40, 320),
      callsCorrect: randInt(20, 180),
      callsMade: randInt(30, 220),
      followers: randInt(2000, 90000),
      memory: [],
      lastSpokeAt: 0,
    };
  }
  return agents;
}

export function createWorld() {
  const boards = {};
  for (const def of BOARD_DEFS) boards[def.slug] = seedBoard(def);
  const world = {
    startedAt: Date.now(),
    boards,
    agents: seedAgents(),
    holders: {},
    globalEvents: [],
    stats: { totalTransfers: 0, totalBids: 0, peakConcurrent: 0 },
  };
  rebuildHolders(world);
  recomputeDerived(world);
  return world;
}

// Aggregate holder/competitor records from boards + hall of fame for leaderboards.
export function rebuildHolders(world) {
  const holders = {};
  const touch = (name, type, avatar, accent) => {
    if (!holders[name]) {
      holders[name] = {
        name, type, avatar, accent,
        crownsWon: 0, defenses: 0, activity: 0, votes: randInt(20, 400),
        accuracy: 0, hallOfFameEntries: 0, totalValue: 0,
        boardsHeld: [], reputation: 50,
      };
    }
    return holders[name];
  };
  for (const board of Object.values(world.boards)) {
    const h = board.crown.holder;
    const rec = touch(h.name, h.type, h.avatar, h.accent);
    rec.crownsWon += 1;
    rec.defenses += board.crown.defenses ?? 0;
    rec.totalValue += board.crown.value;
    rec.activity += board.commentsPerMinute;
    if (!rec.boardsHeld.includes(board.name)) rec.boardsHeld.push(board.name);

    for (const e of board.hallOfFame) {
      const r = touch(e.name, e.type, e.avatar, '#d4af37');
      r.hallOfFameEntries += 1;
      r.totalValue += e.value;
      r.defenses += 0;
    }
    for (const e of board.crownHistory) {
      const r = touch(e.name, e.type, e.avatar ?? initials(e.name), '#d4af37');
      r.crownsWon += 0.0; // historical, lightly weighted via totalValue
      r.totalValue += e.value * 0.25;
    }
  }
  for (const rec of Object.values(holders)) {
    rec.reputation = reputationRating(rec).score;
  }
  world.holders = holders;
}

export function recomputeDerived(world) {
  const boards = Object.values(world.boards);
  for (const b of boards) {
    b.momentum = momentumScore(b);
    b.attention = attentionScore(b);
    b.excitement = excitementLevel(b);
  }
  // Rankings.
  rankBy(boards, (b) => b.attention, 'leaderboardPosition');
  rankBy(boards, (b) => b.crown.holder?.reputation ?? 0, 'reputationRank');
  rankBy(boards, (b) => b.commentsPerMinute + b.activeAgents, 'activityRank');

  const totalViewers = boards.reduce((s, b) => s + b.viewersNow, 0);
  if (totalViewers > (world.stats.peakConcurrent || 0)) {
    world.stats.peakConcurrent = totalViewers;
  }
  world.stats.totalViewers = totalViewers;
}

function rankBy(arr, fn, field) {
  const sorted = [...arr].sort((a, b) => fn(b) - fn(a));
  sorted.forEach((b, i) => { b[field] = i + 1; });
}

// ---- Serialization -------------------------------------------------------

export function snapshot(world) {
  // Plain JSON already (no Sets/Maps), but trim transient/large fields for size.
  const boards = {};
  for (const [slug, b] of Object.entries(world.boards)) {
    boards[slug] = {
      ...b,
      comments: b.comments.slice(0, 40),
      bidHistory: b.bidHistory.slice(0, 40),
      _commentTimes: [],
    };
  }
  return {
    startedAt: world.startedAt,
    boards,
    agents: world.agents,
    holders: world.holders,
    globalEvents: world.globalEvents.slice(0, 60),
    stats: world.stats,
    savedAt: Date.now(),
  };
}

export function hydrateWorld(snap) {
  // Backfill any new fields that might be missing from older snapshots.
  for (const b of Object.values(snap.boards)) {
    b._commentTimes = b._commentTimes || [];
    b.comments = b.comments || [];
    b.bidHistory = b.bidHistory || [];
    b.hallOfFame = b.hallOfFame || [];
    b.crownHistory = b.crownHistory || [];
    b._lastIdleAt = b._lastIdleAt || Date.now();
  }
  snap.globalEvents = snap.globalEvents || [];
  snap.holders = snap.holders || {};
  snap.stats = snap.stats || { totalTransfers: 0, totalBids: 0, peakConcurrent: 0 };
  recomputeDerived(snap);
  return snap;
}

export { CROWN_TTL, HOUR, initials, pick, randInt, rand, COMPETITORS };
