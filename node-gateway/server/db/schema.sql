-- Enable Write-Ahead Logging for concurrency
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS received_signals (
  signal_id       TEXT PRIMARY KEY,
  ticker          TEXT NOT NULL,
  signal_time     TEXT NOT NULL,
  received_at     TEXT NOT NULL,
  payload_json    TEXT NOT NULL,
  telegram_msg_id INTEGER,
  status          TEXT NOT NULL CHECK (status IN ('PENDING','EXECUTING','EXECUTED','REJECTED','EXPIRED'))
);

CREATE TABLE IF NOT EXISTS executed_orders (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  signal_id       TEXT NOT NULL REFERENCES received_signals(signal_id),
  ticker          TEXT NOT NULL,
  order_id        TEXT NOT NULL UNIQUE,
  order_type      TEXT NOT NULL, -- "MARKET" | "GTT"
  entry_price     REAL,
  shares          INTEGER NOT NULL,
  status          TEXT NOT NULL CHECK (status IN ('PLACED','COMPLETE','REJECTED','CANCELLED')),
  gtt_stop_id     TEXT,
  gtt_target_id   TEXT,
  sl_order_id     TEXT,  -- broker-side SL-M protecting an MIS position (GTT is CNC-only)
  placed_at       TEXT NOT NULL,
  filled_at       TEXT,
  sync_to_b       INTEGER DEFAULT 0, -- 0=pending, 1=done, 2=failed
  notes           TEXT
);

CREATE TABLE IF NOT EXISTS app_state (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- [HIGH-007 / ROADMAP-4.5 2026-07-13] The approved snapshot.
--
-- The EXEC/EM callback handlers used to RE-FETCH the signal from the engine
-- at button-press time and execute whatever came back. So the price, share
-- count and stop that were shown in the Telegram message -- the numbers the
-- operator actually approved -- were not necessarily the numbers that got
-- executed. Two ways that bites:
--
--   1. Swing: /signals serves `current_signals`, which run_screener REPLACES
--      wholesale on every run. A re-run between alert and press changes the
--      numbers under the operator's feet.
--   2. Either book: if the re-fetch no longer contains the ticker, the press
--      dies with "signal not found" and the approved trade is simply lost.
--      The engine's momentum list is in-memory, so a restart wipes it -- as
--      happened on 2026-07-13 at 09:44.
--
-- Fix: the sender (agent) registers the EXACT payload it is about to display,
-- keyed by the SAME id it puts in callback_data. The handler then executes
-- that row. What you approved is what executes.
--
-- Immutable by construction: writes are INSERT OR IGNORE, so a re-alert for
-- the same id can never rewrite an already-approved snapshot.
CREATE TABLE IF NOT EXISTS approved_snapshots (
  signal_id    TEXT PRIMARY KEY,   -- exactly the callback_data id (TICKER / TICKER_MOM)
  ticker       TEXT NOT NULL,
  action       TEXT NOT NULL CHECK (action IN ('EXEC','EM')),
  payload_json TEXT NOT NULL,
  created_at   TEXT NOT NULL
);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS idx_signals_status ON received_signals(status);
CREATE INDEX IF NOT EXISTS idx_orders_ticker ON executed_orders(ticker);

-- [HIGH-009] Status integrity triggers — enforce valid status values on EXISTING tables too.
-- SQLite CHECK constraints only apply at table creation; triggers cover live tables.
CREATE TRIGGER IF NOT EXISTS enforce_signal_status_insert
BEFORE INSERT ON received_signals FOR EACH ROW
BEGIN
  SELECT CASE
    WHEN NEW.status NOT IN ('PENDING','EXECUTING','EXECUTED','REJECTED','EXPIRED')
    THEN RAISE(ABORT, 'Invalid status for received_signals')
  END;
END;

CREATE TRIGGER IF NOT EXISTS enforce_signal_status_update
BEFORE UPDATE ON received_signals FOR EACH ROW
BEGIN
  SELECT CASE
    WHEN NEW.status NOT IN ('PENDING','EXECUTING','EXECUTED','REJECTED','EXPIRED')
    THEN RAISE(ABORT, 'Invalid status for received_signals')
  END;
END;

CREATE TRIGGER IF NOT EXISTS enforce_order_status_insert
BEFORE INSERT ON executed_orders FOR EACH ROW
BEGIN
  SELECT CASE
    WHEN NEW.status NOT IN ('PLACED','COMPLETE','REJECTED','CANCELLED')
    THEN RAISE(ABORT, 'Invalid status for executed_orders')
  END;
END;

CREATE TRIGGER IF NOT EXISTS enforce_order_status_update
BEFORE UPDATE ON executed_orders FOR EACH ROW
BEGIN
  SELECT CASE
    WHEN NEW.status NOT IN ('PLACED','COMPLETE','REJECTED','CANCELLED')
    THEN RAISE(ABORT, 'Invalid status for executed_orders')
  END;
END;
