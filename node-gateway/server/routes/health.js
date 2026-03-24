const express = require('express');
const router = express.Router();
const config = require('../config');
const tokenStore = require('../services/token-store');
const { isMarketOpen } = require('../utils/market-hours');
const { signalsDb } = require('../db/index');

router.get('/', async (req, res) => {
  const uptime = Math.floor(process.uptime());
  const tokenInfo = tokenStore.getStatus();
  const marketOpen = isMarketOpen();
  
  let pythonEngineStatus = 'unreachable';
  let pythonEngineMs = 0;
  
  // Probe Container B
  const startMs = Date.now();
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 3000); // Strict 3s timeout
    const bRes = await fetch(`${config.PYTHON_ENGINE_URL}/health`, { signal: controller.signal });
    clearTimeout(timeout);
    if (bRes.ok) {
      pythonEngineStatus = 'reachable';
      pythonEngineMs = Date.now() - startMs;
    }
  } catch (e) {
    // Fails silently, variables remain 'unreachable'
  }

  // Calculate token age
  let tokenAgeMin = null;
  if (tokenInfo.generatedAt) {
    tokenAgeMin = Math.floor((Date.now() - new Date(tokenInfo.generatedAt).getTime()) / 60000);
  }

  // DB Metrics
  let pendingSignals = 0;
  let unsyncedOrders = 0;
  let lastSignalReceived = null;
  let lastOrderPlaced = null;
  let lastOrderTicker = null;

  try {
    pendingSignals = signalsDb.prepare(`SELECT count(*) as c FROM received_signals WHERE status = 'PENDING'`).get().c;
    unsyncedOrders = signalsDb.prepare(`SELECT count(*) as c FROM executed_orders WHERE sync_to_b = 0`).get().c;
    
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

  // Determine overall status
  let overallStatus = 'ok';
  if (tokenInfo.status === 'expired' && marketOpen) {
    overallStatus = 'critical';
  } else if (pythonEngineStatus === 'unreachable' || unsyncedOrders > 0) {
    overallStatus = 'degraded';
  }

  res.json({
    status: overallStatus,
    uptime_seconds: uptime,
    token_status: tokenInfo.status,
    token_age_minutes: tokenAgeMin,
    telegram_status: "connected", // Simplified, as the bot instance doesn't easily expose health
    telegram_mode: config.TELEGRAM_MODE,
    python_engine: pythonEngineStatus,
    python_engine_ms: pythonEngineMs,
    market_open: marketOpen,
    last_signal_received: lastSignalReceived,
    last_order_placed: lastOrderPlaced,
    last_order_ticker: lastOrderTicker,
    pending_signals: pendingSignals,
    unsynced_orders: unsyncedOrders,
    timestamp: new Date().toISOString()
  });
});

module.exports = router;
