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
  SyncBackError,
  StaleSignalError,
  PriceDriftError,
  MarketClosedError,
  DuplicateSignalError,
  ReplayAttackError
};
