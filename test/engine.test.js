import { test, describe, beforeEach } from 'node:test';
import assert from 'node:assert/strict';

import { createWorld } from '../server/state.js';
import { initEngine, challenge, defend } from '../server/engine.js';

const SLUG = 'apple';

let world;

beforeEach(() => {
  world = createWorld();
  initEngine(world, () => {});
});

function board() {
  return world.boards[SLUG];
}

describe('challenge', () => {
  test('rejects a non-positive bid', () => {
    const holder = board().crown.holder.name;
    const result = challenge(SLUG, { name: 'Someone Else', amount: 0 });
    assert.equal(result.status, 400);
    assert.equal(board().crown.holder.name, holder);
  });

  test('rejects a missing challenger name', () => {
    const result = challenge(SLUG, { name: '', amount: 500 });
    assert.equal(result.status, 400);
  });

  test('a modest bid below the coup threshold becomes the top challenger without transferring the crown', () => {
    const b = board();
    const holderName = b.crown.holder.name;
    const valueBefore = b.crown.value;
    const amount = Math.round(valueBefore * 1.1);

    const result = challenge(SLUG, { name: 'Challenger One', amount });

    assert.equal(result.outcome, 'leading');
    assert.equal(board().crown.holder.name, holderName);
    assert.equal(board().topChallenger.name, 'Challenger One');
    assert.equal(board().topChallenger.bid, amount);
  });

  test('an overwhelming bid past the coup threshold transfers the crown immediately', () => {
    const b = board();
    const oldHolder = b.crown.holder.name;
    const coupAmount = Math.ceil(b.crown.value * 1.75) + 50;

    const result = challenge(SLUG, { name: 'Coup Bidder', amount: coupAmount });

    assert.equal(result.outcome, 'coup');
    assert.equal(board().crown.holder.name, 'Coup Bidder');
    assert.notEqual(board().crown.holder.name, oldHolder);
    assert.equal(board().crown.defenses, 0);
    assert.equal(board().topChallenger, null);
  });

  test('a challenge from the current holder is routed to defend()', () => {
    const holderName = board().crown.holder.name;
    const defensesBefore = board().crown.defenses;

    const result = challenge(SLUG, { name: holderName, amount: 100 });

    assert.equal(result.outcome, 'defended');
    assert.equal(board().crown.defenses, defensesBefore + 1);
  });

  test('returns a 404 for an unknown board', () => {
    const result = challenge('not-a-real-board', { name: 'Whoever', amount: 100 });
    assert.equal(result.status, 404);
  });
});

describe('defend', () => {
  test('rejects anyone other than the current holder', () => {
    const result = defend(SLUG, { name: 'Not The Holder', amount: 100 });
    assert.equal(result.status, 403);
  });

  test('the current holder successfully defends, resetting the timer and clearing the challenger', () => {
    const b = board();
    const holderName = b.crown.holder.name;
    b.topChallenger = { name: 'Someone', type: 'human', bid: 100 };
    const defensesBefore = b.crown.defenses;

    const result = defend(SLUG, { name: holderName, amount: 50 });

    assert.equal(result.outcome, 'defended');
    assert.equal(board().crown.defenses, defensesBefore + 1);
    assert.equal(board().topChallenger, null);
    assert.ok(board().crown.timerEndsAt > Date.now());
  });
});
