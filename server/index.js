// The Crown — HTTP server.
//
// Serves the static arena UI, a small REST API, and a Server-Sent Events stream
// that pushes live commentary, counters, crown transfers, and ticker activity.
// Zero runtime dependencies — Node built-ins only.

import http from 'node:http';
import { promises as fs } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { createWorld, hydrateWorld } from './state.js';
import { loadWorld, saveWorldNow, readLedger } from './store.js';
import { snapshot } from './state.js';
import {
  initEngine, startEngine, challenge, defend, cheer,
} from './engine.js';
import {
  homeSummary, boardCard, boardFull, agentView, holderView,
} from './views.js';
import {
  createUser, verifyUser, createSession, resolveSession, destroySession, SESSION_TTL_MS,
} from './auth.js';
import { rateLimit } from './ratelimit.js';
import db from './db.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PUBLIC_DIR = path.join(__dirname, '..', 'public');
const PORT = process.env.PORT || 3000;
const HOST = process.env.HOST || '0.0.0.0';

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
};

// ---- World bootstrap -----------------------------------------------------

let world;
const persisted = await loadWorld();
if (persisted && persisted.boards) {
  world = hydrateWorld(persisted);
  console.log('[crown] restored arena from disk (%d boards)', Object.keys(world.boards).length);
} else {
  world = createWorld();
  console.log('[crown] seeded a fresh arena (%d boards)', Object.keys(world.boards).length);
}

// ---- SSE client registry -------------------------------------------------

const clients = new Set();

function broadcast(event) {
  if (clients.size === 0) return;
  const payload = `data: ${JSON.stringify(event)}\n\n`;
  for (const res of clients) {
    try { res.write(payload); } catch { /* dropped on next heartbeat */ }
  }
}

setInterval(() => {
  for (const res of clients) {
    try { res.write(`: ping\n\n`); } catch { clients.delete(res); }
  }
}, 25000);

initEngine(world, broadcast);
startEngine();

// ---- Tiny router ---------------------------------------------------------

const SESSION_COOKIE = 'crown_session';

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const { pathname } = url;

  try {
    if (pathname === '/api/stream') return handleStream(req, res);
    if (pathname.startsWith('/api/')) return await handleApi(req, res, url);
    return await serveStatic(req, res, pathname);
  } catch (err) {
    console.error('[crown] request error:', err);
    sendJson(res, 500, { error: 'Internal arena error' });
  }
});

server.listen(PORT, HOST, () => {
  console.log(`\n  👑  THE CROWN is live  →  http://localhost:${PORT}\n`);
  console.log('      Attention is Temporary. Legacy is Forever. Claim the Crown.\n');
});

// ---- SSE handler ---------------------------------------------------------

function handleStream(req, res) {
  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache, no-transform',
    Connection: 'keep-alive',
    'X-Accel-Buffering': 'no',
  });
  res.write(`retry: 3000\n\n`);
  res.write(`data: ${JSON.stringify({ kind: 'hello', stats: homeSummary(world).stats })}\n\n`);
  clients.add(res);
  req.on('close', () => clients.delete(res));
}

// ---- REST API ------------------------------------------------------------

async function handleApi(req, res, url) {
  const parts = url.pathname.split('/').filter(Boolean); // ['api', ...]
  const [, resource, id, action] = parts;

  if (resource === 'health') {
    const health = healthCheck();
    return sendJson(res, health.ok ? 200 : 503, health);
  }

  if (resource === 'auth') return handleAuth(req, res, id);

  if (resource === 'home' && req.method === 'GET') {
    return sendJson(res, 200, homeSummary(world));
  }

  if (resource === 'boards') {
    if (!id && req.method === 'GET') {
      const list = Object.values(world.boards).map(boardCard)
        .sort((a, b) => a.leaderboardPosition - b.leaderboardPosition);
      return sendJson(res, 200, { boards: list });
    }
    const board = world.boards[id];
    if (!board) return sendJson(res, 404, { error: 'Board not found' });

    if (!action && req.method === 'GET') {
      board._recentVisits = (board._recentVisits || 0) + 1;
      board.visits += 1;
      return sendJson(res, 200, boardFull(board));
    }
    if (action === 'challenge' && req.method === 'POST') {
      const user = getSessionUser(req);
      if (!user) return sendJson(res, 401, { error: 'Sign in to challenge a Crown' });
      if (!rateLimit(`act:${user.id}`, { limit: 12, windowMs: 60000 })) {
        return sendJson(res, 429, { error: 'Too many actions — slow down.' });
      }
      const body = await readBody(req);
      const result = challenge(id, { name: user.username, amount: body.amount, type: 'human' });
      return sendJson(res, result.error ? (result.status || 400) : 200, result);
    }
    if (action === 'defend' && req.method === 'POST') {
      const user = getSessionUser(req);
      if (!user) return sendJson(res, 401, { error: 'Sign in to defend a Crown' });
      if (!rateLimit(`act:${user.id}`, { limit: 12, windowMs: 60000 })) {
        return sendJson(res, 429, { error: 'Too many actions — slow down.' });
      }
      const body = await readBody(req);
      const result = defend(id, { name: user.username, amount: body.amount });
      return sendJson(res, result.error ? (result.status || 400) : 200, result);
    }
    if (action === 'cheer' && req.method === 'POST') {
      return sendJson(res, 200, cheer(id));
    }
  }

  if (resource === 'agents') {
    if (!id) {
      const list = Object.values(world.agents).map(agentView)
        .sort((a, b) => b.reputation - a.reputation);
      return sendJson(res, 200, { agents: list });
    }
    const agent = world.agents[id];
    if (!agent) return sendJson(res, 404, { error: 'Agent not found' });
    // Gather this agent's most recent lines across all boards.
    const recent = [];
    for (const b of Object.values(world.boards)) {
      for (const c of b.comments) {
        if (c.agentId === id) recent.push({ ...c, boardName: b.name, boardSlug: b.slug, accent: b.accent });
      }
    }
    recent.sort((x, y) => y.ts - x.ts);
    return sendJson(res, 200, { ...agentView(agent), recent: recent.slice(0, 25) });
  }

  if (resource === 'holders' && req.method === 'GET') {
    const list = Object.values(world.holders).map(holderView)
      .sort((a, b) => b.reputation - a.reputation || b.totalValue - a.totalValue);
    return sendJson(res, 200, { holders: list });
  }

  if (resource === 'halloffame' && req.method === 'GET') {
    const entries = [];
    for (const b of Object.values(world.boards)) {
      for (const e of b.hallOfFame) {
        entries.push({ ...e, boardName: b.name, boardSlug: b.slug, accent: b.accent });
      }
    }
    entries.sort((x, y) => y.lostAt - x.lostAt);
    const ledger = await readLedger(60);
    return sendJson(res, 200, { entries: entries.slice(0, 120), ledger });
  }

  return sendJson(res, 404, { error: 'Unknown endpoint' });
}

function healthCheck() {
  let dbOk = true;
  try {
    db.prepare('SELECT 1').get();
  } catch {
    dbOk = false;
  }
  return {
    ok: dbOk,
    uptime: Date.now() - world.startedAt,
    boards: Object.keys(world.boards).length,
    db: dbOk ? 'ok' : 'unreachable',
  };
}

// ---- Auth ------------------------------------------------------------

async function handleAuth(req, res, action) {
  const ip = req.socket.remoteAddress || 'unknown';

  if (action === 'signup' && req.method === 'POST') {
    if (!rateLimit(`auth:${ip}`, { limit: 10, windowMs: 60000 })) {
      return sendJson(res, 429, { error: 'Too many attempts — try again shortly.' });
    }
    const body = await readBody(req);
    try {
      const user = createUser(body.username, body.password);
      const token = createSession(user.id);
      setSessionCookie(res, token, req);
      return sendJson(res, 200, { user: { username: user.username } });
    } catch (err) {
      return sendJson(res, err.status || 500, { error: err.message || 'Signup failed' });
    }
  }

  if (action === 'login' && req.method === 'POST') {
    if (!rateLimit(`auth:${ip}`, { limit: 10, windowMs: 60000 })) {
      return sendJson(res, 429, { error: 'Too many attempts — try again shortly.' });
    }
    const body = await readBody(req);
    const user = verifyUser(body.username, body.password);
    if (!user) return sendJson(res, 401, { error: 'Wrong handle or password' });
    const token = createSession(user.id);
    setSessionCookie(res, token, req);
    return sendJson(res, 200, { user: { username: user.username } });
  }

  if (action === 'logout' && req.method === 'POST') {
    const token = getCookie(req, SESSION_COOKIE);
    destroySession(token);
    clearSessionCookie(res, req);
    return sendJson(res, 200, { ok: true });
  }

  if (action === 'me' && req.method === 'GET') {
    const user = getSessionUser(req);
    return sendJson(res, 200, { user: user ? { username: user.username } : null });
  }

  return sendJson(res, 404, { error: 'Unknown auth endpoint' });
}

function getSessionUser(req) {
  const token = getCookie(req, SESSION_COOKIE);
  return resolveSession(token);
}

function parseCookies(req) {
  const header = req.headers.cookie;
  const out = {};
  if (!header) return out;
  for (const part of header.split(';')) {
    const i = part.indexOf('=');
    if (i === -1) continue;
    out[part.slice(0, i).trim()] = decodeURIComponent(part.slice(i + 1).trim());
  }
  return out;
}

function getCookie(req, name) {
  return parseCookies(req)[name];
}

function isSecureRequest(req) {
  return req.headers['x-forwarded-proto'] === 'https' || process.env.NODE_ENV === 'production';
}

function setSessionCookie(res, token, req) {
  const maxAgeSec = Math.floor(SESSION_TTL_MS / 1000);
  const secure = isSecureRequest(req) ? ' Secure;' : '';
  res.setHeader('Set-Cookie', `${SESSION_COOKIE}=${token}; HttpOnly; SameSite=Lax; Path=/; Max-Age=${maxAgeSec};${secure}`);
}

function clearSessionCookie(res, req) {
  const secure = isSecureRequest(req) ? ' Secure;' : '';
  res.setHeader('Set-Cookie', `${SESSION_COOKIE}=; HttpOnly; SameSite=Lax; Path=/; Max-Age=0;${secure}`);
}

// ---- Static files --------------------------------------------------------

async function serveStatic(req, res, pathname) {
  let rel = decodeURIComponent(pathname);
  if (rel === '/' || rel === '') rel = '/index.html';

  let filePath = path.normalize(path.join(PUBLIC_DIR, rel));
  // Prevent path traversal outside PUBLIC_DIR.
  if (!filePath.startsWith(PUBLIC_DIR)) {
    res.writeHead(403); return res.end('Forbidden');
  }

  try {
    const data = await fs.readFile(filePath);
    const ext = path.extname(filePath);
    res.writeHead(200, {
      'Content-Type': MIME[ext] || 'application/octet-stream',
      'Cache-Control': ext === '.html' ? 'no-cache' : 'public, max-age=300',
    });
    return res.end(data);
  } catch {
    // SPA fallback — serve index.html for client-side routes.
    try {
      const html = await fs.readFile(path.join(PUBLIC_DIR, 'index.html'));
      res.writeHead(200, { 'Content-Type': MIME['.html'], 'Cache-Control': 'no-cache' });
      return res.end(html);
    } catch {
      res.writeHead(404); return res.end('Not found');
    }
  }
}

// ---- Helpers -------------------------------------------------------------

function sendJson(res, status, obj) {
  const body = JSON.stringify(obj);
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(body),
  });
  res.end(body);
}

function readBody(req) {
  return new Promise((resolve) => {
    let data = '';
    req.on('data', (c) => {
      data += c;
      if (data.length > 1e6) req.destroy(); // basic guard
    });
    req.on('end', () => {
      if (!data) return resolve({});
      try { resolve(JSON.parse(data)); } catch { resolve({}); }
    });
    req.on('error', () => resolve({}));
  });
}

// ---- Graceful shutdown ---------------------------------------------------

function shutdown() {
  console.log('\n[crown] saving arena state…');
  try { saveWorldNow(snapshot(world)); } catch {}
  process.exit(0);
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
