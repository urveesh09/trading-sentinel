#!/usr/bin/env node
/**
 * [S9 R2] Gateway backlog reconciliation CLI.
 *
 *   node scripts/backlog-reconciliation.js report --db <signals.db> --dead-letter <file> --output <plan.json>
 *   node scripts/backlog-reconciliation.js apply  --db <signals.db> --dead-letter <file> --plan <plan.json> \
 *        --operator <name> --confirm APPLY_REVIEWED_BACKLOG_PLAN --output <receipt.json>
 *
 * `report` opens the database read-only. `apply` is a separate, operator-reviewed
 * step; running it against Production requires separate operator approval.
 * Outputs are created exclusively (never overwritten).
 */
const fs = require('fs');
const Database = require('better-sqlite3');
const { applyBacklogPlan, buildBacklogReport } = require('../services/backlog-reconciliation');

function args(argv) {
  const out = { _: [] };
  for (let i = 0; i < argv.length; i += 1) {
    if (argv[i].startsWith('--')) { out[argv[i].slice(2)] = argv[i + 1]; i += 1; } else out._.push(argv[i]);
  }
  return out;
}

function writeOnce(path, value) {
  fs.writeFileSync(path, `${JSON.stringify(value, null, 2)}\n`, { flag: 'wx' });
}

function main(argv) {
  const opts = args(argv);
  const command = opts._[0];
  if (!['report', 'apply'].includes(command) || !opts.db || !opts['dead-letter'] || !opts.output) {
    throw new Error('usage: report|apply --db <signals.db> --dead-letter <file> --output <file> [...]');
  }
  if (command === 'report') {
    const db = new Database(opts.db, { readonly: true, fileMustExist: true });
    try { writeOnce(opts.output, buildBacklogReport(db, { deadLetterPath: opts['dead-letter'] })); }
    finally { db.close(); }
    return 0;
  }
  const plan = JSON.parse(fs.readFileSync(opts.plan, 'utf8'));
  const db = new Database(opts.db, { fileMustExist: true });
  try {
    writeOnce(opts.output, applyBacklogPlan(db, plan, { operator: opts.operator, confirm: opts.confirm,
      deadLetterPath: opts['dead-letter'] }));
  } finally { db.close(); }
  return 0;
}

if (require.main === module) {
  try { process.exitCode = main(process.argv.slice(2)); }
  catch (err) { console.error(JSON.stringify({ state: 'BACKLOG_RECONCILIATION_REFUSED', error: err.message })); process.exitCode = 2; }
}

module.exports = { main };
