import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

// Dynamic import (not a static one) so this runs *after* the env var is set —
// ESM hoists static imports above top-level statements, which would otherwise
// let auth.js (and db.js) initialize against the real data/crown.db first.
process.env.CROWN_DB_PATH = ':memory:';
const {
  createUser, verifyUser, createSession, resolveSession, destroySession,
} = await import('../server/auth.js');

describe('createUser', () => {
  test('rejects a username that is too short or has bad characters', () => {
    assert.throws(() => createUser('ab', 'longenoughpw'), /status.*400|Handle/);
    assert.throws(() => createUser('bad name!', 'longenoughpw'));
  });

  test('rejects a password shorter than 8 characters', () => {
    assert.throws(() => createUser('validname', 'short'));
  });

  test('rejects a duplicate username', () => {
    createUser('uniqueperson', 'longenoughpw');
    assert.throws(() => createUser('uniqueperson', 'anotherpassword'), (err) => err.status === 409);
  });

  test('creates a user with the trimmed username and an id', () => {
    const user = createUser('  spacedname  ', 'longenoughpw');
    assert.equal(user.username, 'spacedname');
    assert.ok(Number.isInteger(user.id));
  });
});

describe('verifyUser', () => {
  test('returns the user for correct credentials', () => {
    createUser('loginok', 'correctpassword');
    const user = verifyUser('loginok', 'correctpassword');
    assert.equal(user.username, 'loginok');
  });

  test('returns null for a wrong password', () => {
    createUser('wrongpw', 'correctpassword');
    assert.equal(verifyUser('wrongpw', 'incorrectpassword'), null);
  });

  test('returns null for an unknown username', () => {
    assert.equal(verifyUser('nobodyhere', 'whatever1'), null);
  });
});

describe('sessions', () => {
  test('createSession then resolveSession returns the owning user', () => {
    const user = createUser('sessionuser', 'longenoughpw');
    const token = createSession(user.id);
    const resolved = resolveSession(token);
    assert.equal(resolved.id, user.id);
    assert.equal(resolved.username, 'sessionuser');
  });

  test('resolveSession returns null for a bogus token', () => {
    assert.equal(resolveSession('not-a-real-token'), null);
  });

  test('resolveSession returns null after destroySession', () => {
    const user = createUser('logoutuser', 'longenoughpw');
    const token = createSession(user.id);
    destroySession(token);
    assert.equal(resolveSession(token), null);
  });
});
