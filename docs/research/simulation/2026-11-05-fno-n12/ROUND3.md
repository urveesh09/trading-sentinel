# Round 3 freeze

The exact 2022 controls still lost after replacing daily index prices. Price waiting lost roughly ₹32,420 in 2024 and the protection exit failed in 2023. Move the next test to a different layer. The old fixed-delta tests did not transfer across years, so a new contract must earn its place against the actual native contract at that moment.

CHAIN_FALLBACK may rescue a native strike rejection caused by liquidity, affordability or payoff economics, once. Consider at most two actual adjacent contracts within 100 points in the same series and same option direction. Keep the same moneyness, expiry, risk, occupancy, price, freshness and re-entry rules. The absolute delta band is 0.43–0.67. Admit only one lot, and only if the stressed target reward is at least ₹250 and at least 1.3 times modeled stop loss. No fallback on repeated positions, risk halts, calendar, expiry or regime.

STRIKE_DOMINANCE considers the same adjacent strikes when the original would enter. A replacement must have the same quantity, no more premium paid, no more estimated loss at the same stop and at least ₹250 extra modeled reward per lot at the same target. Use Black-76 at 45 minutes elapsed, the observed strike's current IV less 1.5 percentage points, half the visible spread and full model charges. Those prices rank candidate economics and never become fills. The selected strike re-enters the exact planner and uses observed modeled asks and bids as all the other arms do.

Keep exact N11/N11T controls and sealed yearly inputs. Publish all outcomes and paid-for opportunity changes before combining variants.
