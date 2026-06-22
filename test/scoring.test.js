import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import {
  attentionScore, reputationRating, reputationTier,
  momentumScore, momentumLevel, excitementLevel, saturate,
} from '../server/scoring.js';

function makeBoard(overrides = {}) {
  return {
    crown: { value: 1000, holder: { reputation: 50 }, defenses: 0 },
    topChallenger: null,
    commentsPerMinute: 10,
    bidHistory: [],
    viewersNow: 1000,
    peakEver: 5000,
    activeAgents: 10,
    _viewerTrend: 0,
    _recentBidVolume: 0,
    _recentVisits: 0,
    visits: 100,
    returnVisitors: 20,
    momentum: { score: 50 },
    ...overrides,
  };
}

describe('saturate', () => {
  test('is 0 at 0 and approaches 1 as value grows', () => {
    assert.equal(saturate(0, 100), 0);
    assert.ok(saturate(1e9, 100) > 0.999);
  });

  test('equals 0.5 exactly at the midpoint', () => {
    assert.equal(saturate(100, 100), 0.5);
  });
});

describe('attentionScore', () => {
  test('stays within the documented 0..1000 range', () => {
    const score = attentionScore(makeBoard());
    assert.ok(score >= 0 && score <= 1000);
  });

  test('rises when crown value and viewers increase', () => {
    const low = attentionScore(makeBoard({ crown: { value: 100, holder: { reputation: 50 }, defenses: 0 } }));
    const high = attentionScore(makeBoard({ crown: { value: 50000, holder: { reputation: 50 }, defenses: 0 }, viewersNow: 50000 }));
    assert.ok(high > low);
  });

  test('a live top challenger pushes the score up over no challenger', () => {
    const none = attentionScore(makeBoard());
    const withChallenger = attentionScore(makeBoard({ topChallenger: { bid: 5000 } }));
    assert.ok(withChallenger > none);
  });
});

describe('reputationRating', () => {
  test('returns a score clamped to 1..100 and a matching tier', () => {
    const { score, tier } = reputationRating({});
    assert.ok(score >= 1 && score <= 100);
    assert.equal(tier, reputationTier(score));
  });

  test('more defenses, wins, and Hall of Fame entries raise reputation', () => {
    const newcomer = reputationRating({});
    const veteran = reputationRating({ defenses: 20, crownsWon: 10, hallOfFameEntries: 5, activity: 100, votes: 300 });
    assert.ok(veteran.score > newcomer.score);
  });

  test('tier boundaries match the documented thresholds', () => {
    assert.equal(reputationTier(99), 'Sovereign');
    assert.equal(reputationTier(85), 'Legendary');
    assert.equal(reputationTier(70), 'Elite');
    assert.equal(reputationTier(55), 'Established');
    assert.equal(reputationTier(40), 'Rising');
    assert.equal(reputationTier(10), 'Newcomer');
  });
});

describe('momentumScore', () => {
  test('returns a score clamped to 0..100 and a matching level', () => {
    const { score, level } = momentumScore(makeBoard());
    assert.ok(score >= 0 && score <= 100);
    assert.equal(level, momentumLevel(score));
  });

  test('a hot board (rising viewers, fresh bids, high activity) outscores a cold one', () => {
    const cold = momentumScore(makeBoard({ _viewerTrend: -1, _recentBidVolume: 0, commentsPerMinute: 0, activeAgents: 0 }));
    const hot = momentumScore(makeBoard({ _viewerTrend: 1, _recentBidVolume: 10, commentsPerMinute: 50, activeAgents: 80 }));
    assert.ok(hot.score > cold.score);
  });

  test('level boundaries match the documented thresholds', () => {
    assert.equal(momentumLevel(85), 'Explosive');
    assert.equal(momentumLevel(60), 'High');
    assert.equal(momentumLevel(40), 'Medium');
    assert.equal(momentumLevel(10), 'Low');
  });
});

describe('excitementLevel', () => {
  test('a quiet board reads LOW', () => {
    const board = makeBoard({ commentsPerMinute: 0, momentum: { score: 0 }, _viewerTrend: 0 });
    assert.equal(excitementLevel(board), 'LOW');
  });

  test('a loud, surging board reads EXPLOSIVE', () => {
    const board = makeBoard({ commentsPerMinute: 60, momentum: { score: 100 }, _viewerTrend: 1 });
    assert.equal(excitementLevel(board), 'EXPLOSIVE');
  });
});
