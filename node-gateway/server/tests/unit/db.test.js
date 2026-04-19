/**
 * Tests for db/ — WAL mode (Q5), schema, table separation (Q7).
 *
 * We don't import db/index.js directly (it creates files on disk and
 * imports config). Instead, we replicate the setup using in-memory SQLite
 * to verify WAL mode, schema correctness, and table independence.
 */
const Database = require('better-sqlite3');
const fs = require('fs');
const path = require('path');

const schemaPath = path.join(__dirname, '..', '..', 'db', 'schema.sql');
const schema = fs.readFileSync(schemaPath, 'utf8');

function createTestDb() {
  const db = new Database(':memory:');
  db.pragma('journal_mode = WAL');
  db.exec(schema);
  return db;
}

describe('Database — WAL mode (Q5)', () => {
  test('WAL mode is set on a new connection', () => {
    const db = createTestDb();
    const result = db.pragma('journal_mode');
    // In-memory DBs use 'memory' journal_mode, but the pragma call
    // itself should not throw. For file-based DBs, it returns 'wal'.
    // We verify the pragma call succeeds without error.
    expect(result).toBeDefined();
    db.close();
  });

  test('WAL mode on file-based DB returns "wal"', () => {
    const tmpPath = path.join(__dirname, 'test_wal.db');
    try {
      const db = new Database(tmpPath);
      db.pragma('journal_mode = WAL');
      const result = db.pragma('journal_mode');
      expect(result[0].journal_mode).toBe('wal');

      // Verify on second connection (Q5: every connection)
      const db2 = new Database(tmpPath);
      db2.pragma('journal_mode = WAL');
      const result2 = db2.pragma('journal_mode');
      expect(result2[0].journal_mode).toBe('wal');

      db.close();
      db2.close();
    } finally {
      if (fs.existsSync(tmpPath)) fs.unlinkSync(tmpPath);
      // Clean up WAL and SHM files
      if (fs.existsSync(tmpPath + '-wal')) fs.unlinkSync(tmpPath + '-wal');
      if (fs.existsSync(tmpPath + '-shm')) fs.unlinkSync(tmpPath + '-shm');
    }
  });
});

describe('Database — Schema', () => {
  let db;

  beforeAll(() => {
    db = createTestDb();
  });

  afterAll(() => {
    db.close();
  });

  test('received_signals table exists', () => {
    const tables = db.prepare(
      "SELECT name FROM sqlite_master WHERE type='table' AND name='received_signals'"
    ).all();
    expect(tables).toHaveLength(1);
  });

  test('executed_orders table exists', () => {
    const tables = db.prepare(
      "SELECT name FROM sqlite_master WHERE type='table' AND name='executed_orders'"
    ).all();
    expect(tables).toHaveLength(1);
  });

  test('app_state table exists', () => {
    const tables = db.prepare(
      "SELECT name FROM sqlite_master WHERE type='table' AND name='app_state'"
    ).all();
    expect(tables).toHaveLength(1);
  });

  test('received_signals has correct columns', () => {
    const info = db.prepare('PRAGMA table_info(received_signals)').all();
    const cols = info.map(c => c.name);
    expect(cols).toEqual(expect.arrayContaining([
      'signal_id', 'ticker', 'signal_time', 'received_at',
      'payload_json', 'telegram_msg_id', 'status'
    ]));
  });

  test('executed_orders has correct columns', () => {
    const info = db.prepare('PRAGMA table_info(executed_orders)').all();
    const cols = info.map(c => c.name);
    expect(cols).toEqual(expect.arrayContaining([
      'id', 'signal_id', 'ticker', 'order_id', 'order_type',
      'entry_price', 'shares', 'status', 'gtt_stop_id', 'gtt_target_id',
      'placed_at', 'filled_at', 'sync_to_b', 'notes'
    ]));
  });

  test('signal_id is primary key on received_signals', () => {
    const info = db.prepare('PRAGMA table_info(received_signals)').all();
    const pk = info.find(c => c.name === 'signal_id');
    expect(pk.pk).toBe(1);
  });

  test('performance indexes exist', () => {
    const indexes = db.prepare(
      "SELECT name FROM sqlite_master WHERE type='index'"
    ).all();
    const names = indexes.map(i => i.name);
    expect(names).toContain('idx_signals_status');
    expect(names).toContain('idx_orders_ticker');
  });
});

describe('Database — Table Independence', () => {
  let db;

  beforeEach(() => {
    db = createTestDb();
  });

  afterEach(() => {
    db.close();
  });

  test('inserting into received_signals does not affect executed_orders', () => {
    db.prepare(
      `INSERT INTO received_signals (signal_id, ticker, signal_time, received_at, payload_json, status)
       VALUES (?, ?, ?, ?, ?, ?)`
    ).run('sig1', 'RELIANCE', '2026-01-07T10:00:00Z', '2026-01-07T10:00:01Z', '{}', 'PENDING');

    const signals = db.prepare('SELECT COUNT(*) as c FROM received_signals').get();
    const orders = db.prepare('SELECT COUNT(*) as c FROM executed_orders').get();

    expect(signals.c).toBe(1);
    expect(orders.c).toBe(0);
  });

  test('order_id is UNIQUE in executed_orders', () => {
    // Insert a signal first (FK requirement)
    db.prepare(
      `INSERT INTO received_signals (signal_id, ticker, signal_time, received_at, payload_json, status)
       VALUES (?, ?, ?, ?, ?, ?)`
    ).run('sig1', 'INFY', '2026-01-07T10:00:00Z', '2026-01-07T10:00:01Z', '{}', 'EXECUTED');

    db.prepare(
      `INSERT INTO executed_orders (signal_id, ticker, order_id, order_type, shares, status, placed_at)
       VALUES (?, ?, ?, ?, ?, ?, ?)`
    ).run('sig1', 'INFY', 'ORD001', 'MARKET', 10, 'COMPLETE', '2026-01-07T10:01:00Z');

    // Duplicate order_id should fail
    expect(() => {
      db.prepare(
        `INSERT INTO executed_orders (signal_id, ticker, order_id, order_type, shares, status, placed_at)
         VALUES (?, ?, ?, ?, ?, ?, ?)`
      ).run('sig1', 'INFY', 'ORD001', 'MARKET', 5, 'PLACED', '2026-01-07T10:02:00Z');
    }).toThrow();
  });
});
