# Round 7. A bullish intraday condition inside a quiet daily regime

The increased premium cap changed exposure but did not create a better strategy. Inspect missed directional opportunities during otherwise idle time. The earlier unfiltered low-day calls and broad daily trend alignment lost money. Instead use a time-local bullish acceptance condition and ask two separate questions. The low-ADX member already tests a pullback. The acceptance gate tests the market in which it occurs.

The opening six closed five-minute bars must move up by at least 70% of their range, which must be at least 90% of the median of the previous 15 complete regular openings of the same futures contract. Require at least ten such earlier sessions. On the decision bar, each of the last two completed closes must remain in the top quarter of the opening range or above it, and above the previous observed session's final full close. Use it between 09:55 and 11:45. Require complete local clocks. No spot/futures symbol stitching.

- ACCEPT_CALL admits the existing TPB call only when the ordinary N11T route would refuse that low-day direction, the book is flat, the acceptance gate holds, and all native risk, stand-aside, stretch and contract checks pass. At most one such call per day, one lot. Existing shorts remain eligible.
- ACCEPT_NO_PUT withholds the ordinary low-day TPB put during the same bullish acceptance gate. It leaves all other members and clocks intact.

The two arms separate the value of adding a new call from cutting a put. Neither tests whether all calls or all puts are worthwhile. Both share the ₹250,000 paper wallet. Keep all five windows in the development set.
