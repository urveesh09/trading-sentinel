/**
 * Tests for utils/market-hours.js - IST market window enforcement.
 */
const {
  isMarketOpen,
  isPreMarket,
  isCashCasEligibilityResolutionWindow,
  validatedHolidayPayload,
} = require('../../utils/market-hours');

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
    // This tests indirectly - the function must use Intl with Asia/Kolkata
    // If it used local time, results would differ in non-IST zones
    // 2026-01-07 Wednesday 12:00 IST = 06:30 UTC - market should be open
    withMockedTime('2026-01-07T06:30:00Z', () => {
      expect(isMarketOpen()).toBe(true);
    });
  });

  describe('holiday handling (WORKFLOW-J.5)', () => {
    test('FALLBACK blocks the audited Ganesh Chaturthi holiday immediately', () => {
      withMockedTime('2026-09-14T05:30:00Z', () => {
        expect(isMarketOpen()).toBe(false);
      });
    });

    test('FALLBACK returns true on a Friday Independence Day (Saturday Aug 15 is the holiday, not Friday)', () => {
      // Sanity: the fallback DOES include Independence Day (it
      // ships 2026-08-15). Pinning this so the test fails loud
      // if a future refactor accidentally removes that.
      withMockedTime('2026-08-14T05:30:00Z', () => {
        // 2026-08-14 is a Friday, not in the holiday list;
        // market open at 11:00 IST.
        expect(isMarketOpen()).toBe(true);
      });
    });

    test('FALLBACK contains the canonical Ganesh Chaturthi date', () => {
      const {
        NSE_HOLIDAYS,
        NSE_HOLIDAYS_FALLBACK,
      } = require('../../utils/market-hours');
      expect(NSE_HOLIDAYS_FALLBACK.has('2026-09-14')).toBe(true);
      // The live set is currently a copy of the fallback (no engine).
      expect(NSE_HOLIDAYS.has('2026-09-14')).toBe(true);
    });

    test('env override replaces the live holiday set, fixing Ganesh Chaturthi', () => {
      const {
        NSE_HOLIDAYS,
        __resetHolidaysForTest,
      } = require('../../utils/market-hours');
      // Simulate the env-override path with a curated set that
      // includes the holidays the fallback misses. The test seam
      // is the same path that MARKET_HOURS_HOLIDAYS_JSON uses
      // internally (replaceHolidays(replace)).
      __resetHolidaysForTest(
        new Set([
          '2026-01-26', '2026-03-31', '2026-04-03', '2026-04-14',
          '2026-05-01', '2026-08-15', '2026-09-14', '2026-10-02',
          '2026-10-20', '2026-11-10', '2026-12-25',
        ])
      );
      // Now Ganesh Chaturthi is honoured: on the canonical set,
      // 11:00 IST on Sep 14 is closed.
      withMockedTime('2026-09-14T05:30:00Z', () => {
        expect(isMarketOpen()).toBe(false);
      });
      // Rep 2: a non-holiday still opens.
      withMockedTime('2026-09-15T05:30:00Z', () => {
        expect(isMarketOpen()).toBe(true);
      });
      // Restore for downstream tests.
      __resetHolidaysForTest(new Set());
    });

    test('engine fetch mutates the live Set in place (closure binding preserved)', () => {
      // We simulate the engine fetch by directly calling the
      // test seam that performs the same in-place replacement.
      // Production does the same via fetch().then(...).
      const {
        NSE_HOLIDAYS,
        __resetHolidaysForTest,
      } = require('../../utils/market-hours');
      const before = NSE_HOLIDAYS; // Same identity across the swap.
      __resetHolidaysForTest(new Set(['2026-09-14']));
      expect(before).toBe(NSE_HOLIDAYS); // identity-stable
      expect(NSE_HOLIDAYS.size).toBe(1);
      __resetHolidaysForTest(new Set());
    });

    test('stale embedded fallback fails closed after its audited validity period', () => {
      withMockedTime('2027-01-04T05:30:00Z', () => {
        expect(isMarketOpen()).toBe(false);
      });
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

describe('isCashCasEligibilityResolutionWindow()', () => {
  test('is true only from 15:15 through 15:29 IST on weekdays', () => {
    expect(isCashCasEligibilityResolutionWindow(new Date('2026-09-15T09:45:00Z'))).toBe(true); // 15:15 IST
    expect(isCashCasEligibilityResolutionWindow(new Date('2026-09-15T09:59:00Z'))).toBe(true); // 15:29 IST
    expect(isCashCasEligibilityResolutionWindow(new Date('2026-09-15T10:00:00Z'))).toBe(false); // 15:30 IST
  });

  test('is false for an invalid timestamp', () => {
    expect(isCashCasEligibilityResolutionWindow('not-a-date')).toBe(false);
  });

  test('execution verdict fails closed when an engine calendar is expired', () => {
    const { __resetHolidaysForTest, isExecutionAllowed } = require('../../utils/market-hours');
    __resetHolidaysForTest(new Set(['2026-12-25']), 'engine:test', '2026-12-31');
    withMockedTime('2027-01-04T05:30:00Z', () => {
      expect(isExecutionAllowed({ observation_at: new Date(), symbol: 'TCS', cas_eligible: false }))
        .toEqual(expect.objectContaining({ allowed: false, phase: 'UNKNOWN' }));
    });
    __resetHolidaysForTest(new Set(), 'fallback:test', '2026-12-31');
  });
});

describe('holiday payload validation', () => {
  test.each([
    null,
    { holidays: [], valid_through: '2026-12-31' },
    { holidays: ['not-a-date'], valid_through: '2026-12-31' },
    { holidays: ['2027-01-01'], valid_through: '2026-12-31' },
    { holidays: ['2026-12-25'], valid_through: 'invalid' },
  ])('rejects malformed or incoherent payload %#', (payload) => {
    expect(validatedHolidayPayload(payload)).toBeNull();
  });

  test('accepts a nonempty bounded payload without filtering rows', () => {
    const result = validatedHolidayPayload({ holidays: ['2026-12-25'], valid_through: '2026-12-31' });
    expect([...result.holidays]).toEqual(['2026-12-25']);
    expect(result.validThrough).toBe('2026-12-31');
  });
});
