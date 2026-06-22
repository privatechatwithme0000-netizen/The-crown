// Real accounts: signup/login with scrypt password hashing, server-side
// sessions resolved from an httpOnly cookie. No client-submitted identity
// is ever trusted for crown actions — it's always derived from the session.

import crypto from 'node:crypto';
import db from './db.js';

const SESSION_TTL_MS = 30 * 24 * 3600 * 1000; // 30 days
const USERNAME_RE = /^[a-zA-Z0-9_]{3,20}$/;
const SCRYPT_KEYLEN = 64;

function httpError(status, message) {
  const err = new Error(message);
  err.status = status;
  return err;
}

function scryptHash(password, salt) {
  return crypto.scryptSync(password, salt, SCRYPT_KEYLEN).toString('hex');
}

export function createUser(username, password) {
  username = String(username || '').trim();
  if (!USERNAME_RE.test(username)) {
    throw httpError(400, 'Handle must be 3-20 characters: letters, numbers, underscore only.');
  }
  if (!password || password.length < 8) {
    throw httpError(400, 'Password must be at least 8 characters.');
  }
  const existing = db.prepare('SELECT id FROM users WHERE username = ?').get(username);
  if (existing) throw httpError(409, 'That handle is already taken.');

  const salt = crypto.randomBytes(16).toString('hex');
  const hash = scryptHash(password, salt);
  const info = db
    .prepare('INSERT INTO users (username, password_hash, salt, created_at) VALUES (?, ?, ?, ?)')
    .run(username, hash, salt, Date.now());
  return { id: Number(info.lastInsertRowid), username };
}

export function verifyUser(username, password) {
  username = String(username || '').trim();
  const row = db
    .prepare('SELECT id, username, password_hash, salt FROM users WHERE username = ?')
    .get(username);
  if (!row) return null;
  const hash = scryptHash(password || '', row.salt);
  const a = Buffer.from(hash, 'hex');
  const b = Buffer.from(row.password_hash, 'hex');
  if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) return null;
  return { id: row.id, username: row.username };
}

export function createSession(userId) {
  const token = crypto.randomBytes(32).toString('hex');
  const now = Date.now();
  db.prepare('INSERT INTO sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)')
    .run(token, userId, now, now + SESSION_TTL_MS);
  return token;
}

export function resolveSession(token) {
  if (!token) return null;
  const row = db
    .prepare(
      `SELECT s.expires_at AS expiresAt, u.id AS userId, u.username AS username
       FROM sessions s JOIN users u ON u.id = s.user_id
       WHERE s.token = ?`,
    )
    .get(token);
  if (!row) return null;
  if (row.expiresAt < Date.now()) {
    db.prepare('DELETE FROM sessions WHERE token = ?').run(token);
    return null;
  }
  return { id: row.userId, username: row.username };
}

export function destroySession(token) {
  if (!token) return;
  db.prepare('DELETE FROM sessions WHERE token = ?').run(token);
}

// Periodically sweep expired sessions so the table doesn't grow unbounded.
setInterval(() => {
  db.prepare('DELETE FROM sessions WHERE expires_at < ?').run(Date.now());
}, 3600000).unref?.();

export { SESSION_TTL_MS };
