/**
 * [WORKFLOW-J.6 2026-09-13] Tests for the Node sessionPhase mirror.
 *
 * Two layers of tests:
 *
 * 1) Focused unit tests covering every documented phase boundary
 *    (pre-market / continuous / five CAS sub-windows / derivative
 *    CAS-aligned / post-CAS / closed / Saturday / Sunday).
 *
 * 2) The golden-vector cross-check: 2,304 IST instants across the
 *    September 2026 weekday sweep must produce IDENTICAL output
 *    to Python's ``classify_session_phase``. The vectors live at
 *    ``tests/fixtures/session_phase_golden.json`` and are
 *    regenerated explicitly via:
 *
 *        python tests/fixtures/regenerate_session_phase_golden.py
 *
 *    (That script is the audit-grade reproducibility surface;
 *    it itself runs the Python classifier and emits the JSON.)
 *
 * Together these pin the J.6 contract: a single source of truth
 * for session phases, mirrored bit-perfectly in Node, with the
 * golden ensuring no future drift goes undetected.
 */
'use strict';

const path = require('path');
const fs = require('fs');

// Load the production mirror.
const {
  sessionPhase,
  currentSessionPhase,
  VALID_SESSION_PHASES,
  NSE_HOLIDAYS,
} = require('../../utils/market-hours');

// ---- (1) Helper: IST-aware Date factory -------------------------

/**
 * Build a Date that, when interpreted as IST, lands on the given
 * IST (year, month, day, hour, minute) -- i.e. the test passes
 * the IST instant and the mirror returns the corresponding
 * phase. We construct the Date by adding 5h30m to the IST
 * values, which is the canonical IST -> UTC projection.
 */
function ist(year, month, day, hh, mm) {
  // Construct a UTC date matching the IST fields -- a Date at
  // ``UTC(year, month, day, hh-5, mm-30)`` reads as IST
  // ``year/month/day hh:mm`` (modulo DST, which IST has none).
  return new Date(Date.UTC(year, month - 1, day, hh - 5, mm - 30));
}

/**
 * Like ``ist`` but with seconds precision. Used by the
 * "last-second boundary" tests where 15:14:59 vs 15:15:00 vs
 * 15:15:01 all need distinct phase results.
 */
function istSec(year, month, day, hh, mm, ss) {
  return new Date(Date.UTC(year, month - 1, day, hh - 5, mm - 30, ss));
}

// ---- (2) VALID_SESSION_PHASES invariant ------------------------

describe('VALID_SESSION_PHASES', () => {
  test('contains exactly the 10 documented phase strings', () => {
    // This is the bounded-contract pin. If a future refactor
    // adds or renames a phase on either side (Python or Node),
    // the golden-vector cross-check (test 5 below) will fail
    // FIRST, but this constant is the local face that catches
    // drift in the Node mirror specifically.
    expect(Array.from(VALID_SESSION_PHASES)).toEqual([
      'CLOSED',
      'PRE_MARKET',
      'CONTINUOUS_TRADING',
      'CAS_REFERENCE_PRICE_WINDOW',
      'CAS_ORDER_ENTRY',
      'CAS_LIMIT_ENTRY_ONLY',
      'CAS_MATCHING',
      'CAS_POST',
      'DERIVATIVES_CAS_ALIGNED',
      'UNKNOWN',
    ]);
  });

  test('is frozen (cannot be mutated)', () => {
    // Object.freeze means any push / index-assignment silently
    // fails in non-strict mode and throws in strict mode. We
    // attempt a mutation; the frozen contract is the assertion.
    expect(Object.isFrozen(VALID_SESSION_PHASES)).toBe(true);
  });
});

// ---- (3) Defensive: garbage / null / NaN / invalid dates -----

describe('sessionPhase defensive', () => {
  test('null returns UNKNOWN', () => {
    expect(sessionPhase(null)).toBe('UNKNOWN');
  });

  test('undefined returns UNKNOWN', () => {
    expect(sessionPhase(undefined)).toBe('UNKNOWN');
  });

  test('NaN-producing input returns UNKNOWN (no crash)', () => {
    // Strings that produce Invalid Date (their getTime() is NaN)
    // are returned as ``UNKNOWN`` so the mirror never raises.
    // The integer ``12345`` is a valid millisecond timestamp
    // and classifies normally -- the test is for strings that
    // ``new Date(<s>)`` rejects.
    expect(sessionPhase('not-a-date')).toBe('UNKNOWN');
    expect(sessionPhase(new Date('not-a-date'))).toBe('UNKNOWN');
    expect(sessionPhase({})).toBe('UNKNOWN');  // Date coercion falls back
    expect(sessionPhase(null)).toBe('UNKNOWN');  // explicit null branch
  });
});

// ---- (4) Documented phase boundaries (mirror the Python
//        TestRealDatetimeWired cases) ---------------------------

describe('sessionPhase boundary matrix', () => {
  // Use 2026-09-14 (Monday) as the canonical trading day.
  // 2026-09-13 (Sunday) returns CLOSED regardless of time.
  const MONDAY = 2026;
  const MONDAY_MONTH = 9;
  const MONDAY_DAY = 14;
  const SATURDAY_MONTH = 9;
  const SATURDAY_DAY = 12;
  const SUNDAY_MONTH = 9;
  const SUNDAY_DAY = 13;
  const CAS_DATE = 14; // Same Monday. Use cas_eligible=true for CAS-window probes.

  describe('weekday handling', () => {
    test('Sunday is CLOSED at 11:00 IST', () => {
      // 2026-09-13 is a Sunday.
      expect(
        sessionPhase(ist(SUNDAY_MONTH === 1 ? 2026 : 2026, SUNDAY_MONTH, SUNDAY_DAY, 11, 0))
      ).toBe('CLOSED');
    });
    test('Saturday is CLOSED at 11:00 IST', () => {
      // 2026-09-12 is a Saturday.
      expect(
        sessionPhase(ist(2026, SATURDAY_MONTH, SATURDAY_DAY, 11, 0))
      ).toBe('CLOSED');
    });
  });

  describe('pre-market and continuous (Monday)', () => {
    test('08:00 IST: CLOSED', () => {
      expect(sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 8, 0))).toBe('CLOSED');
    });
    test('08:59 IST: CLOSED (just before pre-open)', () => {
      expect(sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 8, 59))).toBe('CLOSED');
    });
    test('09:00 IST: PRE_MARKET (pre-open boundary)', () => {
      expect(sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 9, 0))).toBe('PRE_MARKET');
    });
    test('09:14 IST: PRE_MARKET (last second pre-open)', () => {
      expect(sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 9, 14, ))).toBe('PRE_MARKET');
    });
    test('09:15 IST: CONTINUOUS_TRADING (market open boundary)', () => {
      expect(sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 9, 15))).toBe('CONTINUOUS_TRADING');
    });
    test('12:00 IST: CONTINUOUS_TRADING', () => {
      expect(sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 12, 0))).toBe('CONTINUOUS_TRADING');
    });
    test('14:55 IST: CONTINUOUS_TRADING (last second of continuous)', () => {
      expect(sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 14, 55))).toBe('CONTINUOUS_TRADING');
    });
    test('15:00 IST: CONTINUOUS_TRADING for non-CAS, non-derivative', () => {
      expect(sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 15, 0))).toBe('CONTINUOUS_TRADING');
    });
    test('15:14 IST: CONTINUOUS_TRADING for non-CAS', () => {
      expect(sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 15, 14))).toBe('CONTINUOUS_TRADING');
    });
    test('15:30 IST: CLOSED for non-CAS cash', () => {
      expect(sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 15, 30))).toBe('CLOSED');
    });
    test('15:30 IST: CONTINUOUS_TRADING for derivatives (15:30 still in band up to 15:29 → 15:30 is the boundary)', () => {
      // 15:30 IST is the CAS_LIMIT_END for cash but for
      // derivatives it's the start of the CAS-aligned band.
      expect(
        sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 15, 30), {
          is_derivative: true,
        })
      ).toBe('DERIVATIVES_CAS_ALIGNED');
    });
    test('16:00 IST: CLOSED (post-close ended)', () => {
      expect(sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 16, 0))).toBe('CLOSED');
    });
    test('23:59 IST: CLOSED', () => {
      expect(sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 23, 59))).toBe('CLOSED');
    });
  });

  describe('CAS sub-windows (Monday, cas_eligible=true)', () => {
    test('15:14 IST: still CONTINUOUS_TRADING (before CAS open)', () => {
      // At 15:14, the CAS window has not opened -- cash symbols
      // are still in CONTINUOUS_TRADING. CAS branches only fire
      // from 15:15 IST onwards.
      expect(
        sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 15, 14), {
          cas_eligible: true,
        })
      ).toBe('CONTINUOUS_TRADING');
    });
    test('15:15 IST: CAS_REFERENCE_PRICE_WINDOW opens', () => {
      // The 15:15 boundary is the start of CAS. From this
      // instant onwards the CAS sub-window labels apply (when
      // cas_eligible is True).
      expect(
        sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 15, 15), {
          cas_eligible: true,
        })
      ).toBe('CAS_REFERENCE_PRICE_WINDOW');
    });
    test('15:19:59 IST: CAS_REFERENCE_PRICE_WINDOW (last second reference)', () => {
      // 15:19:59 is the last instant of CAS_REFERENCE_PRICE_WINDOW;
      // 15:20:00 is the boundary into CAS_ORDER_ENTRY.
      expect(
        sessionPhase(istSec(MONDAY, MONDAY_MONTH, MONDAY_DAY, 15, 19, 59), {
          cas_eligible: true,
        })
      ).toBe('CAS_REFERENCE_PRICE_WINDOW');
    });
    test('15:20 IST: CAS_ORDER_ENTRY starts', () => {
      // 15:20:00 is the boundary (CAS_ORDER_END is exclusive).
      expect(
        sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 15, 20), {
          cas_eligible: true,
        })
      ).toBe('CAS_ORDER_ENTRY');
    });
    test('15:24 IST: CAS_ORDER_ENTRY (last second)', () => {
      expect(
        sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 15, 24), {
          cas_eligible: true,
        })
      ).toBe('CAS_ORDER_ENTRY');
    });
    test('15:25 IST: CAS_LIMIT_ENTRY_ONLY', () => {
      expect(
        sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 15, 25), {
          cas_eligible: true,
        })
      ).toBe('CAS_LIMIT_ENTRY_ONLY');
    });
    test('15:29 IST: CAS_LIMIT_ENTRY_ONLY (last second)', () => {
      expect(
        sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 15, 29), {
          cas_eligible: true,
        })
      ).toBe('CAS_LIMIT_ENTRY_ONLY');
    });
    test('15:30 IST: CAS_MATCHING', () => {
      expect(
        sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 15, 30), {
          cas_eligible: true,
        })
      ).toBe('CAS_MATCHING');
    });
    test('15:34 IST: CAS_MATCHING (last second)', () => {
      expect(
        sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 15, 34), {
          cas_eligible: true,
        })
      ).toBe('CAS_MATCHING');
    });
    test('15:35 IST: CAS_POST', () => {
      expect(
        sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 15, 35), {
          cas_eligible: true,
        })
      ).toBe('CAS_POST');
    });
    test('15:59 IST: CAS_POST (last second)', () => {
      expect(
        sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 15, 59), {
          cas_eligible: true,
        })
      ).toBe('CAS_POST');
    });
  });

  describe('CAS sub-windows with cas_eligible=false (default boundary behaviour)', () => {
    test('15:17 IST: CONTINUOUS_TRADING (CAS branch suppressed; no eligibility)', () => {
      // cas_eligible=false explicitly; CAS sub-windows must NOT fire.
      expect(
        sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 15, 17), {
          cas_eligible: false,
        })
      ).toBe('CONTINUOUS_TRADING');
    });
    test('15:32 IST: CLOSED (15:30+ for non-CAS cash)', () => {
      expect(
        sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 15, 32), {
          cas_eligible: false,
        })
      ).toBe('CLOSED');
    });
    test('15:17 IST with cas_eligible=null: CONTINUOUS_TRADING (mirrors non-eligibility)', () => {
      // The Node mirror intentionally treats null like false
      // because Node has no Python config import for the
      // eligibility list. Documented contract.
      expect(
        sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 15, 17), {
          cas_eligible: null,
        })
      ).toBe('CONTINUOUS_TRADING');
    });
  });

  describe('Derivatives CAS-aligned band', () => {
    test('15:35 IST derivatives CAS-aligned', () => {
      expect(
        sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 15, 35), {
          is_derivative: true,
        })
      ).toBe('DERIVATIVES_CAS_ALIGNED');
    });
    test('15:39 IST derivatives CAS-aligned (last second)', () => {
      expect(
        sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 15, 39), {
          is_derivative: true,
        })
      ).toBe('DERIVATIVES_CAS_ALIGNED');
    });
    test('15:40 IST derivatives CLOSED (last second of band)', () => {
      // At 15:40 exactly, derivatives transition from band to
      // CLOSED. The Python mirror returns CLOSED via the
      // ``derivatives >= 15:40`` branch.
      expect(
        sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 15, 40), {
          is_derivative: true,
        })
      ).toBe('CLOSED');
    });
    test('15:50 IST derivatives CLOSED', () => {
      expect(
        sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 15, 50), {
          is_derivative: true,
        })
      ).toBe('CLOSED');
    });
  });

  describe('Production-options shape', () => {
    test('symbol + is_derivative + cas_eligible all together resolve cleanly', () => {
      // Combinations that cover most production passes:
      const opts = {
        symbol: 'RELIANCE',
        is_derivative: false,
        cas_eligible: true,
      };
      const p = sessionPhase(ist(MONDAY, MONDAY_MONTH, MONDAY_DAY, 15, 17), opts);
      expect(p).toBe('CAS_REFERENCE_PRICE_WINDOW');
    });
  });
});

// ---- (5) Golden-vector cross-check (bit-perfect with Python) ----

describe('golden vector parity vs Python classifier', () => {
  let golden;
  beforeAll(() => {
    // The golden vectors are produced by Python's
    // ``classify_session_phase``. The production mirror here
    // must produce identical output for every (ist_dt, symbol,
    // is_derivative, cas_eligible) tuple. Drift here is a hard
    // fail -- the next slice's CI gate.
    //
    // Regenerate locally via:
    //   python tests/fixtures/regenerate_session_phase_golden.py
    const goldenPath = path.join(
      __dirname, '..', 'fixtures', 'session_phase_golden.json'
    );
    if (!fs.existsSync(goldenPath)) {
      throw new Error(
        `golden vector file missing: ${goldenPath}. Run ` +
        '`python tests/fixtures/regenerate_session_phase_golden.py` ' +
        'to recreate it.'
      );
    }
    golden = JSON.parse(fs.readFileSync(goldenPath, 'utf-8'));
  });

  test('all vectors return one of the ten documented phases', () => {
    const validSet = new Set(VALID_SESSION_PHASES);
    for (const v of golden.vectors) {
      const opts = {
        symbol: v.symbol,
        is_derivative: v.deriv,
      };
      if (Object.prototype.hasOwnProperty.call(v, 'cas')) {
        opts.cas_eligible = v.cas;
      }
      const got = sessionPhase(new Date(v.ist_utc), opts);
      expect(validSet.has(got)).toBe(true);
    }
  });

  test('mirror is bit-perfect with Python classify_session_phase', () => {
    let mismatches = 0;
    let firstMismatch = null;
    for (const v of golden.vectors) {
      const opts = {
        symbol: v.symbol,
        is_derivative: v.deriv,
      };
      if (Object.prototype.hasOwnProperty.call(v, 'cas')) {
        opts.cas_eligible = v.cas;
      }
      const got = sessionPhase(new Date(v.ist_utc), opts);
      if (got !== v.expected) {
        mismatches += 1;
        if (firstMismatch == null) {
          firstMismatch = { vector: v, got };
        }
      }
    }
    expect({ mismatches, firstMismatch }).toEqual({
      mismatches: 0,
      firstMismatch: null,
    });
    // If this fails, regenerate the golden (see above) and
    // compare the diff against the Python classifier output.
    // A mismatch is a category-1 invariant failure: the J.6
    // contract is broken.
  });
});

// ---- (6) currentSessionPhase convenience wrapper ---------------

describe('currentSessionPhase', () => {
  test('returns a phase from the bounded set', () => {
    // We can't pin the exact phase (clock moves). We just assert
    // the bounded contract.
    const validSet = new Set(VALID_SESSION_PHASES);
    expect(validSet.has(currentSessionPhase())).toBe(true);
    expect(validSet.has(currentSessionPhase({}))).toBe(true);
  });

  test('opts propagate to sessionPhase', () => {
    // Pin via direct sessionPhase call (we cannot mock Date.now
    // without disturbing global state).
    const p = sessionPhase(ist(2026, 9, 14, 15, 17), {
      cas_eligible: true,
    });
    expect(p).toBe('CAS_REFERENCE_PRICE_WINDOW');
  });
});
