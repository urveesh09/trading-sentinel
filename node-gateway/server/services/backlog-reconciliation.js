/**
 * [S9 R2 2026-10-02] Gateway backlog reconciliation: read-only report plus an
 * operator-reviewed, idempotent resolution.
 *
 * Contract
 * - `buildBacklogReport` never writes. It classifies pending requests,
 *   interrupted executions, unsynced orders and dead-lettered alerts, giving
 *   each a proposed action, a reason and a precondition fingerprint.
 * - `applyBacklogPlan` acts only on a reviewed report, named operator and
 *   explicit confirmation. Inside one IMMEDIATE transaction it re-reads every
 *   row, skips any whose fingerprint changed (a new callback, a broker update,
 *   a race), and records an audit receipt. Repeating it is a no-op.
 * - Nothing is deleted, no broker call or Telegram message is made, no fill is
 *   fabricated, and a dead letter is only acknowledged — never resent.
 *   EXECUTING / OUTCOME_UNKNOWN rows always need broker reconciliation.
 */
const crypto = require('crypto');
const fs = require('fs');

const CONFIRMATION = 'APPLY_REVIEWED_BACKLOG_PLAN';
const REPORT_SCHEMA = 'gateway_backlog_report_v1';
const IST_OFFSET_MS = 330 * 60 * 1000;
const SESSION_END_MINUTE = 15 * 60 + 30; // NSE cash close, IST

const sha = (value) => crypto.createHash('sha256').update(value).digest('hex');
const fingerprint = (value) => sha(JSON.stringify(value));

function istParts(date) {
  const shifted = new Date(date.getTime() + IST_OFFSET_MS);
  return { day: shifted.toISOString().slice(0, 10), minute: shifted.getUTCHours() * 60 + shifted.getUTCMinutes() };
}

/** Classify one PENDING request by the IST session it belongs to. */
function classifyPending(row, now) {
  const received = new Date(row.received_at);
  if (!row.received_at || Number.isNaN(received.getTime())) {
    return { action: 'MANUAL_REVIEW', reason: 'received_at_unparseable' };
  }
  const then = istParts(received);
  const current = istParts(now);
  if (then.day < current.day) return { action: 'EXPIRE', reason: 'ist_session_ended_prior_day' };
  if (then.day === current.day && current.minute >= SESSION_END_MINUTE) {
    return { action: 'EXPIRE', reason: 'ist_session_closed_today' };
  }
  if (then.day > current.day) return { action: 'MANUAL_REVIEW', reason: 'received_at_in_future' };
  return { action: 'LEAVE', reason: 'session_still_open' };
}

const pendingFields = (row) => ({ signal_id: row.signal_id, status: row.status,
  execution_state: row.execution_state, received_at: row.received_at, telegram_msg_id: row.telegram_msg_id });
const orderFields = (row) => ({ order_id: row.order_id, signal_id: row.signal_id, status: row.status,
  sync_to_b: row.sync_to_b, filled_at: row.filled_at, entry_price: row.entry_price, shares: row.shares });

function readDeadLetters(deadLetterPath) {
  let raw = '';
  try { raw = fs.readFileSync(deadLetterPath, 'utf8'); } catch (_) { return []; }
  return raw.split('\n').filter(Boolean).map((line, index) => ({ line, index, fingerprint: sha(line) }));
}

function readAcknowledged(ackPath) {
  const acked = new Set();
  let raw = '';
  try { raw = fs.readFileSync(ackPath, 'utf8'); } catch (_) { return acked; }
  for (const line of raw.split('\n').filter(Boolean)) {
    try { const record = JSON.parse(line); if (record && record.fingerprint) acked.add(record.fingerprint); }
    catch (_) { /* torn trailing line from an interrupted append: ignored */ }
  }
  return acked;
}

const ackPathFor = (deadLetterPath) => `${deadLetterPath}.ack.jsonl`;

/** Read-only classification of every backlog item. */
function buildBacklogReport(signalsDb, { deadLetterPath, now = new Date() }) {
  const items = [];
  for (const row of signalsDb.prepare(
    `SELECT signal_id, status, execution_state, received_at, telegram_msg_id FROM received_signals
     WHERE status IN ('PENDING','EXECUTING') ORDER BY received_at, signal_id`).all()) {
    if (row.status === 'EXECUTING') {
      items.push({ kind: 'execution', id: row.signal_id, action: 'BROKER_RECONCILIATION_REQUIRED',
        reason: `execution_state_${row.execution_state}`, precondition: fingerprint(pendingFields(row)) });
      continue;
    }
    const { action, reason } = classifyPending(row, now);
    items.push({ kind: 'pending_request', id: row.signal_id, action, reason,
      precondition: fingerprint(pendingFields(row)) });
  }
  for (const row of signalsDb.prepare(
    `SELECT order_id, signal_id, status, sync_to_b, filled_at, entry_price, shares FROM executed_orders
     WHERE sync_to_b IS NULL OR sync_to_b NOT IN (1, 3) ORDER BY placed_at, order_id`).all()) {
    if (row.status === 'CANCELLED' || row.status === 'REJECTED') {
      items.push({ kind: 'terminal_unsynced_order', id: row.order_id, action: 'RESOLVE_NO_SYNC',
        reason: `terminal_${row.status.toLowerCase()}_has_no_fill_to_sync`, precondition: fingerprint(orderFields(row)) });
    } else if (row.status === 'COMPLETE') {
      items.push({ kind: 'completed_unsynced_order', id: row.order_id, action: 'LEAVE',
        reason: 'startup_recovery_retries_completed_sync', precondition: fingerprint(orderFields(row)) });
    } else {
      items.push({ kind: 'open_order', id: row.order_id, action: 'BROKER_RECONCILIATION_REQUIRED',
        reason: `order_status_${row.status}`, precondition: fingerprint(orderFields(row)) });
    }
  }
  const acknowledged = readAcknowledged(ackPathFor(deadLetterPath));
  for (const entry of readDeadLetters(deadLetterPath)) {
    if (acknowledged.has(entry.fingerprint)) continue;
    let ts = null;
    try { ts = JSON.parse(entry.line).ts || null; } catch (_) { ts = null; }
    items.push({ kind: 'dead_letter', id: entry.fingerprint, action: 'ACKNOWLEDGE_NO_RESEND',
      reason: 'historical_alert_never_resent', recorded_at: ts, precondition: entry.fingerprint });
  }
  const report = { schema: REPORT_SCHEMA, generated_at: now.toISOString(), read_only: true,
    sends_messages: false, places_orders: false, items,
    counts: items.reduce((acc, item) => { acc[item.action] = (acc[item.action] || 0) + 1; return acc; }, {}) };
  report.plan_fingerprint = fingerprint(items);
  return report;
}

const RECEIPT_DDL = `CREATE TABLE IF NOT EXISTS backlog_resolutions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  item_kind TEXT NOT NULL, item_id TEXT NOT NULL, action TEXT NOT NULL,
  precondition TEXT NOT NULL, reason TEXT NOT NULL, operator TEXT NOT NULL,
  plan_fingerprint TEXT NOT NULL, applied_at TEXT NOT NULL,
  UNIQUE(item_kind, item_id, action))`;

/** Apply a reviewed plan; returns a receipt. Re-running is idempotent. */
function applyBacklogPlan(signalsDb, plan, { operator, confirm, deadLetterPath, now = new Date() }) {
  if (confirm !== CONFIRMATION) throw new Error(`confirmation must be ${CONFIRMATION}`);
  if (!operator || !String(operator).trim()) throw new Error('a named operator is required');
  if (!plan || plan.schema !== REPORT_SCHEMA || plan.plan_fingerprint !== fingerprint(plan.items || [])) {
    throw new Error('plan is not an unmodified backlog report');
  }
  const appliedAt = now.toISOString();
  const outcome = { applied: [], skipped: [], already_applied: [] };
  signalsDb.exec(RECEIPT_DDL);
  const receipt = signalsDb.prepare(`INSERT OR IGNORE INTO backlog_resolutions
    (item_kind,item_id,action,precondition,reason,operator,plan_fingerprint,applied_at) VALUES (?,?,?,?,?,?,?,?)`);
  const acknowledgements = [];
  const run = signalsDb.transaction(() => {
    for (const item of plan.items) {
      if (!['EXPIRE', 'RESOLVE_NO_SYNC', 'ACKNOWLEDGE_NO_RESEND'].includes(item.action)) continue;
      const done = signalsDb.prepare(
        'SELECT 1 FROM backlog_resolutions WHERE item_kind=? AND item_id=? AND action=?').get(item.kind, item.id, item.action);
      if (done) { outcome.already_applied.push(item.id); continue; }
      if (item.action === 'EXPIRE') {
        const row = signalsDb.prepare(`SELECT signal_id, status, execution_state, received_at, telegram_msg_id
          FROM received_signals WHERE signal_id=?`).get(item.id);
        if (!row || fingerprint(pendingFields(row)) !== item.precondition) { outcome.skipped.push({ id: item.id, reason: 'precondition_changed' }); continue; }
        if (classifyPending(row, now).action !== 'EXPIRE') { outcome.skipped.push({ id: item.id, reason: 'no_longer_expired' }); continue; }
        const changed = signalsDb.prepare(`UPDATE received_signals SET status='EXPIRED',
          execution_state='EXPIRED_BY_RECONCILIATION' WHERE signal_id=? AND status='PENDING'`).run(item.id).changes;
        if (changed !== 1) { outcome.skipped.push({ id: item.id, reason: 'precondition_changed' }); continue; }
      } else if (item.action === 'RESOLVE_NO_SYNC') {
        const row = signalsDb.prepare(`SELECT order_id, signal_id, status, sync_to_b, filled_at, entry_price, shares
          FROM executed_orders WHERE order_id=?`).get(item.id);
        if (!row || fingerprint(orderFields(row)) !== item.precondition) { outcome.skipped.push({ id: item.id, reason: 'precondition_changed' }); continue; }
        // sync_to_b = 3: terminal order with nothing to sync. No fill, price or status is changed.
        const changed = signalsDb.prepare(`UPDATE executed_orders SET sync_to_b = 3 WHERE order_id=?
          AND status IN ('CANCELLED','REJECTED') AND (sync_to_b IS NULL OR sync_to_b NOT IN (1, 3))`).run(item.id).changes;
        if (changed !== 1) { outcome.skipped.push({ id: item.id, reason: 'precondition_changed' }); continue; }
      } else {
        const present = readDeadLetters(deadLetterPath).some((entry) => entry.fingerprint === item.id);
        if (!present) { outcome.skipped.push({ id: item.id, reason: 'dead_letter_not_found' }); continue; }
        acknowledgements.push(item);
      }
      receipt.run(item.kind, item.id, item.action, item.precondition, item.reason, String(operator).trim(),
        plan.plan_fingerprint, appliedAt);
      outcome.applied.push({ id: item.id, kind: item.kind, action: item.action });
    }
  });
  run.immediate();
  // Acknowledgement is an append-only sibling ledger written after the DB
  // receipts commit; the original dead-letter lines are never modified.
  const ackPath = ackPathFor(deadLetterPath);
  const already = readAcknowledged(ackPath);
  for (const item of acknowledgements) {
    if (already.has(item.id)) continue;
    fs.appendFileSync(ackPath, `${JSON.stringify({ fingerprint: item.id, operator: String(operator).trim(),
      acknowledged_at: appliedAt, resent: false, plan_fingerprint: plan.plan_fingerprint })}\n`);
  }
  return { schema: 'gateway_backlog_receipt_v1', plan_fingerprint: plan.plan_fingerprint, operator: String(operator).trim(),
    applied_at: appliedAt, sends_messages: false, places_orders: false, ...outcome };
}

module.exports = { CONFIRMATION, REPORT_SCHEMA, ackPathFor, applyBacklogPlan, buildBacklogReport,
  classifyPending, readAcknowledged };
