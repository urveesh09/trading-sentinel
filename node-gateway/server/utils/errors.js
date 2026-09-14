class AppError extends Error {
  constructor(message, type, statusCode, clientMessage) {
    super(message);
    this.name = this.constructor.name;
    this.type = type;
    this.statusCode = statusCode;
    this.clientMessage = clientMessage;
    Error.captureStackTrace(this, this.constructor);
  }
}

class TokenExpiredError extends AppError {
  constructor(message = 'Zerodha token expired') {
    super(message, 'token_expired', 401, 'Trading session expired. Please log in again.');
  }
}

class ValidationError extends AppError {
  constructor(message = 'Validation failed') {
    super(message, 'validation_error', 422, 'Invalid request parameters.');
  }
}

class OrderExecutionError extends AppError {
  constructor(message = 'Order execution failed') {
    super(message, 'execution_error', 502, 'Broker execution failed.');
  }
}

class InsufficientMarginError extends AppError {
  constructor(required, available) {
    super(
      `INSUFFICIENT_MARGIN: required ${Number(required).toFixed(2)}, available ${Number(available).toFixed(2)}`,
      'insufficient_margin', 409,
      'Insufficient usable broker margin for this new entry. No order was submitted.'
    );
    this.required = Number(required);
    this.available = Number(available);
    this.code = 'INSUFFICIENT_MARGIN';
    this.retryable = false;
  }
}

class SyncBackError extends AppError {
  constructor(message = 'Sync to Engine failed') {
    super(message, 'sync_error', 502, 'Position sync delayed. Manual check advised.');
  }
}

class StaleSignalError extends AppError {
  constructor(message = 'Signal is too old') {
    super(message, 'stale_signal', 422, 'Signal expired (>60s) and was rejected.');
  }
}

class PriceDriftError extends AppError {
  constructor(message = 'Price drifted beyond 2% threshold') {
    super(message, 'price_drift', 422, 'Execution aborted due to excessive price drift.');
  }
}

class MarketClosedError extends AppError {
  constructor(message = 'Market is currently closed') {
    super(message, 'market_closed', 422, 'Market is closed. Cannot execute order.');
  }
}

// [WORKFLOW-J.7 2026-09-13] CAS-aware execution guard.
// Thrown when the bounded session phase is one that blocks
// broker orders (CAS_REFERENCE_PRICE_WINDOW / CAS_ORDER_ENTRY /
// CAS_LIMIT_ENTRY_ONLY / CAS_MATCHING / CAS_POST) or PRE_MARKET
// when allow_pre_market is not set. The ``phase`` and
// ``reason`` fields surface the verdict to the operator.
class CasPhaseError extends AppError {
  constructor(phase, reason) {
    super(
      reason || `CAS phase ${phase} blocks broker orders`,
      'cas_phase_blocked',
      422,
      reason || 'Closing-auction phase; broker orders are blocked until continuous trading resumes.'
    );
    this.phase = phase;
    this.reason = reason;
  }
}

class DuplicateSignalError extends AppError {
  constructor(message = 'Duplicate signal received') {
    super(message, 'duplicate_signal', 200, 'Signal already processed.');
  }
}

class ReplayAttackError extends AppError {
  constructor(message = 'Callback replay detected') {
    super(message, 'replay_attack', 409, 'Action already taken.');
  }
}

module.exports = {
  AppError,
  TokenExpiredError,
  ValidationError,
  OrderExecutionError,
  InsufficientMarginError,
  SyncBackError,
  StaleSignalError,
  PriceDriftError,
  MarketClosedError,
  DuplicateSignalError,
  ReplayAttackError
};
