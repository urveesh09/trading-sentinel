/**
 * Tests for utils/market-hours.js — IST market window enforcement.
 */
const { isMarketOpen, isPreMarket } = require('../../utils/market-hours');

// Helper to mock Date.now() and global Date for specific IST times
function withMockedTime(isoString, fn) {
  const orig = global.Date;
  const fixed = new orig(isoString);
  global.Date = class extends orig {
    constructor(...args) {
      if (args.length === 0) return fixed;
      return new orig(...args);
    }
    static now() { return fixed.getTime(); }
  };
  // preserve static methods
  global.Date.UTC = orig.UTC;
  global.Date.parse = orig.parse;
  try {
    return fn();
  } finally {
    global.Date = orig;
  }
}

describe('isMarketOpen()', () => {
  test('returns false before 09:15 IST (09:14)', () => {
    // 09:14 IST = 03:44 UTC
    withMockedTime('2026-01-07T03:44:00Z', () => {
      expect(isMarketOpen()).toBe(false);
    });
  });

  test('returns true at 09:15 IST', () => {
    // 09:15 IST = 03:45 UTC
    withMockedTime('2026-01-07T03:45:00Z', () => {
      expect(isMarketOpen()).toBe(true);
    });
  });

  test('returns true at 11:00 IST on a weekday', () => {
    // 11:00 IST = 05:30 UTC (Wednesday Jan 7 2026)
    withMockedTime('2026-01-07T05:30:00Z', () => {
      expect(isMarketOpen()).toBe(true);
    });
  });

  test('returns true at 15:29 IST', () => {
    // 15:29 IST = 09:59 UTC
    withMockedTime('2026-01-07T09:59:00Z', () => {
      expect(isMarketOpen()).toBe(true);
    });
  });

  test('returns false at 15:30 IST (market close)', () => {
    // 15:30 IST = 10:00 UTC
    withMockedTime('2026-01-07T10:00:00Z', () => {
      expect(isMarketOpen()).toBe(false);
    });
  });

  test('returns false after 15:30 IST (16:00)', () => {
    // 16:00 IST = 10:30 UTC
    withMockedTime('2026-01-07T10:30:00Z', () => {
      expect(isMarketOpen()).toBe(false);
    });
  });

  test('returns false on Saturday', () => {
    // 2026-01-10 is Saturday, 11:00 IST
    withMockedTime('2026-01-10T05:30:00Z', () => {
      expect(isMarketOpen()).toBe(false);
    });
  });

  test('returns false on Sunday', () => {
    // 2026-01-11 is Sunday, 11:00 IST
    withMockedTime('2026-01-11T05:30:00Z', () => {
      expect(isMarketOpen()).toBe(false);
    });
  });

  test('uses Asia/Kolkata timezone (not server local time)', () => {
    // This tests indirectly — the function must use Intl with Asia/Kolkata
    // If it used local time, results would differ in non-IST zones
    // 2026-01-07 Wednesday 12:00 IST = 06:30 UTC — market should be open
    withMockedTime('2026-01-07T06:30:00Z', () => {
      expect(isMarketOpen()).toBe(true);
    });
  });
});

describe('isPreMarket()', () => {
  test('returns true at 09:00 IST', () => {
    // 09:00 IST = 03:30 UTC
    withMockedTime('2026-01-07T03:30:00Z', () => {
      expect(isPreMarket()).toBe(true);
    });
  });

  test('returns true at 09:14 IST', () => {
    // 09:14 IST = 03:44 UTC
    withMockedTime('2026-01-07T03:44:00Z', () => {
      expect(isPreMarket()).toBe(true);
    });
  });

  test('returns false at 09:15 IST (market opens)', () => {
    // 09:15 IST = 03:45 UTC
    withMockedTime('2026-01-07T03:45:00Z', () => {
      expect(isPreMarket()).toBe(false);
    });
  });

  test('returns false before 09:00 IST', () => {
    // 08:59 IST = 03:29 UTC
    withMockedTime('2026-01-07T03:29:00Z', () => {
      expect(isPreMarket()).toBe(false);
    });
  });

  test('returns false on Saturday', () => {
    // 2026-01-10 Saturday, 09:10 IST
    withMockedTime('2026-01-10T03:40:00Z', () => {
      expect(isPreMarket()).toBe(false);
    });
  });
});
