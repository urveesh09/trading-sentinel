// [MOMENTUM-AUTO 2026-10-04] One execution path for an intraday Momentum
// signal, shared by the Telegram EM button and the automatic route
// (POST /api/internal/momentum-auto-execute). Both therefore get the same
// atomic once-per-ticker-per-day lock, the same approved snapshot and the same
// executor checks (owner halt, CAS/session, token, drift, risk geometry,
// own cash, margin, protective stop and unwind).
const config = require('../config');
const { logger } = require('../middleware/logger');
const { signalsDb } = require('../db/index');
const executor = require('./executor');
const { getApprovedSnapshot } = require('./approved-snapshots');

function momentumLockId(cleanId, now = new Date()) {
  return `${cleanId}_MOM_${now.toISOString().split('T')[0]}`;
}

// Atomic lock:
//   - First attempt: INSERT with EXECUTING status.
//   - Retry after a flat failure (PENDING): flip back to EXECUTING.
//   - In-flight (EXECUTING) or done (EXECUTED): block -- no double orders.
function acquireMomentumLock(lockId, cleanId) {
  return signalsDb.transaction(() => {
    const existing = signalsDb.prepare(
      `SELECT status FROM received_signals WHERE signal_id = ?`
    ).get(lockId);
    if (!existing) {
      signalsDb.prepare(`
        INSERT INTO received_signals (signal_id, ticker, signal_time, received_at, payload_json, status, execution_state)
        VALUES (?, ?, ?, ?, '{}', 'EXECUTING', 'SUBMITTING')
      `).run(lockId, cleanId, new Date().toISOString(), new Date().toISOString());
      return { locked: false };
    }
    if (existing.status === 'PENDING') {
      signalsDb.prepare(`UPDATE received_signals SET status = 'EXECUTING', execution_state = 'SUBMITTING' WHERE signal_id = ?`)
        .run(lockId);
      return { locked: false };
    }
    return { locked: true, status: existing.status };
  })();
}

async function fetchEngineMomentumSignal(cleanId) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), config.PYTHON_ENGINE_TIMEOUT_MS);
  try {
    const resp = await fetch(`${config.PYTHON_ENGINE_URL}/momentum-signals`, {
      headers: { 'X-Internal-Secret': config.INTERNAL_API_SECRET },
      signal: controller.signal,
    });
    const data = await resp.json();
    return data.signals?.find(s => s.ticker === cleanId);
  } finally {
    clearTimeout(timeout);
  }
}

// [FILL-ANCHOR 2026-08-04] Persist what was actually armed, not the signal's
// stale stop/target. Failure is logged, not thrown: acquireMomentumLock left the
// row EXECUTING, which already blocks a second buy.
function recordMomentumExecuted(lockId, signalData, result) {
  const executedPayload = {
    ...signalData,
    shares: result.shares,
    stop_loss: result.stop_loss,
    target_1: result.target_1,
    target_2: result.target_2,
    entry_price: result.fillPrice,
    risk_per_share: result.risk_per_share,
    signal_close: signalData.close,
  };
  try {
    signalsDb.prepare(`
      UPDATE received_signals SET status = 'EXECUTED', execution_state = 'FILLED', payload_json = ? WHERE signal_id = ?
    `).run(JSON.stringify(executedPayload), lockId);
  } catch (err) {
    logger.error({ event_type: 'momentum_executed_record_failed', signal_id: lockId,
      order_id: result.orderId, err: err.message });
  }
}

/**
 * Execute one Momentum signal.
 *
 * @param {object} opts
 * @param {string} opts.signalId   callback/snapshot id (TICKER_MOM)
 * @param {string} opts.cleanId    ticker
 * @param {boolean} opts.allowLiveFetch  button path only: fall back to the
 *        engine's in-memory list when no snapshot exists. The automatic path
 *        passes false -- it executes only a registered snapshot.
 * @param {function} [opts.onStart] called with `true` when executing from the
 *        snapshot, `false` before a live fetch (the button uses it to answer
 *        the Telegram callback promptly).
 * @returns {Promise<{outcome: 'LOCKED'|'EXECUTED'|'FAILED', status?, result?, error?, held?}>}
 */
async function executeMomentum({ signalId, cleanId, allowLiveFetch, onStart = async () => {} }) {
  const lockId = momentumLockId(cleanId);
  const lock = acquireMomentumLock(lockId, cleanId);
  if (lock.locked) return { outcome: 'LOCKED', status: lock.status };

  try {
    // [HIGH-007] Approved snapshot first: the engine's momentum list is
    // in-memory and a restart wipes it; the snapshot is on disk.
    let signalData = getApprovedSnapshot(signalId, 'EM');
    if (signalData) {
      await onStart(true);
    } else {
      logger.warn({ event_type: 'approved_snapshot_missing', signal_id: signalId, action: 'EM' });
      if (allowLiveFetch) {
        await onStart(false);
        signalData = await fetchEngineMomentumSignal(cleanId);
      }
    }
    if (!signalData) {
      signalsDb.prepare(`UPDATE received_signals SET status = 'PENDING' WHERE signal_id = ?`).run(lockId);
      throw new Error(allowLiveFetch ? 'Momentum signal not found in Engine state.'
        : 'Momentum snapshot not registered; automatic execution requires it.');
    }

    // MomentumSignal has no signal_id; executed_orders.signal_id is NOT NULL.
    signalData.signal_id = lockId;
    const result = await executor.executeSignal(signalData, 'EM', true);
    // [DISPATCH-LOCK 2026-10-05] The BUY is filled from here on. A failure to
    // record it must leave the row EXECUTING (locked), never reset it.
    recordMomentumExecuted(lockId, signalData, result);
    return { outcome: 'EXECUTED', result, signalData };
  } catch (err) {
    // A held position (stop and unwind failed) or an unknown broker outcome
    // must stay locked: a retry would stack a second buy.
    if (err && (err.positionHeld || err.outcomeUnknown)) {
      const state = err.positionHeld ? 'HELD_UNPROTECTED' : 'OUTCOME_UNKNOWN';
      signalsDb.prepare(`UPDATE received_signals SET status = 'EXECUTING', execution_state = ? WHERE signal_id = ?`)
        .run(state, lockId);
      logger.error({ event_type: 'momentum_execution_failed', held: true, state, err: err.message });
      return { outcome: 'FAILED', error: err, held: true };
    }
    signalsDb.prepare(`UPDATE received_signals SET status = 'PENDING', execution_state = 'IDLE' WHERE signal_id = ?`)
      .run(lockId);
    logger.error({ event_type: 'momentum_execution_failed', err: err.message });
    return { outcome: 'FAILED', error: err, held: false };
  }
}

module.exports = { executeMomentum, momentumLockId };
