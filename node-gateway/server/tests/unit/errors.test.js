/**
 * Tests for utils/errors.js - custom error classes.
 */
const {
  AppError,
  TokenExpiredError,
  ValidationError,
  OrderExecutionError,
  PriceDriftError,
  MarketClosedError,
  DuplicateSignalError,
  ReplayAttackError,
  StaleSignalError,
  SyncBackError,
} = require('../../utils/errors');

describe('AppError', () => {
  test('creates error with all fields', () => {
    const err = new AppError('internal msg', 'CUSTOM', 500, 'user msg');
    expect(err.message).toBe('internal msg');
    expect(err.type).toBe('CUSTOM');
    expect(err.statusCode).toBe(500);
    expect(err.clientMessage).toBe('user msg');
    expect(err instanceof Error).toBe(true);
  });
});

describe('Specific error subclasses', () => {
  test('TokenExpiredError has statusCode 401', () => {
    const err = new TokenExpiredError();
    expect(err.statusCode).toBe(401);
    expect(err.type).toBe('token_expired');
  });

  test('ValidationError has statusCode 422', () => {
    const err = new ValidationError('bad input');
    expect(err.statusCode).toBe(422);
  });

  test('OrderExecutionError has statusCode 502', () => {
    const err = new OrderExecutionError('kite failed');
    expect(err.statusCode).toBe(502);
  });

  test('PriceDriftError has statusCode 422', () => {
    const err = new PriceDriftError('drifted too far');
    expect(err.statusCode).toBe(422);
  });

  test('MarketClosedError has statusCode 422', () => {
    const err = new MarketClosedError();
    expect(err.statusCode).toBe(422);
  });

  test('DuplicateSignalError has statusCode 200', () => {
    const err = new DuplicateSignalError('already exists');
    expect(err.statusCode).toBe(200);
  });

  test('ReplayAttackError has statusCode 409', () => {
    const err = new ReplayAttackError('replay');
    expect(err.statusCode).toBe(409);
  });

  test('StaleSignalError has statusCode 422', () => {
    const err = new StaleSignalError('too old');
    expect(err.statusCode).toBe(422);
  });

  test('SyncBackError has statusCode 502', () => {
    const err = new SyncBackError('sync failed');
    expect(err.statusCode).toBe(502);
  });

  test('all errors are instances of AppError', () => {
    expect(new TokenExpiredError()).toBeInstanceOf(AppError);
    expect(new PriceDriftError('')).toBeInstanceOf(AppError);
    expect(new MarketClosedError()).toBeInstanceOf(AppError);
  });
});
