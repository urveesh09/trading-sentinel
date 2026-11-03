# Same direction, opposite-side protected credit

Written before any credit score. Ledger round f34ceb9 reproduces the baseline;
both new ledgers equal ordinary/adverse E03.1, and NET worsens severe. Gross
turnover/two entries are not binding on this sample; not a new income source.

## Two primary arms

When E03.1's unchanged completed-bar trend-pullback signal is up, sell the first
OTM put and buy the next put 50 points lower; reverse to calls on a down signal.
One 65-unit pack only. Both strikes <=200 points from current spot. No need for
the long-lottery 5-20 price band: this changes the payoff, not entry direction.

- **CREDIT_8M**: manage until eight minutes after fill, or an earlier failed
  underlying thesis / premium stop / profit take, flat by 15:14.
- **CREDIT_TREND**: same, but no eight-minute clock; harvest until the thesis
  fails, premium stop/profit take or 15:14. No auction exposure is intended.

Fixed take: closing cost <=half initial credit. Fixed stop: closing cost >=2x
credit, or index breaches the original 2-ATR thesis stop. Next executable bar
fills; a trigger is not its fill. Flat at 15:14, chosen to precede the later
2026 auction regime; 2024/2025 are still legacy seen years. Entries 13:00-15:00,
two sequential packs/day, five-minute cooldown, same absolute cash brakes.

## Cash, fills and missing assets

Fresh independent 25,000 cash book; user broadened research risk. Full-width
cash collateral plus buffer must fit cash: 51 points*65 + entry fees +500.
The extra point is a declared liquidation limit allowance, not a fabricated
price. Initial debit paid for the hedge also fits cash before short receipts.
Risk reserve per pack is (51-credit)*65 +entry fees+500; daily original reserve
<=5,000, scaled by the existing 1,500/3,000/4,000 drawdown brakes. No larger size,
naked short, margin borrowing, profits refill or hidden wider cover.

Entry is a hypothetical simultaneous two-leg basket; inherited ordinary,
adverse/severe per-leg prices, 20% volume capacity and fees. Require positive
credit below width and enough gross credit to cover entry plus two exit-order
fees. Limit credit deterioration to 10% of decision credit. Refuse unfillable
legs; never clamp a zero/negative bid to a positive price. Historical broker
SPAN/ELM and atomic execution are unavailable: cash coverage is a model, **not
proof that a broker would accept the margin**. No live qualification follows.

Exit buys back the short first in the model. If both legs are executable they
close together. If the purchased hedge cannot be sold, it may remain as a
fully paid **long-only residual asset**, recorded with a conservative zero
lower-bound mark; there is no invented sell/settlement. That lowers the cash
return and excludes any later positive settlement. Report assumed hedge writeoff
apart from filled-fee realized PnL, residual inventory/counts and positive value
unknown. Do not claim the account is flat. No future short liability remains
when this continuation is allowed. Exercise taxes assumed payable from future
positive long proceeds only; no positive exercise/settlement credited.

If the short cannot close, the book STOPS and all following dates are unavailable.
Never write off an open short liability and free the book. A fee-inclusive close
above the pre-reserved worst-case loss is not filled; keep the liability pending.
No clipping an expensive fill to theoretical width. Any unresolved short fails
the strategy. All long residuals and lower-bound assumptions remain PARTIAL.

## Assessment

Shared PLAN.md seen-year positive/improvement/ex-best/drawdown checks. Compare
each year's net lower-bound cash, continuous cash, fees, win/loss distributions,
full risk, worst day, sampled marks and severe prices to E03.1. Margin and
execution qualification remain separately unavailable even if money looks good.
Fixed coarse robustness only after primary scores, no winning clock search.
Direction-reversed/random-side controls test whether trend information matters.
No native engine/settings/schema/Production/provider/download changes.
