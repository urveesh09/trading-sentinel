// Durable P1 own-cash reservation protocol.  This intentionally mirrors
// python-engine/account_cash_reservations.py and operates on shared cache.db.
const Database = require('better-sqlite3');
const path = require('path');
const config = require('../config');

const ACTIVE = new Set(['RESERVED', 'DISPATCHED', 'AMBIGUOUS', 'PARTIAL']);
const OPEN = new Set(['OPEN', 'TRIGGER PENDING', 'AMO REQ RECEIVED', 'OPEN PENDING',
  'VALIDATION PENDING', 'PUT ORDER REQ RECEIVED', 'MODIFY PENDING', 'MODIFY VALIDATION PENDING']);

function entryChargeReserve(notional) {
  if (!(Number.isFinite(notional) && notional > 0)) throw new Error('notional must be positive and finite');
  const brokerage = Math.min(notional * 0.0003, 20);
  const exchangeAndSebi = notional * (0.000035 + 0.000001);
  const gst = 0.18 * (brokerage + exchangeAndSebi);
  const stamp = notional * 0.00015;
  return Math.ceil((brokerage + exchangeAndSebi + gst + stamp) * 100) / 100;
}

function reservationAmount(notional) {
  const charges = entryChargeReserve(notional);
  const buffer = Math.ceil(notional * 0.01 * 100) / 100;
  return { amount: Number((notional + charges + buffer).toFixed(2)), charges, buffer };
}

function brokerRepresents(row, orders) {
  return orders.some((order) => {
    if (!order || typeof order !== 'object') return false;
    const sameId = row.broker_order_id && String(order.order_id || '') === row.broker_order_id;
    const sameTag = row.broker_tag && String(order.tag || '') === row.broker_tag;
    if (!sameId && !sameTag) return false;
    const status = String(order.status || '').toUpperCase();
    return String(order.transaction_type || '').toUpperCase() === 'BUY' &&
      (OPEN.has(status) || status === 'COMPLETE');
  });
}

class AccountCashReservations {
  constructor(dbPath) {
    this.db = new Database(dbPath);
    this.db.pragma('journal_mode = WAL');
    this.db.pragma('busy_timeout = 30000');
    this.db.exec(`CREATE TABLE IF NOT EXISTS account_cash_reservations (
      reservation_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, book TEXT NOT NULL,
      broker_tag TEXT NOT NULL, broker_order_id TEXT, amount REAL NOT NULL CHECK(amount > 0),
      charge_reserve REAL NOT NULL CHECK(charge_reserve >= 0),
      fill_buffer REAL NOT NULL CHECK(fill_buffer >= 0),
      state TEXT NOT NULL CHECK(state IN ('RESERVED','DISPATCHED','AMBIGUOUS','PARTIAL','RELEASED')),
      created_at TEXT NOT NULL, updated_at TEXT NOT NULL, release_reason TEXT
    ); CREATE INDEX IF NOT EXISTS idx_account_cash_active
      ON account_cash_reservations(account_id, state);`);
  }

  reserve({ reservationId, accountId, book, brokerTag, notional, ownUncommittedCash, brokerOrders }) {
    if (![reservationId, accountId, book, brokerTag].every((v) => typeof v === 'string' && v)) {
      throw new Error('ACCOUNT_RESERVATION_EVIDENCE_UNAVAILABLE: invalid reservation identity');
    }
    if (!(Number.isFinite(ownUncommittedCash) && ownUncommittedCash >= 0) || !Array.isArray(brokerOrders)) {
      throw new Error('ACCOUNT_RESERVATION_EVIDENCE_UNAVAILABLE: own-cash/order evidence unavailable');
    }
    const { amount, charges, buffer } = reservationAmount(notional);
    const now = new Date().toISOString();
    return this.db.transaction(() => {
      const existing = this.db.prepare('SELECT * FROM account_cash_reservations WHERE reservation_id=?').get(reservationId);
      if (existing) {
        if (existing.state === 'RELEASED') throw new Error('ACCOUNT_RESERVATION_REUSED: released id cannot dispatch again');
        return { reservationId, amount: existing.amount, chargeReserve: existing.charge_reserve,
          fillBuffer: existing.fill_buffer, availableAfter: ownUncommittedCash };
      }
      const active = this.db.prepare("SELECT * FROM account_cash_reservations WHERE account_id=? AND state IN ('RESERVED','DISPATCHED','AMBIGUOUS','PARTIAL')").all(accountId);
      const held = active.reduce((sum, row) => sum + (brokerRepresents(row, brokerOrders) ? 0 : row.amount), 0);
      const availableAfter = ownUncommittedCash - held - amount;
      if (availableAfter < -0.00001) {
        throw new Error(`ACCOUNT_OWN_CASH_INSUFFICIENT: required ${amount.toFixed(2)}, uncommitted ${ownUncommittedCash.toFixed(2)}, local holds ${held.toFixed(2)}`);
      }
      this.db.prepare(`INSERT INTO account_cash_reservations
        (reservation_id,account_id,book,broker_tag,amount,charge_reserve,fill_buffer,state,created_at,updated_at)
        VALUES (?,?,?,?,?,?,?,'RESERVED',?,?)`).run(reservationId, accountId, book, brokerTag,
        amount, charges, buffer, now, now);
      return { reservationId, amount, chargeReserve: charges, fillBuffer: buffer, availableAfter: Math.max(0, availableAfter) };
    })();
  }

  markDispatch(reservationId, { brokerOrderId = null, ambiguous = false } = {}) {
    const result = this.db.prepare(`UPDATE account_cash_reservations
      SET broker_order_id=COALESCE(?, broker_order_id), state=?, updated_at=?
      WHERE reservation_id=? AND state IN ('RESERVED','DISPATCHED','AMBIGUOUS','PARTIAL')`)
      .run(brokerOrderId, ambiguous ? 'AMBIGUOUS' : 'DISPATCHED', new Date().toISOString(), reservationId);
    if (result.changes !== 1) throw new Error('ACCOUNT_RESERVATION_MISSING: dispatch state was not retained');
  }

  releaseNotSent(reservationId, reason) {
    return this.db.prepare(`UPDATE account_cash_reservations SET state='RELEASED', release_reason=?, updated_at=?
      WHERE reservation_id=? AND state='RESERVED'`).run(String(reason).slice(0, 100), new Date().toISOString(), reservationId).changes === 1;
  }

  releaseZeroFill(reservationId, { brokerOrderId, terminalStatus, filledQuantity }) {
    if (!brokerOrderId || !['CANCELLED', 'REJECTED'].includes(String(terminalStatus || '').toUpperCase()) || Number(filledQuantity) !== 0) return false;
    return this.db.prepare(`UPDATE account_cash_reservations SET state='RELEASED', release_reason=?, updated_at=?
      WHERE reservation_id=? AND broker_order_id=? AND state IN ('RESERVED','DISPATCHED','AMBIGUOUS','PARTIAL')`)
      .run(`verified_${String(terminalStatus).toLowerCase()}_zero_fill`, new Date().toISOString(), reservationId, brokerOrderId).changes === 1;
  }
}

const dataDir = config.NODE_ENV === 'production' ? '/data' : path.join(__dirname, '../../data');
const shared = new AccountCashReservations(process.env.ACCOUNT_CASH_RESERVATION_DB_PATH || path.join(dataDir, 'cache.db'));

module.exports = { AccountCashReservations, entryChargeReserve, reservationAmount, shared };
