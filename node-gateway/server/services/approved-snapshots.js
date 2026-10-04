const { logger } = require('../middleware/logger');
const { signalsDb } = require('../db/index');

// [HIGH-007 / ROADMAP-4.5 2026-07-13] Approved snapshot lookup.
//
// Returns the exact payload that was DISPLAYED to the operator for this
// callback id, or null if the sender never registered one. The `action` is
// matched too, so an EXEC id can never resolve to an EM snapshot (they carry
// different sizing and a different product type -- CNC vs MIS -- and confusing
// them would place the wrong kind of order).
//
// Never throws: a corrupt row must degrade to "missing", not kill the caller.
function getApprovedSnapshot(signalId, action) {
  try {
    const snap = signalsDb.prepare(
      `SELECT payload_json FROM approved_snapshots WHERE signal_id = ? AND action = ?`
    ).get(signalId, action);
    if (!snap) return null;
    return JSON.parse(snap.payload_json);
  } catch (err) {
    logger.error({ event_type: 'approved_snapshot_read_failed', signalId, action, err: err.message });
    return null;
  }
}

module.exports = { getApprovedSnapshot };
