import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import { generateCommentary } from '../server/commentary.js';
import { AGENT_DEFS, ROLE_FOR_EVENT } from '../server/agents.js';

function makeBoard(overrides = {}) {
  return {
    slug: 'apple',
    name: 'Apple',
    crown: { holder: { name: 'Holder One' }, value: 5000, defenses: 2, timerEndsAt: Date.now() + 3600000 },
    topChallenger: null,
    viewersNow: 1200,
    commentsPerMinute: 15,
    ...overrides,
  };
}

describe('generateCommentary', () => {
  test('falls back to the idle template pool for an unknown event type', () => {
    const comment = generateCommentary({ type: 'not-a-real-event' }, makeBoard());
    assert.equal(comment.kind, 'idle');
  });

  test('returns a fully-formed commentary object with a real agent', () => {
    const comment = generateCommentary({ type: 'bid', bidderName: 'Vortex', amount: 6000, value: 6000 }, makeBoard());
    const agent = AGENT_DEFS.find((a) => a.id === comment.agentId);
    assert.ok(agent, 'agentId should match a real agent');
    assert.equal(comment.agentName, agent.name);
    assert.equal(comment.avatar, agent.avatar);
    assert.equal(comment.kind, 'bid');
    assert.ok(typeof comment.text === 'string' && comment.text.length > 0);
    assert.ok(Number.isFinite(comment.ts));
  });

  test('interpolates real event data into the rendered text', () => {
    const event = { type: 'transfer', fromName: 'Old Guard', toName: 'New Regent', value: 9999, durationHours: 40 };
    let sawFromName = false;
    for (let i = 0; i < 20; i++) {
      const comment = generateCommentary(event, makeBoard());
      assert.ok(comment.text.includes('New Regent'), 'every transfer template names the new holder');
      if (comment.text.includes('Old Guard')) sawFromName = true;
    }
    assert.ok(sawFromName, 'at least one transfer template should name the outgoing holder');
  });

  test('only picks an agent whose role is eligible for the event type', () => {
    for (let i = 0; i < 30; i++) {
      const comment = generateCommentary({ type: 'halloffame', name: 'Someone', value: 100, durationHours: 10, reputation: 80 }, makeBoard());
      assert.ok(ROLE_FOR_EVENT.halloffame.includes(comment.role));
    }
  });

  test('an explicit agentId on the event is honored', () => {
    const comment = generateCommentary({ type: 'idle', agentId: 'atlas-monroe' }, makeBoard());
    assert.equal(comment.agentId, 'atlas-monroe');
    assert.equal(comment.agentName, 'Atlas Monroe');
  });

  test('avoids immediately repeating the last agent to speak when other candidates exist', () => {
    const board = makeBoard();
    let repeats = 0;
    let lastAgentId = null;
    for (let i = 0; i < 40; i++) {
      const comment = generateCommentary({ type: 'idle' }, board, { lastAgentId });
      if (comment.agentId === lastAgentId) repeats++;
      lastAgentId = comment.agentId;
    }
    assert.equal(repeats, 0);
  });
});
