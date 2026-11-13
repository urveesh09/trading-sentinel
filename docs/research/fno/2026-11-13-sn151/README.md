# SN151–SN160: the hot-day program — digging where the one gap-day edge lives (Nov 13, 2026)

**Owner:** "Go ahead even more ... if that fails learn from it, try something else ... some machine learning, some automated, something mixed."

- **Frozen** at `5f42b20e` (`PLAN.md`) before any scoring. Numbers are in `results-*.json`.
- **One post-score fix:** SN156 printed its results and then crashed writing the JSON (a number-format bug); it was rerun unchanged.
- **The edge being dug:** volatility persistence. When the morning moves more than its options price, it keeps moving, so the 10:00 straddle (SN95-L) beats matched random days (SN101, p = 0.002).

| SN | New angle | Result (held out, Gold-free days, strict ₹205 per leg) | Verdict |
|---|---|---|---|
| 151 | "Hot right now?" every 30 minutes, 10:00–13:00 | −₹46,028 (144 trades; 2026 +₹14,276); random 95th −₹63,883 | NOT PROVEN: later entries have too little day left to pay the premium |
| 152 | Yesterday hot → straddle today | **+₹4,008** (41 trades; random 95th +₹1,239), but 2 of 4 years, −₹43,426 without best 5, −₹13,182 at ₹400 | NOT PROVEN (a faint echo only) |
| 153 | Expiry-day hot straddle (0 days to expiry) | Score half −₹6,314 (6 trades); the pick won 1 of its 8 trades overall | NOT PROVEN: expiry-day decay eats the move |
| 154 | Learned probability "will today's straddle pay?" | −₹15,898 (36 trades) | NOT PROVEN |
| 155 | Rule + model must agree | Only 4 trades (−₹1,550) vs SN95-L alone +₹17,144 | The plain rule wins |
| 156 | Leg out of a winning straddle (+50% / +100%) | −₹10,044 / −₹13,947 vs holding both +₹17,144 | Hold both to the close |
| 157 | Partner-speed momentum on hot days (1-second) | B hot days −₹22,001 (83 trades), the same as a random side (−₹21,504); cold days −₹48,863 | NOT PROVEN |
| 158 | The hot-day book (SN95-L + SN126-L) as a ₹15k sleeve | **+₹19,794** in four years (51 trade days: 2023 −₹3,644, 2024 +₹17,832, 2025 −₹5,727, 2026 +₹11,333). The same ₹15k inside Gold: ₹13.21 lakh vs ₹8.71 lakh (growing, stop 3) | Real but small; capital earns far more in Gold |
| 159 | Bootstrap intervals (per trade day) | SN95-L +₹490 (95% interval −₹665 to +₹1,830); SN126-L +₹163 (−₹416 to +₹765); the book +₹388 (−₹431 to +₹1,301) | Not yet distinguishable from zero: hence forward watches, not money |
| 160 | Scoreboard | `results-sn160.json` | – |

## What SN151–SN160 teach

1. **The edge is precise.**
   - **Timing:** it is the 10:00 straddle, when most of the day is still ahead. Later or rolling entries, yesterday's heat and expiry days all dilute it.
   - **Management:** taking a leg off early, or letting a learned filter vote, removes the right tail that pays.
2. **Machine learning helps only where data are plentiful,** and hot days are rare (~45 in four years). On small samples the simple rule built on a known mechanism beats every model.
3. **Even the best gap-day book is worth ~₹20k over four years on ₹15k,** with intervals that include zero. On the same capital, Gold makes ~₹4.5 lakh more.
   - **For more profit:** the evidence-backed lever stays the money behind Gold (and its 50% growth trigger).
   - **For gap days:** run the hot-day book on paper (SN95-L + SN126-L) until ≥ 20 forward trades confirm it.
