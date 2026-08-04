const {
  resolveRiskDistance,
  anchorLevels,
  sizeToRisk,
} = require('../../services/risk-geometry');

// The 2026-08-03 trade this module exists to prevent. Numbers are the real ones
// from cache.db: signal at 11:02:58 off the 10:45 bar, EXEC pressed 11:14:43.
const SUMICHEM = {
  signalClose:   512.00,
  signalStop:    509.20,   // 0.547% -- the engine's 0.5% floor, applied to 512.00
  signalTarget1: 517.60,   // +2.0R from the signal close
  fillPrice:     510.10,   // 12 minutes and -0.37% later
  atr:           20.14,
  shares:        4,
  capitalAtRisk: 11.20,    // 4 x 2.80
};

describe('resolveRiskDistance()', () => {
  test('keeps the risk distance the engine sized against when no floor binds', () => {
    const { risk, source, intendedRisk } = resolveRiskDistance({
      signalClose: 100, signalStop: 98, price: 100, minStopPct: 0.005,
    });
    expect(intendedRisk).toBeCloseTo(2.0, 6);
    expect(risk).toBeCloseTo(2.0, 6);
    expect(source).toBe('signal');
  });

  test('widens to the percentage floor measured on the TRANSACTION price', () => {
    // Signal risk 0.5 on a 100.00 close; we transact at 200.00, where a 1.2%
    // floor is 2.40. The floor must follow the price, not the stale close.
    const { risk, source } = resolveRiskDistance({
      signalClose: 100, signalStop: 99.5, price: 200, minStopPct: 0.012,
    });
    expect(risk).toBeCloseTo(2.4, 6);
    expect(source).toBe('pct_floor');
  });

  test('widens to the ATR floor when that is the widest of the three', () => {
    const { risk, source } = resolveRiskDistance({
      signalClose: 100, signalStop: 99, price: 100,
      minStopPct: 0.005, minStopAtrMult: 0.35, atr: 10,
    });
    expect(risk).toBeCloseTo(3.5, 6);   // 0.35 * 10 beats both 1.00 and 0.50
    expect(source).toBe('atr_floor');
  });

  test('ignores the ATR floor when the signal carried no ATR', () => {
    const { risk, source } = resolveRiskDistance({
      signalClose: 100, signalStop: 98, price: 100,
      minStopPct: 0.005, minStopAtrMult: 0.35, atr: null,
    });
    expect(risk).toBeCloseTo(2.0, 6);
    expect(source).toBe('signal');
  });

  test('never narrows the risk below what the engine intended', () => {
    // A favourable fill must not shrink the stop into the noise either.
    const { risk } = resolveRiskDistance({
      signalClose: 512, signalStop: 509.2, price: 400, minStopPct: 0.005,
    });
    expect(risk).toBeCloseTo(2.8, 6);   // 0.5% of 400 = 2.00 < 2.80
  });

  test('refuses a malformed signal rather than inventing a denominator', () => {
    expect(() => resolveRiskDistance({
      signalClose: 100, signalStop: 100, price: 100, minStopPct: 0.005,
    })).toThrow(RangeError);
    expect(() => resolveRiskDistance({
      signalClose: 100, signalStop: 101, price: 100, minStopPct: 0.005,
    })).toThrow(RangeError);
  });
});

describe('anchorLevels()', () => {
  test('slides stop and target onto the fill, preserving the R multiple', () => {
    const { stop, target1, rTarget1 } = anchorLevels({
      price: 99, risk: 2, signalClose: 100, signalStop: 98,
      signalTarget1: 104, signalTarget2: 104,
    });
    expect(rTarget1).toBeCloseTo(2.0, 6);
    expect(stop).toBeCloseTo(97, 2);      // 99 - 2
    expect(target1).toBeCloseTo(103, 2);  // 99 + 2*2
  });

  test('an adverse fill moves the target UP so reward:risk is unchanged', () => {
    const { stop, target1 } = anchorLevels({
      price: 101, risk: 2, signalClose: 100, signalStop: 98,
      signalTarget1: 104, signalTarget2: 104,
    });
    expect(stop).toBeCloseTo(99, 2);
    expect(target1).toBeCloseTo(105, 2);
    // The trade still risks 2 to make 4 -- not 2 to make 3.
    expect((target1 - 101) / (101 - stop)).toBeCloseTo(2.0, 6);
  });

  test('preserves a separate target_2 rather than collapsing it onto target_1', () => {
    const { target1, target2 } = anchorLevels({
      price: 100, risk: 1, signalClose: 100, signalStop: 99,
      signalTarget1: 102, signalTarget2: 105,
    });
    expect(target1).toBeCloseTo(102, 2);
    expect(target2).toBeCloseTo(105, 2);
  });
});

describe('sizeToRisk()', () => {
  test('cuts share count when a floor widened the risk', () => {
    // Budget 100 rupees. Engine sized 50 shares at 2/share; the floor makes it 4.
    expect(sizeToRisk({ originalShares: 50, capitalAtRisk: 100, risk: 4 })).toBe(25);
  });

  test('never adds size on a favourable fill', () => {
    expect(sizeToRisk({ originalShares: 50, capitalAtRisk: 100, risk: 1 })).toBe(50);
  });

  test('returns 0 when even one share breaches the budget', () => {
    expect(sizeToRisk({ originalShares: 4, capitalAtRisk: 11.2, risk: 20 })).toBe(0);
  });
});

describe('regression: SUMICHEM 2026-08-03', () => {
  test('the old behaviour left only 0.90 of risk against a sized 2.80', () => {
    // Documents the bug: the stop that was actually armed vs the fill.
    const liveRisk = SUMICHEM.fillPrice - SUMICHEM.signalStop;
    expect(liveRisk).toBeCloseTo(0.90, 2);
    expect(liveRisk / SUMICHEM.fillPrice).toBeLessThan(0.002);  // 0.18% -- inside the spread
  });

  test('re-anchoring restores the full risk distance at the 0.5% floor', () => {
    const { risk } = resolveRiskDistance({
      signalClose: SUMICHEM.signalClose,
      signalStop:  SUMICHEM.signalStop,
      price:       SUMICHEM.fillPrice,
      minStopPct:  0.005,          // the floor that was live on 2026-08-03
      minStopAtrMult: 0,
    });
    const { stop, target1 } = anchorLevels({
      price: SUMICHEM.fillPrice, risk,
      signalClose:   SUMICHEM.signalClose,
      signalStop:    SUMICHEM.signalStop,
      signalTarget1: SUMICHEM.signalTarget1,
    });

    expect(risk).toBeCloseTo(2.80, 2);
    expect(stop).toBeCloseTo(507.30, 2);

    // The breakeven ratchet fires at +1R. Under the bug that was 511.00, which
    // the 11:15 bar (high 511.45) reached within a minute. Anchored, it is
    // 512.90 -- above the whole 11:15-11:45 chop, so the trade survives to noon.
    const ratchetTrigger = SUMICHEM.fillPrice + risk;
    expect(ratchetTrigger).toBeCloseTo(512.90, 2);
    expect(ratchetTrigger).toBeGreaterThan(511.45);

    // And the 12:00 bar (high 517.70) still clears the anchored target.
    expect(target1).toBeCloseTo(515.70, 2);
    expect(517.70).toBeGreaterThan(target1);
  });

  test('the 1.2% floor on dev widens the stop and cuts size to stay in budget', () => {
    const { risk, source } = resolveRiskDistance({
      signalClose: SUMICHEM.signalClose,
      signalStop:  SUMICHEM.signalStop,
      price:       SUMICHEM.fillPrice,
      minStopPct:  0.012,
      minStopAtrMult: 0.35,
      atr:         SUMICHEM.atr,
    });
    // 0.35 * 20.14 = 7.05 beats both 2.80 and 1.2% of 510.10 (6.12).
    expect(source).toBe('atr_floor');
    expect(risk).toBeCloseTo(7.05, 2);

    // 7.05/share against an 11.20 budget affords 1 share, not 4. Without this
    // the position would carry 28.20 of risk -- 2.5x the approved amount.
    expect(sizeToRisk({
      originalShares: SUMICHEM.shares,
      capitalAtRisk:  SUMICHEM.capitalAtRisk,
      risk,
    })).toBe(1);
  });
});
