# Round 1 freeze

The 2022 N11 controls were mostly low-ADX put pullbacks. Twenty low TPB entries lost ₹7,901.53, four EFF entries lost ₹4,785.12, and fourteen structural stops lost ₹23,281.72. A direct VWAP filter cannot solve the low-day cases because all were already on its favorable side. The earlier broad one-bar momentum confirmation missed more large winners than it saved in losses. Keep the same baseline controls and test distinct hypotheses on the largest 2022 weak spot.

PRICE_WAIT waits up to six minutes for a better futures price. For a put it requires a rebound of 20–40% of the original stop distance on a later scan observation. On a call the inequality mirrors it. A larger adverse move cancels. The original stop, target and signal identity are retained, entry is repriced by the normal planner, and the new observation must pass the current risk checks. One intent per original signal bar. No change to high-ADX entries.

PROTECT leaves admissions untouched. For a low-day TPB that gains 1R before the native trail arms, a later completed bar and current futures print must both have given it back to 0.1R or less. At that point a visible option exit basis may trigger a modeled early exit. Native hard flat, structural and premium stops, and already armed trails take priority. It uses no time-only stagnation threshold.

Compare both to N11 and N11T from 2022 through October 2026. Treat 2022 as a diagnostic seen window. Keep every loss and missed trade. No change to N11T parameters.
