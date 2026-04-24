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
  placed_at       TEXT NOT NULL,
  filled_at       TEXT,
  sync_to_b       INTEGER DEFAULT 0, -- 0=pending, 1=done, 2=failed
  notes           TEXT
);

CREATE TABLE IF NOT EXISTS app_state (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
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
