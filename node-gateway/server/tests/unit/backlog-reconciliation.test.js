/**
 * [S9 R2 2026-10-02] Gateway backlog reconciliation: read-only report and an
 * operator-reviewed, idempotent resolution that never deletes rows, sends a
 * message, places an order or fabricates a fill.
 */
const fs = require('fs');
const os = require('os');
const path = require('path');
const Database = require('better-sqlite3');

jest.mock('node-telegram-bot-api', () => jest.fn().mockImplementation(() => ({
  on: jest.fn(), sendMessage: jest.fn(), setWebHook: jest.fn().mockResolvedValue(true),
  stopPolling: jest.fn().mockResolvedValue(true),
})));

const recon = require('../../services/backlog-reconciliation');

// 2026-10-02 11:00 IST
const NOW = new Date('2026-10-02T05:30:00Z');

function fixture() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'backlog-'));
  const dbPath = path.join(dir, 'signals.db');
  const db = new Database(dbPath);
  db.exec(fs.readFileSync(path.join(__dirname, '../../db/schema.sql'), 'utf8'));
  const signal = db.prepare(`INSERT INTO received_signals (signal_id,ticker,signal_time,received_at,payload_json,status,execution_state)
    VALUES (?,?,?,?,?,?,?)`);
  signal.run('old-pending', 'ACME', 't', '2026-09-30T05:00:00Z', '{}', 'PENDING', 'IDLE');
  signal.run('today-pending', 'BETA', 't', '2026-10-02T05:20:00Z', '{}', 'PENDING', 'IDLE');
  signal.run('bad-clock', 'GAMA', 't', 'not-a-time', '{}', 'PENDING', 'IDLE');
  signal.run('stuck', 'DELT', 't', '2026-10-01T05:00:00Z', '{}', 'EXECUTING', 'OUTCOME_UNKNOWN');
  signal.run('done', 'EPSI', 't', '2026-10-01T05:00:00Z', '{}', 'EXECUTED', 'IDLE');
  const order = db.prepare(`INSERT INTO executed_orders (signal_id,ticker,order_id,order_type,entry_price,shares,status,placed_at,sync_to_b)
    VALUES ('done',?,?,?,?,?,?,?,?)`);
  order.run('EPSI', 'O-cancel', 'MARKET', null, 1, 'CANCELLED', '2026-10-01T05:01:00Z', 0);
  order.run('EPSI', 'O-reject', 'MARKET', null, 1, 'REJECTED', '2026-10-01T05:02:00Z', 2);
  order.run('EPSI', 'O-complete', 'MARKET', 101.5, 1, 'COMPLETE', '2026-10-01T05:03:00Z', 0);
  order.run('EPSI', 'O-placed', 'MARKET', null, 1, 'PLACED', '2026-10-01T05:04:00Z', 0);
  order.run('EPSI', 'O-synced', 'MARKET', 99.0, 1, 'COMPLETE', '2026-10-01T05:05:00Z', 1);
  const deadLetter = path.join(dir, 'undelivered_alerts.jsonl');
  fs.writeFileSync(deadLetter, `${JSON.stringify({ ts: '2026-09-29T04:00:00Z', message: 'EXEC ACME', error: 'timeout' })}\n`
    + `${JSON.stringify({ ts: '2026-09-29T04:05:00Z', message: 'EXEC BETA', error: 'timeout' })}\n`);
  return { db, dbPath, deadLetter, dir };
}

const actions = (report) => Object.fromEntries(report.items.filter((i) => i.kind !== 'dead_letter').map((i) => [i.id, i.action]));

test('report classifies every backlog item without writing', () => {
  const { db, dbPath, deadLetter } = fixture();
  db.close();
  const before = fs.readFileSync(dbPath);
  const readonly = new Database(dbPath, { readonly: true, fileMustExist: true });
  const report = recon.buildBacklogReport(readonly, { deadLetterPath: deadLetter, now: NOW });
  readonly.close();
  expect(fs.readFileSync(dbPath).equals(before)).toBe(true);
  expect(actions(report)).toEqual({
    'old-pending': 'EXPIRE', 'today-pending': 'LEAVE', 'bad-clock': 'MANUAL_REVIEW',
    stuck: 'BROKER_RECONCILIATION_REQUIRED', 'O-cancel': 'RESOLVE_NO_SYNC', 'O-reject': 'RESOLVE_NO_SYNC',
    'O-complete': 'LEAVE', 'O-placed': 'BROKER_RECONCILIATION_REQUIRED',
  });
  expect(report.items.filter((i) => i.kind === 'dead_letter')).toHaveLength(2);
  expect(report).toMatchObject({ read_only: true, sends_messages: false, places_orders: false });
});

test('same-day pending expires only after the IST session close', () => {
  const row = { received_at: '2026-10-02T05:20:00Z' };
  expect(recon.classifyPending(row, new Date('2026-10-02T09:59:00Z')).action).toBe('LEAVE');  // 15:29 IST
  expect(recon.classifyPending(row, new Date('2026-10-02T10:00:00Z')).action).toBe('EXPIRE'); // 15:30 IST
});

test('apply needs a reviewed unmodified plan, an operator and explicit confirmation', () => {
  const { db, deadLetter } = fixture();
  const plan = recon.buildBacklogReport(db, { deadLetterPath: deadLetter, now: NOW });
  const opts = { operator: 'owner', confirm: recon.CONFIRMATION, deadLetterPath: deadLetter, now: NOW };
  expect(() => recon.applyBacklogPlan(db, plan, { ...opts, confirm: 'yes' })).toThrow(/confirmation/);
  expect(() => recon.applyBacklogPlan(db, plan, { ...opts, operator: ' ' })).toThrow(/operator/);
  const tampered = { ...plan, items: plan.items.map((i) => (i.id === 'today-pending' ? { ...i, action: 'EXPIRE' } : i)) };
  expect(() => recon.applyBacklogPlan(db, tampered, opts)).toThrow(/unmodified/);
  db.close();
});

test('apply expires, resolves and acknowledges without fills, deletes or resends; repeat is a no-op', () => {
  const { db, deadLetter } = fixture();
  const plan = recon.buildBacklogReport(db, { deadLetterPath: deadLetter, now: NOW });
  const opts = { operator: 'owner', confirm: recon.CONFIRMATION, deadLetterPath: deadLetter, now: NOW };
  const ordersBefore = db.prepare('SELECT order_id, status, entry_price, filled_at, shares FROM executed_orders ORDER BY order_id').all();
  const receipt = recon.applyBacklogPlan(db, plan, opts);
  expect(receipt.applied.map((i) => i.id).sort()).toEqual(
    ['O-cancel', 'O-reject', 'old-pending', ...plan.items.filter((i) => i.kind === 'dead_letter').map((i) => i.id)].sort());
  expect(receipt).toMatchObject({ sends_messages: false, places_orders: false });
  const status = Object.fromEntries(db.prepare('SELECT signal_id, status FROM received_signals').all().map((r) => [r.signal_id, r.status]));
  expect(status).toMatchObject({ 'old-pending': 'EXPIRED', 'today-pending': 'PENDING', 'bad-clock': 'PENDING', stuck: 'EXECUTING' });
  const sync = Object.fromEntries(db.prepare('SELECT order_id, sync_to_b FROM executed_orders').all().map((r) => [r.order_id, r.sync_to_b]));
  expect(sync).toEqual({ 'O-cancel': 3, 'O-reject': 3, 'O-complete': 0, 'O-placed': 0, 'O-synced': 1 });
  // No fill, price, status or row count changed.
  expect(db.prepare('SELECT order_id, status, entry_price, filled_at, shares FROM executed_orders ORDER BY order_id').all())
    .toEqual(ordersBefore);
  expect(fs.readFileSync(deadLetter, 'utf8').split('\n').filter(Boolean)).toHaveLength(2);
  expect(fs.readFileSync(recon.ackPathFor(deadLetter), 'utf8').split('\n').filter(Boolean)).toHaveLength(2);
  const again = recon.applyBacklogPlan(db, plan, opts);
  expect(again.applied).toEqual([]);
  expect(again.already_applied).toHaveLength(receipt.applied.length);
  expect(fs.readFileSync(recon.ackPathFor(deadLetter), 'utf8').split('\n').filter(Boolean)).toHaveLength(2);
  expect(db.prepare('SELECT COUNT(*) AS c FROM backlog_resolutions').get().c).toBe(receipt.applied.length);
  db.close();
});

test('a row changed after review (new callback / broker update) is skipped, not overwritten', () => {
  const { db, deadLetter } = fixture();
  const plan = recon.buildBacklogReport(db, { deadLetterPath: deadLetter, now: NOW });
  db.prepare("UPDATE received_signals SET status='REJECTED' WHERE signal_id='old-pending'").run();
  db.prepare("UPDATE executed_orders SET sync_to_b=1 WHERE order_id='O-cancel'").run();
  const receipt = recon.applyBacklogPlan(db, plan, { operator: 'owner', confirm: recon.CONFIRMATION,
    deadLetterPath: deadLetter, now: NOW });
  expect(receipt.skipped).toEqual(expect.arrayContaining([
    { id: 'old-pending', reason: 'precondition_changed' }, { id: 'O-cancel', reason: 'precondition_changed' }]));
  expect(db.prepare("SELECT status FROM received_signals WHERE signal_id='old-pending'").get().status).toBe('REJECTED');
  db.close();
});

test('health counts only unacknowledged dead letters after acknowledgement', () => {
  const { db, deadLetter } = fixture();
  process.env.ALERT_DEAD_LETTER_PATH = deadLetter;
  jest.resetModules();
  const telegram = require('../../services/telegram');
  expect(telegram.undeliveredAlertCount()).toBe(2);
  const plan = recon.buildBacklogReport(db, { deadLetterPath: deadLetter, now: NOW });
  recon.applyBacklogPlan(db, plan, { operator: 'owner', confirm: recon.CONFIRMATION, deadLetterPath: deadLetter, now: NOW });
  expect(telegram.undeliveredAlertCount()).toBe(0);
  fs.appendFileSync(deadLetter, `${JSON.stringify({ ts: '2026-10-02T05:00:00Z', message: 'new', error: 'x' })}\n`);
  expect(telegram.undeliveredAlertCount()).toBe(1);
  delete process.env.ALERT_DEAD_LETTER_PATH;
  db.close();
});

test('CLI report is read-only and never overwrites its output', () => {
  const { db, dbPath, deadLetter, dir } = fixture();
  db.close();
  const { main } = require('../../scripts/backlog-reconciliation');
  const output = path.join(dir, 'plan.json');
  expect(main(['report', '--db', dbPath, '--dead-letter', deadLetter, '--output', output])).toBe(0);
  expect(JSON.parse(fs.readFileSync(output, 'utf8')).schema).toBe(recon.REPORT_SCHEMA);
  expect(() => main(['report', '--db', dbPath, '--dead-letter', deadLetter, '--output', output])).toThrow();
});

test('reconciliation code has no messaging, broker or order dependency', () => {
  const source = fs.readFileSync(path.join(__dirname, '../../services/backlog-reconciliation.js'), 'utf8');
  expect(source).not.toMatch(/require\(['"].*(telegram|kite|executor|axios|http)/);
});
