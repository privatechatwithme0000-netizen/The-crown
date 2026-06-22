// Small maintenance CLI. Usage: node server/cli.js <command>
//
//   reset   Reseed a fresh world snapshot. The permanent Hall of Fame ledger
//           (data/halloffame.ndjson) is intentionally preserved — legacy is forever.

import { createWorld, snapshot } from './state.js';
import { saveWorldNow, resetWorldFiles } from './store.js';

const cmd = process.argv[2];

if (cmd === 'reset') {
  resetWorldFiles();
  const world = createWorld();
  saveWorldNow(snapshot(world));
  console.log('[crown] arena reseeded. The Hall of Fame ledger was preserved.');
} else {
  console.log('Usage: node server/cli.js reset');
  process.exit(cmd ? 1 : 0);
}
