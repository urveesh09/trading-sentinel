/**
 * Tests for utils/sanitise.js — sensitive data redaction.
 */
const { sanitise } = require('../../utils/sanitise');

describe('sanitise()', () => {
  test('redacts token field', () => {
    const result = sanitise({ token: 'abc123' });
    expect(result.token).toBe('[REDACTED]');
  });

  test('redacts access_token field', () => {
    const result = sanitise({ access_token: 'xyz789' });
    expect(result.access_token).toBe('[REDACTED]');
  });

  test('redacts api_key field', () => {
    const result = sanitise({ api_key: 'my_key' });
    expect(result.api_key).toBe('[REDACTED]');
  });

  test('redacts api_secret field', () => {
    const result = sanitise({ api_secret: 'my_secret' });
    expect(result.api_secret).toBe('[REDACTED]');
  });

  test('redacts password field', () => {
    const result = sanitise({ password: 'hunter2' });
    expect(result.password).toBe('[REDACTED]');
  });

  test('redacts secret field', () => {
    const result = sanitise({ secret: 'sshh' });
    expect(result.secret).toBe('[REDACTED]');
  });

  test('redacts session field', () => {
    const result = sanitise({ session: 'sess_data' });
    expect(result.session).toBe('[REDACTED]');
  });

  test('preserves non-sensitive fields', () => {
    const result = sanitise({ ticker: 'RELIANCE', close: 500 });
    expect(result.ticker).toBe('RELIANCE');
    expect(result.close).toBe(500);
  });

  test('handles nested objects', () => {
    const result = sanitise({ data: { token: 'abc', name: 'test' } });
    expect(result.data.token).toBe('[REDACTED]');
    expect(result.data.name).toBe('test');
  });

  test('handles arrays', () => {
    const result = sanitise([{ token: 'abc' }, { name: 'test' }]);
    expect(result[0].token).toBe('[REDACTED]');
    expect(result[1].name).toBe('test');
  });

  test('handles null input', () => {
    expect(sanitise(null)).toBeNull();
  });

  test('handles primitive input', () => {
    expect(sanitise('hello')).toBe('hello');
    expect(sanitise(42)).toBe(42);
  });

  test('case-insensitive key matching', () => {
    // Key contains 'token' — should redact
    const result = sanitise({ myTokenValue: 'sensitive' });
    expect(result.myTokenValue).toBe('[REDACTED]');
  });

  test('does not redact non-string sensitive values', () => {
    // Numeric values for sensitive keys should not be redacted
    const result = sanitise({ token: 12345 });
    expect(result.token).toBe(12345);
  });
});
