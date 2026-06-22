// View serializers — shape internal state into the payloads the client consumes.
// Keeps internal-only fields (prefixed with _) out of the wire format.

import { reputationRating } from './scoring.js';

export function boardLite(b) {
  return {
    slug: b.slug,
    name: b.name,
    accent: b.accent,
    glow: b.glow,
    value: b.crown.value,
    holder: b.crown.holder,
    defenses: b.crown.defenses,
    timerEndsAt: b.crown.timerEndsAt,
    topChallenger: b.topChallenger,
    viewersNow: b.viewersNow,
    peakToday: b.peakToday,
    peakEver: b.peakEver,
    activeAgents: b.activeAgents,
    commentsPerMinute: b.commentsPerMinute,
    excitement: b.excitement,
    momentum: b.momentum,
    attention: b.attention,
    leaderboardPosition: b.leaderboardPosition,
  };
}

export function boardCard(b) {
  return {
    ...boardLite(b),
    category: b.category,
    entity: b.entity,
    tagline: b.tagline,
  };
}

export function boardFull(b) {
  return {
    ...boardCard(b),
    reputationRank: b.reputationRank,
    activityRank: b.activityRank,
    visits: b.visits,
    returnVisitors: b.returnVisitors,
    crown: b.crown,
    bidHistory: b.bidHistory.slice(0, 30),
    crownHistory: b.crownHistory.slice(0, 30),
    hallOfFame: [...b.hallOfFame].sort((x, y) => y.wonAt - x.wonAt),
    comments: b.comments.slice(0, 50),
  };
}

export function agentView(a) {
  const accuracyPct = a.callsMade ? Math.round((a.callsCorrect / a.callsMade) * 100) : 0;
  return {
    id: a.id,
    name: a.name,
    role: a.role,
    avatar: a.avatar,
    accent: a.accent,
    tone: a.tone,
    personality: a.personality,
    catchphrases: a.catchphrases,
    prefersBoards: a.prefersBoards,
    rivals: a.rivals,
    reputation: a.reputation,
    accuracyPct,
    commentsToday: a.commentsToday,
    followers: a.followers,
  };
}

export function holderView(h) {
  const rep = reputationRating(h);
  return {
    name: h.name,
    type: h.type,
    avatar: h.avatar,
    accent: h.accent,
    crownsWon: Math.round(h.crownsWon),
    defenses: h.defenses,
    boardsHeld: h.boardsHeld,
    totalValue: Math.round(h.totalValue),
    hallOfFameEntries: h.hallOfFameEntries,
    reputation: rep.score,
    tier: rep.tier,
  };
}

export function homeSummary(world) {
  const boards = Object.values(world.boards);
  const cards = boards.map(boardCard);

  const trending = [...cards].sort((a, b) => b.attention - a.attention).slice(0, 8);
  const battles = [...cards]
    .filter((b) => b.timerEndsAt - Date.now() < 6 * 3600000 || b.excitement === 'EXPLOSIVE')
    .sort((a, b) => a.timerEndsAt - b.timerEndsAt)
    .slice(0, 6);
  const mostWatched = [...cards].sort((a, b) => b.viewersNow - a.viewersNow).slice(0, 6);
  const highestMomentum = [...cards].sort((a, b) => b.momentum.score - a.momentum.score).slice(0, 6);

  const recentTransfers = [...world.globalEvents]
    .filter((e) => e.type === 'transfer')
    .slice(0, 8);

  const topHolders = Object.values(world.holders)
    .map(holderView)
    .sort((a, b) => b.reputation - a.reputation || b.totalValue - a.totalValue)
    .slice(0, 8);

  const topAgents = Object.values(world.agents)
    .map(agentView)
    .sort((a, b) => b.reputation - a.reputation)
    .slice(0, 7);

  const totalViewers = boards.reduce((s, b) => s + b.viewersNow, 0);
  const totalAgents = boards.reduce((s, b) => s + b.activeAgents, 0);
  const totalCrownValue = boards.reduce((s, b) => s + b.crown.value, 0);

  return {
    trending,
    battles,
    mostWatched,
    highestMomentum,
    recentTransfers,
    topHolders,
    topAgents,
    arenaHighlights: world.globalEvents.slice(0, 12),
    ticker: world.globalEvents.slice(0, 18),
    stats: {
      totalViewers,
      totalAgents,
      totalCrownValue,
      boards: boards.length,
      peakConcurrent: world.stats.peakConcurrent || totalViewers,
      totalTransfers: world.stats.totalTransfers || 0,
      uptimeSince: world.startedAt,
    },
  };
}
