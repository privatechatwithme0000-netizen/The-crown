// Scoring formulas for the arena. All pure functions so they can be reasoned
// about and tested in isolation.

const clamp = (n, lo, hi) => Math.max(lo, Math.min(hi, n));

// Smoothly maps a raw value onto 0..1 with a soft knee at `mid`.
function saturate(value, mid) {
  if (value <= 0) return 0;
  return value / (value + mid);
}

/**
 * ATTENTION SCORE — the headline public number for a board (0..1000).
 * Blends: Bid Strength · Reputation · Activity · Viewer Engagement · Board Influence.
 */
export function attentionScore(board) {
  const bidStrength = saturate(board.crown.value, 2500); // crown value vs. soft knee
  const challengerPush = board.topChallenger ? saturate(board.topChallenger.bid, 2000) : 0;
  const reputation = clamp((board.crown.holder?.reputation ?? 50) / 100, 0, 1);
  const activity = saturate(board.commentsPerMinute + board.bidHistory.length * 0.4, 30);
  const viewerEngagement = saturate(board.viewersNow, 12000);
  const influence = saturate(board.peakEver, 40000);

  const score =
    bidStrength * 320 +
    challengerPush * 120 +
    reputation * 150 +
    activity * 150 +
    viewerEngagement * 160 +
    influence * 100;

  return Math.round(clamp(score, 0, 1000));
}

/**
 * REPUTATION RATING for a holder/competitor (0..100 plus a tier label).
 * Tracks: Successful Defenses · Crown Wins · Activity · Community Votes ·
 * Agent Accuracy · Hall of Fame Status.
 */
export function reputationRating(holder) {
  const defenses = holder.defenses ?? 0;
  const wins = holder.crownsWon ?? 0;
  const activity = holder.activity ?? 0;
  const votes = holder.votes ?? 0;
  const accuracy = holder.accuracy ?? 0; // 0..1, mainly for agents
  const hof = holder.hallOfFameEntries ?? 0;

  const raw =
    defenses * 7 +
    wins * 9 +
    saturate(activity, 40) * 18 +
    saturate(votes, 200) * 14 +
    accuracy * 16 +
    hof * 6 +
    20; // baseline so newcomers aren't at zero

  const score = Math.round(clamp(raw, 1, 100));
  return { score, tier: reputationTier(score) };
}

export function reputationTier(score) {
  if (score >= 92) return 'Sovereign';
  if (score >= 80) return 'Legendary';
  if (score >= 66) return 'Elite';
  if (score >= 50) return 'Established';
  if (score >= 32) return 'Rising';
  return 'Newcomer';
}

/**
 * BOARD MOMENTUM (0..100 + level). Built from short-window growth signals:
 * Viewer Growth · Bid Growth · Agent Activity · Comment Activity ·
 * Board Visits · Return Visitors.
 */
export function momentumScore(board) {
  const viewerGrowth = clamp(board._viewerTrend ?? 0, -1, 1); // -1..1
  const bidGrowth = saturate(board._recentBidVolume ?? 0, 4); // 0..1
  const agentActivity = saturate(board.activeAgents, 60);
  const commentActivity = saturate(board.commentsPerMinute, 35);
  const visitFlow = saturate(board._recentVisits ?? 0, 25);
  const loyalty = board.visits > 0 ? clamp((board.returnVisitors ?? 0) / board.visits, 0, 1) : 0;

  const raw =
    (viewerGrowth * 0.5 + 0.5) * 26 +
    bidGrowth * 24 +
    agentActivity * 14 +
    commentActivity * 16 +
    visitFlow * 12 +
    loyalty * 8;

  const score = Math.round(clamp(raw, 0, 100));
  return { score, level: momentumLevel(score) };
}

export function momentumLevel(score) {
  if (score >= 80) return 'Explosive';
  if (score >= 58) return 'High';
  if (score >= 34) return 'Medium';
  return 'Low';
}

/**
 * CROWD EXCITEMENT — derived from live tempo and momentum.
 */
export function excitementLevel(board) {
  const cpm = board.commentsPerMinute;
  const mo = board.momentum?.score ?? 0;
  const trend = board._viewerTrend ?? 0;
  const heat = cpm * 1.8 + mo * 0.6 + Math.max(0, trend) * 30;
  if (heat >= 95) return 'EXPLOSIVE';
  if (heat >= 60) return 'HIGH';
  if (heat >= 30) return 'MEDIUM';
  return 'LOW';
}

export { clamp, saturate };
