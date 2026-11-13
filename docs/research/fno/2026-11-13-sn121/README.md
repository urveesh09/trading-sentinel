# SN121–SN130: gap days freed from Gold's rules, and what the partner teaches (Nov 13, 2026)

## What the owner asked

"rather just sitting and doing nothing ... try something else ... my partner ... is around ₹6–7,000 in profit on ₹25,000 at some moment ... human greed and FOMO ... if they can do it, why can the system not ... You have autonomy ... change all the rules for the gap days."

## How it was tested

- **Frozen** at `cecf2f8a` (`PLAN.md`) before any scoring. One pre-freeze change: the condor's wings moved to ±50/±250 after a coverage check (±300 printed on only 174 of 541 nights).
- **Gap-day rules relaxed** as allowed:
  - holding to 15:25;
  - overnight defined-risk selling;
  - many trades a day;
  - a ₹25k partner-sized wallet;
  - profit locks.
- **Truth-testing unchanged:** frozen rules, strict costs, held-out years, random controls.
- **Partner data:** the frozen Nov 4 Production extract (237 round trips, 7 sessions), hash-checked, marked with real archived quotes.
  - Per the standing rule, **no partner rupee totals appear anywhere**: shapes, shares, ratios and per-lot averages only.

## The honest one-line answer

A machine cannot copy the partner's profitable *moments*.
- Being up ₹5k+ at some point is a feature of the path, not of predictable profit.
- Every rule that trades actively on gap days loses roughly its costs (₹290–340 per lot per 15-minute trade).
- What the partner *can* use is the one thing their data clearly shows: they give the peak back by over-trading after it. A give-back stop would have cut their loss on these 7 days by about 70%.

That is a coaching message, not a trading strategy.

## Results

| SN | Question | Result | Verdict |
|---|---|---|---|
| 121 | The partner's day paths (7 sessions, 237 trips, 37 a day median) | A positive peak on 6 of 7 days, **≥ +20% of ₹25k on 5 of 7** (your ₹6–7k is real); only **3 of 7 ended green**; median **22 trips taken after the day's peak**. On their own sequence, against an actual loss over the 7 days: a +20% lock cuts the loss by 37%, **stopping once a ≥ +5% peak has fallen back 30% cuts it by 71%** (50%: 67%) | Description (7 days, seen) |
| 122 | Do their entries and exits carry skill? (real quotes, 230 trips) | **Entries: yes, for one minute.** The option rises **+1.51%** in the first minute vs +0.12% for random times in the same contract (**p = 0.0015**). By 5 minutes the edge is gone (p = 0.42; 15 min p = 0.09). **Exits: well timed** (the option falls 2.5% in the minute after they sell). Machine exits on their entries are worse: their own −₹126 per lot, a 10-minute hold −₹221, a 20% trail −₹358 (real quotes, ₹205 stress) | Their trips are near break-even *before* our stress; costs × 37 trips and post-peak trading do the damage |
| 123 | A partner-like machine scalper (4 years, Gold-free days, ₹25k, 2 lots) | Burst entries: 6 trades a day, **−₹2,950 a day** (strict), touches +₹6k on 1% of days. Random entries: 16 a day, −₹8,295 a day. Both lose even at zero slippage (−₹578 / −₹2,018 a day). Profit locks only shrink losses (best held out −₹9.07 lakh vs random −₹14.40 lakh) | NOT PROVEN: our minute rules do not have the partner's 1-minute read |
| 124 | Overnight option selling (Muravyev & Ni), defined risk | The effect exists (implied volatility −1.6% overnight; a long straddle overnight loses ₹890 a night), but **selling a fly / condor overnight loses ₹850–1,040 a night** strict (₹430–620 at house costs): 4 legs of costs swamp a 2–3 point edge. Held out −₹2.72 lakh | NOT PROVEN |
| 125 | The last half-hour, holding to 15:25 (first half-hour, 14:30–15:00, gap, both agree) | Held out **−₹1,10,959** (all 4 years negative), worse than a random side's 95th percentile | NOT PROVEN |
| 126 | Active scalping only on hot days (movement underpriced) | Big bursts (2.5 ATR, 15-minute hold): **+₹4,414** held out on 35 trades, 3 of 4 years positive, beats a random side (−₹14,137), 1 minute late +₹1,401, but **−₹2,362 at ₹400** stress. The same rule on cold days: −₹11,852 | NOT PROVEN, a lead: forward watch SN126-L |
| 127 | When is buying an option least bad? | A 15-minute ATM buy costs **₹285–340 per lot at every clock** (the friction). Even perfect hindsight direction makes only ₹200–600 per lot per 15 minutes, the most at 09:20 | Map for the coach |
| 128 | Selling the morning implied-volatility crush (no overnight risk) | −₹1,100 a trade strict, the same as selling at midday (no morning effect after costs) | NOT PROVEN |
| 129 | The sleeve of survivors beside Gold | **Nothing passed, so the sleeve is not formed.** As a description, running every candidate on every gap day loses **₹17.6 lakh** in four years. With ₹55k total, Gold ₹55k alone makes **₹16.16 lakh** (growing, stop 3) | Do not trade every day |
| 130 | Synthesis | Below | – |

## SN130 — why humans sometimes win, and what a machine can copy

**What the research says**
1. **Most active derivatives traders lose, and keep trading.**
   - [SEBI's FY22–24 study](https://www.outlookmoney.com/invest/93-of-individual-traders-suffered-losses-in-fo-in-last-3-years-sebi-study): **93%** of individual F&O traders lost money, and over 75% of loss-makers kept trading after two losing years.
   - [FY26](https://openthemagazine.com/business/sebi-fo-loss-study-explained-why-9-in-10-retail-traders-lost-91685-crore-in-fy26): 87.7% lost.
   - Only about 1% earn over ₹1 lakh after costs; options are 92% of the losses.
2. **A few are genuinely skilled, and they are rare.**
   - In Taiwan's complete day-trading records, fewer than 1% of day traders earn reliably positive returns after costs.
   - They are identifiable ahead of time from the prior year ([Barber, Lee, Liu & Odean](https://faculty.haas.berkeley.edu/odean/papers/day%20traders/Day%20Trading%20Skill%20110523.pdf)).
3. **Overnight vs intraday option pricing.**
   - The overnight overpricing of options is real ([Muravyev & Ni, JFE 2020](https://ideas.repec.org/a/eee/jfinec/v136y2020i1p219-238.html)). Their own numbers are gross of costs, and SN124 confirms that for NIFTY the costs swamp it.
   - [Intraday momentum](https://alphaarchitect.com/2014/08/attention-prop-traders-the-first-half-hour-of-trading-predicts-the-last-half-hour/) (US, 12 of 16 markets) does not survive option costs on NIFTY (SN125).

**What the partner's data says**
- The partner is not unskilled:
  - their entries catch the next minute (p = 0.0015) and their exits dodge the next drop;
  - per trip they are near break-even before slippage.
- Three habits turn that into losses:
  1. **too many round trips** (37 a day), each paying ~₹300 per lot of friction (SN127);
  2. **continuing after the day's peak** (a median of 22 more trips);
  3. **holding past the edge** (their edge lasts ~1 minute; median hold 10).
- "Being up ₹6–7k at some moment" happens to almost any active option buyer on a volatile path. On its own it does not show a profit that can be kept.

**What the machine can copy, and what it cannot**
- *Cannot:* the partner's 1-minute read of the tape. Minute-bar rules (SN123) lose. Whatever they see is faster than our data and is not in the price series we hold.
- *Can:* the discipline the partner lacks. For the partner coach (messages only, the owner's call), these are frozen here as forward-watch proposals, not deployed:
  1. **Give-back alert:** once the day's marked P&L has been ≥ +5% of their usual capital and falls 30% from its peak, send "you have given back 30% of today's best; consider stopping". On the 7 sessions this would have cut the loss by ~71%.
  2. **Friction counter:** the day's round trips with their estimated cost (~₹300 per lot each, SN127).
  3. **Edge clock:** a note that the advantage of their entries fades after ~1–5 minutes (SN122).

  Score these on their next ≥ 20 sessions, partner days only, against the actual outcome.

## Forward watches (frozen; no module, no money)

- **SN95-L** (unchanged).
- **SN126-L:**
  - **Days:** Gold-free days with R_today in the causal top 20% at 10:00.
  - **Entry:** 10:00–15:00, a fresh 3-minute move ≥ 2.5 × the 1-minute ATR × √3; buy the ATM option in its direction.
  - **Exit:** a 2-ATR index stop or 15 minutes, 25% backstop; at most 5 trades a day.
  - **Pass:** ≥ 20 trades after Nov 13, 2026, net > 0 at ₹205 *and* at ₹400.

Both are hot-day rules, the only days on which buying has shown an edge (SN101, SN111, SN126).
