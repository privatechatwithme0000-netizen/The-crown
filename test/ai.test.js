import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

// Dynamic import after clearing the key — aiEnabled is computed at module
// load time, and ESM hoists static imports above top-level statements.
delete process.env.ANTHROPIC_API_KEY;
const { aiEnabled, maybeEnhance, buildPrompt, MARQUEE_EVENTS } = await import('../server/ai.js');

const agent = {
  id: 'atlas-monroe',
  name: 'Atlas Monroe',
  role: 'Historian',
  tone: 'Legacy-focused, measured',
  personality: 'Keeps the long memory. Every crown is a chapter to him.',
};
const board = { name: 'Apple', slug: 'apple' };

describe('ai (no ANTHROPIC_API_KEY set)', () => {
  test('aiEnabled is false when the key is absent', () => {
    assert.equal(aiEnabled, false);
  });

  test('maybeEnhance resolves to null without making a network call', async () => {
    const event = { type: 'transfer', fromName: 'Old Guard', toName: 'New Regent', value: 4200, durationHours: 30 };
    const result = await maybeEnhance(event, board, agent);
    assert.equal(result, null);
  });

  test('maybeEnhance resolves to null for non-marquee event types too', async () => {
    const result = await maybeEnhance({ type: 'bid', amount: 100 }, board, agent);
    assert.equal(result, null);
  });
});

describe('MARQUEE_EVENTS', () => {
  test('only the big, legacy-defining moments qualify for AI enhancement', () => {
    assert.ok(MARQUEE_EVENTS.has('transfer'));
    assert.ok(MARQUEE_EVENTS.has('halloffame'));
    assert.ok(MARQUEE_EVENTS.has('record'));
    assert.ok(!MARQUEE_EVENTS.has('bid'));
    assert.ok(!MARQUEE_EVENTS.has('idle'));
  });
});

describe('buildPrompt', () => {
  test('the system prompt carries the agent persona and house style rules', () => {
    const { system } = buildPrompt({ type: 'transfer', fromName: 'A', toName: 'B', value: 100, durationHours: 5 }, board, agent);
    assert.ok(system.includes('Atlas Monroe'));
    assert.ok(system.includes('Historian'));
    assert.ok(system.includes(agent.tone));
    assert.ok(/Congratulations/.test(system), 'should explicitly ban generic praise');
  });

  test('the user prompt cites the real event numbers, not placeholders', () => {
    const event = { type: 'transfer', fromName: 'Old Guard', toName: 'New Regent', value: 4200, durationHours: 30, coup: true };
    const { user } = buildPrompt(event, board, agent);
    assert.ok(user.includes('Old Guard'));
    assert.ok(user.includes('New Regent'));
    assert.ok(user.includes('4,200'));
    assert.ok(user.includes('coup'));
  });

  test('a halloffame event cites name, duration, value, and reputation', () => {
    const event = { type: 'halloffame', name: 'Vortex', value: 999, durationHours: 12, reputation: 88 };
    const { user } = buildPrompt(event, board, agent);
    assert.ok(user.includes('Vortex'));
    assert.ok(user.includes('999'));
    assert.ok(user.includes('88'));
  });

  test('a record event cites the literal record string', () => {
    const event = { type: 'record', record: 'New all-time peak audience — 12,000 watching' };
    const { user } = buildPrompt(event, board, agent);
    assert.ok(user.includes('12,000 watching'));
  });
});
