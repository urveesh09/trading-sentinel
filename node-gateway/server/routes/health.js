const express = require('express');
const router = express.Router();
const config = require('../config');
const tokenStore = require('../services/token-store');
const { isMarketOpen, sessionPhase, currentSessionPhase } = require('../utils/market-hours');
const { signalsDb } = require('../db/index');
const { undeliveredAlertSummary } = require('../services/telegram');
const { releaseIdentity } = require('../release-identity');

// [S23-H1 2026-10-23] Old, settled backlog is reported, not alarmed. On Oct 23
// health stayed 'degraded' all day for 8 dead letters (8-24 Sep), 10
// PENDING signals from 29 Jun-7 Oct and 4 CANCELLED/REJECTED orders never
// synced; a flag that is always raised cannot report a new failure. Health
// now degrades for a dead letter or an unsynced order from the last
// HEALTH_BACKLOG_RECENT_HOURS, and for an unsynced order of any age that may
// have filled (not CANCELLED/REJECTED). Everything older is in stale_backlog
// until the reviewed backlog reconciliation resolves it.
const RECENT_HOURS = Number(process.env.HEALTH_BACKLOG_RECENT_HOURS) > 0
  ? Number(process.env.HEALTH_BACKLOG_RECENT_HOURS) : 24;

router.get('/', async (req, res) => {
  const uptime = Math.floor(process.uptime());
  const tokenInfo = tokenStore.getStatus();
  const marketOpen = isMarketOpen();
  
  let pythonEngineStatus = 'unreachable';
  let pythonEngineMs = 0;
  let pythonEngineRelease = null;
  
  // Probe Container B
  const startMs = Date.now();
  let timeout;
  try {
    const controller = new AbortController();
    timeout = setTimeout(() => controller.abort(), 3000); // Strict 3s timeout
    const bRes = await fetch(`${config.PYTHON_ENGINE_URL}/health`, { signal: controller.signal });
    if (bRes.ok) {
      pythonEngineStatus = 'reachable';
      pythonEngineMs = Date.now() - startMs;
      // Release identity is diagnostic only: an unreadable response must not
      // make the gateway health endpoint fail or conceal a connectivity fact.
      try {
        const engineBody = await bRes.json();
        if (engineBody && typeof engineBody.release === 'object') {
          pythonEngineRelease = engineBody.release;
        }
      } catch (err) {
        // Leave it null; the deploy verifier will reject missing identity.
      }
    }
  } catch (e) {
    // Fails silently, variables remain 'unreachable'
  } finally {
    // Also release the deadline after a non-2xx response or fetch failure.
    clearTimeout(timeout);
  }

  // Calculate token age
  let tokenAgeMin = null;
  if (tokenInfo.generatedAt) {
    tokenAgeMin = Math.floor((Date.now() - new Date(tokenInfo.generatedAt).getTime()) / 60000);
  }

  // DB Metrics
  let pendingSignals = 0;
  let unsyncedOrders = 0;
  let actionableUnsynced = 0;
  let stalePending = 0;
  let lastSignalReceived = null;
  let lastOrderPlaced = null;
  let lastOrderTicker = null;
  const recentMs = RECENT_HOURS * 3600 * 1000;
  const cutoff = new Date(Date.now() - recentMs).toISOString();

  try {
    pendingSignals = signalsDb.prepare(`SELECT count(*) as c FROM received_signals WHERE status = 'PENDING'`).get().c;
    unsyncedOrders = signalsDb.prepare(`SELECT count(*) as c FROM executed_orders WHERE sync_to_b = 0`).get().c;
    stalePending = signalsDb.prepare(
      `SELECT count(*) as c FROM received_signals WHERE status = 'PENDING' AND received_at < ?`
    ).get(cutoff).c;
    actionableUnsynced = signalsDb.prepare(
      `SELECT count(*) as c FROM executed_orders WHERE sync_to_b = 0
         AND (placed_at >= ? OR UPPER(COALESCE(status, '')) NOT IN ('CANCELLED', 'REJECTED'))`
    ).get(cutoff).c;

    const lastSig = signalsDb.prepare(`SELECT received_at FROM received_signals ORDER BY received_at DESC LIMIT 1`).get();
    if (lastSig) lastSignalReceived = lastSig.received_at;

    const lastOrd = signalsDb.prepare(`SELECT placed_at, ticker FROM executed_orders ORDER BY placed_at DESC LIMIT 1`).get();
    if (lastOrd) {
      lastOrderPlaced = lastOrd.placed_at;
      lastOrderTicker = lastOrd.ticker;
    }
  } catch (err) {
    // Handle DB query failure gracefully
  }

  // [ALERT-DEADLETTER 2026-07-31] Alerts that exhausted every retry. On
  // 2026-07-28 a momentum EXEC alert died after 3 retries and the only trace
  // was one log line. Telegram is the broken channel when this happens, so the
  // backlog is surfaced here instead -- a non-zero count means the operator has
  // been told something they never received.
  let undeliveredAlerts = 0;
  let recentUndelivered = 0;
  let oldestUndeliveredAt = null;
  try {
    const summary = undeliveredAlertSummary({ recentMs });
    undeliveredAlerts = summary.open;
    recentUndelivered = summary.recent;
    oldestUndeliveredAt = summary.oldest_ts;
  } catch (err) {
    // Never let a health probe fail on a bookkeeping read.
  }

  // Determine overall status
  let overallStatus = 'ok';
  if (tokenInfo.status === 'expired' && marketOpen) {
    overallStatus = 'critical';
  } else if (pythonEngineStatus === 'unreachable' || actionableUnsynced > 0
             || recentUndelivered > 0) {
    overallStatus = 'degraded';
  }
  let telegramStatus = 'diagnostic_bot_instance_present';
  if (recentUndelivered > 0) telegramStatus = 'delivery_backlog_present';
  else if (undeliveredAlerts > 0) telegramStatus = 'stale_delivery_backlog_present';

  res.json({
    status: overallStatus,
    uptime_seconds: uptime,
    token_status: tokenInfo.status,
    token_age_minutes: tokenAgeMin,
    // A bot instance existing is not delivery confirmation.  Preserve the
    // established field for clients, but make its diagnostic-only basis
    // explicit and surface the durable dead-letter backlog separately.
    telegram_status: telegramStatus,
    telegram_status_basis: "bot_instance_and_local_dead_letter_backlog_not_transport_probe",
    telegram_mode: config.TELEGRAM_MODE,
    python_engine: pythonEngineStatus,
    python_engine_ms: pythonEngineMs,
    market_open: marketOpen,
    // [WORKFLOW-J.6] Bounded session phase (mirror of
    // ``python-engine/market_calendar.classify_session_phase``).
    // Operators can use this to surface CAS sub-windows in
    // dashboards and to gate CAS-aware decisions in services.
    // The reading is fresh on every request (no caching) so the
    // phase is always current as of the response moment.
    session_phase: currentSessionPhase(),
    last_signal_received: lastSignalReceived,
    last_order_placed: lastOrderPlaced,
    last_order_ticker: lastOrderTicker,
    pending_signals: pendingSignals,
    unsynced_orders: unsyncedOrders,
    undelivered_alerts: undeliveredAlerts,
    // [S23-H1] What degrades health now, and the older backlog kept visible.
    actionable_unsynced_orders: actionableUnsynced,
    recent_undelivered_alerts: recentUndelivered,
    stale_backlog: {
      recent_hours: RECENT_HOURS,
      undelivered_alerts: undeliveredAlerts - recentUndelivered,
      oldest_undelivered_at: oldestUndeliveredAt,
      unsynced_settled_orders: unsyncedOrders - actionableUnsynced,
      pending_signals: stalePending,
      resolve_with: 'reviewed backlog reconciliation (server/scripts/backlog-reconciliation.js)',
    },
    release: releaseIdentity('node-gateway'),
    python_engine_release: pythonEngineRelease,
    timestamp: new Date().toISOString()
  });
});

module.exports = router;
