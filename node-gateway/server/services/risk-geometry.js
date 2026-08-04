/**
 * [FILL-ANCHOR 2026-08-04] Re-anchor a signal's risk geometry to the price we
 * can actually transact at.
 *
 * WHY THIS EXISTS
 * ---------------
 * The engine computes stop_loss and target_1 from the CLOSE of the breakout
 * candle. Between that close and the fill there is a queue:
 *
 *     15-min bar closes -> engine scan -> agent poll (<=15 min) -> Telegram ->
 *     human presses EXEC -> LTP drift check -> LIMIT order -> fill
 *
 * On 2026-08-03 that queue was 12 minutes wide for SUMICHEM. The signal said
 * close 512.00 / stop 509.20 (a 0.55% stop, 2.80/share of risk). The fill came
 * in at 510.10 -- and the protective SL was still armed at the signal's 509.20.
 * Live risk-per-share was therefore 0.90, not 2.80: 0.18% of price, well inside
 * the spread.
 *
 * That single substitution corrupts everything downstream, because R is the
 * unit the whole system reasons in:
 *
 *   - position sizing already divided the risk budget by the SIGNAL's
 *     risk-per-share, so the rupee risk on the book no longer matches the budget;
 *   - momentum_exits ratchets the stop to breakeven at MOMENTUM_BREAKEVEN_R, so
 *     a 0.90 R meant SUMICHEM read "+1.0R" after a 0.18% wiggle, ratcheted to
 *     cost-adjusted breakeven 510.71, and was clipped at 510.70 thirteen minutes
 *     after entry. It printed 517.70 at 12:00; target_1 was 517.60.
 *   - every r_multiple written to trade_outcomes measures a denominator that
 *     was never the real risk, so the strategy cannot be evaluated at all.
 *
 * THE RULE
 * --------
 * Risk DISTANCE is the invariant, not the stop PRICE. The engine sized the
 * position against a rupee-per-share risk; we preserve that distance and slide
 * the whole geometry (stop, targets) to sit around the price we actually get.
 * Floors are re-checked against the transaction price, because a 1.2% floor
 * computed on a stale close is not a 1.2% floor on the fill.
 *
 * Two call sites, deliberately:
 *   1. resolveRiskDistance() at the LTP drift check, BEFORE the buy -- so if a
 *      floor widens the risk we can still cut share count and stay inside the
 *      risk budget.
 *   2. anchorLevels() after the fill -- shares are committed by then, so the
 *      distance from step 1 is reused verbatim and only re-centred on the fill.
 */

/**
 * The rupee-per-share risk this trade should carry.
 *
 * Takes the widest of: the distance the engine intended, a percentage floor on
 * the transaction price, and an ATR-proportional floor. Widest wins for the
 * same reason the engine's own stop does `min(candle_low, floor_stop)` -- a
 * stop inside the noise is not a stop, it is a coin flip that also inflates
 * share count (sizing divides by this number).
 *
 * @param {object}  a
 * @param {number}  a.signalClose     close the engine priced the signal off
 * @param {number}  a.signalStop      stop the engine derived from that close
 * @param {number}  a.price           price we can transact at (LTP, then fill)
 * @param {number}  a.minStopPct      fractional floor, e.g. 0.012 for 1.2%
 * @param {number} [a.minStopAtrMult] ATR floor multiplier, e.g. 0.35
 * @param {number} [a.atr]            daily ATR at entry; ignored when falsy
 * @returns {{risk: number, source: string, intendedRisk: number}}
 */
function resolveRiskDistance({
  signalClose,
  signalStop,
  price,
  minStopPct,
  minStopAtrMult = 0,
  atr = null,
}) {
  if (!(signalClose > 0) || !(price > 0)) {
    throw new RangeError(`resolveRiskDistance: non-positive price (close=${signalClose}, price=${price})`);
  }
  const intendedRisk = signalClose - signalStop;
  if (!(intendedRisk > 0)) {
    // A stop at or above the close means the signal was malformed. Sizing
    // divided by this, so refuse rather than invent a number.
    throw new RangeError(`resolveRiskDistance: stop ${signalStop} is not below close ${signalClose}`);
  }

  const pctFloor = price * minStopPct;
  const atrFloor = atr > 0 ? atr * minStopAtrMult : 0;

  let risk = intendedRisk;
  let source = 'signal';
  if (pctFloor > risk) { risk = pctFloor; source = 'pct_floor'; }
  if (atrFloor > risk) { risk = atrFloor; source = 'atr_floor'; }

  return { risk, source, intendedRisk };
}

/**
 * Slide stop and targets so they sit the intended number of R away from the
 * price we actually transacted at.
 *
 * R-multiples are preserved rather than prices: target_1 was `close + k*R` for
 * some k the engine chose (the regime's R-target), so it becomes `price + k*R`.
 * Anchoring the TARGET to a stale close while the STOP moves would silently
 * change the reward:risk of every trade with the direction of the drift.
 *
 * @param {object} a
 * @param {number} a.price          fill price (or LTP pre-order)
 * @param {number} a.risk           rupee-per-share risk from resolveRiskDistance
 * @param {number} a.signalClose    close the R-multiples were measured from
 * @param {number} a.signalStop     stop the R-multiples were measured from
 * @param {number} a.signalTarget1
 * @param {number} [a.signalTarget2]
 * @returns {{stop: number, target1: number, target2: number, rTarget1: number}}
 */
function anchorLevels({ price, risk, signalClose, signalStop, signalTarget1, signalTarget2 }) {
  const intendedRisk = signalClose - signalStop;
  if (!(intendedRisk > 0)) {
    throw new RangeError(`anchorLevels: stop ${signalStop} is not below close ${signalClose}`);
  }
  if (!(risk > 0)) {
    throw new RangeError(`anchorLevels: non-positive risk ${risk}`);
  }

  const rTarget1 = (signalTarget1 - signalClose) / intendedRisk;
  // Momentum ships a single target (target_2 === target_1). Preserve whatever
  // separation the signal had rather than assuming they are equal.
  const rTarget2 = signalTarget2 != null
    ? (signalTarget2 - signalClose) / intendedRisk
    : rTarget1;

  return {
    stop:    round2(price - risk),
    target1: round2(price + rTarget1 * risk),
    target2: round2(price + rTarget2 * risk),
    rTarget1,
  };
}

/**
 * Largest share count that keeps rupee risk inside the budget the engine
 * approved. Only ever shrinks -- a favourable fill is not licence to add size
 * the risk model never sanctioned.
 */
function sizeToRisk({ originalShares, capitalAtRisk, risk }) {
  if (!(risk > 0)) throw new RangeError(`sizeToRisk: non-positive risk ${risk}`);
  const affordable = Math.floor(capitalAtRisk / risk);
  return Math.max(0, Math.min(originalShares, affordable));
}

function round2(x) {
  return Math.round(x * 100) / 100;
}

module.exports = { resolveRiskDistance, anchorLevels, sizeToRisk, round2 };
