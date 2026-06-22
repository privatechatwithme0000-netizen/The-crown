// Persistence layer.
//
// Two artifacts live in /data:
//   world.json          — the full live world snapshot (rewritten periodically)
//   halloffame.ndjson   — an APPEND-ONLY ledger. Every Hall of Fame entry and
//                          crown transfer is appended and never rewritten or
//                          deleted, honoring "this history can never be deleted."

import { promises as fs } from 'node:fs';
import fsSync from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const DATA_DIR = path.join(__dirname, '..', 'data');
const WORLD_FILE = path.join(DATA_DIR, 'world.json');
const LEDGER_FILE = path.join(DATA_DIR, 'halloffame.ndjson');

function ensureDir() {
  if (!fsSync.existsSync(DATA_DIR)) fsSync.mkdirSync(DATA_DIR, { recursive: true });
}

export async function loadWorld() {
  ensureDir();
  try {
    const raw = await fs.readFile(WORLD_FILE, 'utf8');
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

let saveQueued = false;
let lastSnapshot = null;

// Debounced atomic write so frequent ticks don't thrash the disk.
export function saveWorld(snapshot) {
  lastSnapshot = snapshot;
  if (saveQueued) return;
  saveQueued = true;
  setTimeout(async () => {
    saveQueued = false;
    const data = lastSnapshot;
    try {
      ensureDir();
      const tmp = WORLD_FILE + '.tmp';
      await fs.writeFile(tmp, JSON.stringify(data), 'utf8');
      await fs.rename(tmp, WORLD_FILE);
    } catch (err) {
      console.error('[store] world save failed:', err.message);
    }
  }, 1500);
}

export function saveWorldNow(snapshot) {
  try {
    ensureDir();
    fsSync.writeFileSync(WORLD_FILE, JSON.stringify(snapshot), 'utf8');
  } catch (err) {
    console.error('[store] sync world save failed:', err.message);
  }
}

// Append one immutable record to the permanent ledger.
export function appendLedger(record) {
  try {
    ensureDir();
    fsSync.appendFileSync(LEDGER_FILE, JSON.stringify({ ...record, at: Date.now() }) + '\n', 'utf8');
  } catch (err) {
    console.error('[store] ledger append failed:', err.message);
  }
}

export async function readLedger(limit = 200) {
  try {
    const raw = await fs.readFile(LEDGER_FILE, 'utf8');
    const lines = raw.split('\n').filter(Boolean);
    const slice = lines.slice(-limit);
    return slice.map((l) => JSON.parse(l)).reverse();
  } catch {
    return [];
  }
}

export function resetWorldFiles() {
  ensureDir();
  for (const f of [WORLD_FILE, WORLD_FILE + '.tmp']) {
    if (fsSync.existsSync(f)) fsSync.unlinkSync(f);
  }
  // Note: the ledger is intentionally NOT deleted — legacy is forever.
}

export { DATA_DIR, WORLD_FILE, LEDGER_FILE };
