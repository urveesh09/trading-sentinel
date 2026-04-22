/**
 * Tests for services/token-store.js - in-memory token management.
 */
const tokenStore = require('../../services/token-store');

describe('TokenStore', () => {
  beforeEach(() => {
    tokenStore.clearToken();
  });

  test('setToken stores token and marks valid', () => {
    tokenStore.setToken('test_access_token');
    expect(tokenStore.getToken()).toBe('test_access_token');
    expect(tokenStore.isValid()).toBe(true);
  });

  test('getToken returns null when no token set', () => {
    expect(tokenStore.getToken()).toBeNull();
  });

  test('isValid returns false when no token set', () => {
    expect(tokenStore.isValid()).toBe(false);
  });

  test('markExpired invalidates token but keeps it stored', () => {
    tokenStore.setToken('abc');
    expect(tokenStore.isValid()).toBe(true);
    tokenStore.markExpired();
    expect(tokenStore.isValid()).toBe(false);
    // Token is still stored in memory, just marked expired
    expect(tokenStore.getToken()).toBe('abc');
  });

  test('clearToken removes everything', () => {
    tokenStore.setToken('abc');
    tokenStore.clearToken();
    expect(tokenStore.getToken()).toBeNull();
    expect(tokenStore.isValid()).toBe(false);
  });

  test('getStatus returns active when token set', () => {
    tokenStore.setToken('abc');
    const status = tokenStore.getStatus();
    expect(status.status).toBe('active');
    expect(status.generatedAt).toBeDefined();
  });

  test('getStatus returns expired after markExpired', () => {
    tokenStore.setToken('abc');
    tokenStore.markExpired();
    const status = tokenStore.getStatus();
    expect(status.status).toBe('expired');
  });

  test('getStatus returns expired when no token', () => {
    const status = tokenStore.getStatus();
    expect(status.status).toBe('expired');
    expect(status.generatedAt).toBeNull();
  });

  test('setToken updates generatedAt timestamp', () => {
    const before = new Date().toISOString();
    tokenStore.setToken('tok');
    const status = tokenStore.getStatus();
    expect(status.generatedAt).toBeDefined();
    expect(new Date(status.generatedAt).getTime()).toBeGreaterThanOrEqual(new Date(before).getTime() - 1);
  });
});
