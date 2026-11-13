# SN121–SN130: gap days, freed from Gold's rules (frozen plan, committed before any scoring, Nov 13, 2026)

## The owner's request

"rather just sitting and doing nothing ... try something else ... look at my partner, they make losses a lot, but they still actively trade every day. There is a certain moment of time when they are around ₹6–7,000 in profit on an investment of ₹25,000 ... human greed and FOMO ... if they can do it, why can the system not ... You have autonomy. You can change all the rules for the gap days."

## What changes, and what doesn't

**Gap-day rules the owner freed** (for these studies only):
- holding past 15:10 (to 15:25);
- overnight positions with defined risk (option selling with bought wings);
- many trades a day;
- other wallets (₹25k like the partner);
- profit locks.

**What does not change** (truth-testing, not trading rules):
- every rule fixed before scoring;
- costs (Zerodha charges + ₹205 per lot per trade / per leg-lot strict, ₹100 per leg-lot house, ₹400 reported);
- leave-one-year-out where four years exist;
- random controls;
- research only; nothing deployed.

**Margin** for short structures is the structure's maximum loss, a proxy that is not broker-verified.

## Partner data

The frozen read-only Production extract `docs/research/partner/2026-11-04-assistance-review/_local/production-selected.json`, checked against its manifest SHA-256 `59309f7c…`:
- 237 round trips, 7 sessions, Oct 27 – Nov 4 2026;
- marked to market with Production's quote archive (SHA-checked; strikes outside its window stay unpriced).

**Privacy:**
- per the standing rule, no partner rupee totals in any committed file or report;
- partner results are shapes, shares, counts and per-lot averages only;
- the extract stays in its git-ignored `_local/`.

## External evidence read before planning (SN130 cites it)

- **SEBI's F&O studies:**
  - about 9 in 10 individual traders lose (93% over FY22–24; 87.7% in FY26);
  - only ~1% earn over ₹1 lakh after costs.
- **Barber, Lee, Liu & Odean, Taiwan:** under 1% of day traders are predictably profitable.
- **Muravyev & Ni (JFE 2020):** index options lose ~1% a night delta-hedged and gain intraday, because prices ignore that overnight volatility is lower. Their figures are gross of costs.
- **Gao, Han, Li & Zhou:** the first half-hour return predicts the last half-hour (US; 12 of 16 markets in later work; no Indian study found).

## The ten studies

### SN121 — the partner's day paths (description)

For each session, the partner's minute-by-minute day P&L:
- realised at each trip's close;
- plus open trips marked at the archived mid when priced.

Then:
- **Describe:** when the day's peak came, the share of the peak given back by the close, and trips taken after the peak.
- **Counterfactuals on their own sequence:**
  - lock the day when its P&L first reaches +10% / +20% of a ₹25k notional;
  - or stop once a peak of ≥ +5% has fallen back by 30% / 50%.
- **Reported as:** days improved / worsened, and the sign and size of the change relative to the actual result.

### SN122 — do the partner's entries and exits carry skill? (real quotes)

- **Entries:** for every priced trip, the option mid's move 1 / 5 / 15 / 30 minutes after entry. Against 2,000 random entry minutes in the same contract that day (09:20–15:00), as a permutation p-value.
- **Exits:** the move after their exit, i.e. whether they left money or saved it.
- **Machine exits on their entries:** a fixed 10-minute hold, and a 20% premium trail. Per-lot executable net against their actual exits.

### SN123 — the "+₹6–7k moment" for a machine (4 years, Gold-free days, ₹25k, 2 lots)

- **Partner-like scalper, families:**
  - `random`: an entry chance every minute at a rate giving ~20 trades a day, random side;
  - `burst`: a fresh 3-minute index move ≥ 1.5 ATR × √3, in its direction.
- **Each trade:**
  - the ATM option;
  - exit at the first of a −15% premium stop, a +20% target, or a 5-minute clock;
  - from 09:20, last entry 15:00.
- **Report:**
  - the share of days whose running P&L touches +₹2k / +₹4k / +₹6k;
  - the share ending green;
  - the mean day.
- **Lock grid:** day target {₹1.5k, ₹3k, ₹6k} × day stop {₹2.5k, ₹5k}, chosen leave-one-year-out for `burst`, with the same procedure on `random` as the NULL.
- **Pass:** the companion rule of SN92 (held-out > 0, ≥ 3/4 years, beats NULL, robust).

### SN124 — overnight short volatility (Muravyev–Ni)

Every night where tonight's and the next session share the nearest weekly expiry (the next session is not that expiry), all days:
1. **Entry:** sell at 15:15 the ATM iron fly (short ATM straddle, long ±200 wings) or the iron condor (short ±50, long ±250; the same 200-point width as the fly). Set before any scoring: a coverage check found the ±300 wings printed at 15:15 on only 174 of 541 nights, against 507 for ±250.
2. **Exit:** buy back next morning at 09:16 / 09:20 / 09:45 / 10:15.
3. **Selection:** 8 variants, leave one year out.
4. **Control:** the same structure sold 09:20 → bought 15:15 the same day (the day leg).
5. **Description:** the long straddle overnight, and implied σ 15:15 → 09:20.
6. **Wallets:** ₹15k / ₹20k / ₹30k, 1 lot when the maximum loss fits.
7. **Pass:**
   - held-out > 0 at strict and house;
   - ≥ 3/4 years;
   - positive without the best 5 nights;
   - beats the day leg;
   - worst night reported.

### SN125 — the last half-hour (holding to 15:25 allowed)

- **Signals,** buying the ATM option at 15:00 and selling at 15:25:
  - the sign of the previous close → 09:45 return (Gao's first half-hour incl. overnight);
  - the sign of 14:30 → 15:00;
  - the sign of the opening gap;
  - first-half-hour and 14:30 → 15:00 both agreeing.
- **Days:** Gold-free (primary) and all days.
- **Scoring:** leave one year out over the 4 signals.
- **Control:** a random side.
- **Pass:** SN92's companion rule.

### SN126 — trade actively only when movement is underpriced (hot-day scalping)

- **Days:** SN95-L's hot days (Gold-free, R_today top 20% at 10:00).
- **Entry:** 10:00–15:00, a fresh 3-minute burst ≥ k × ATR × √3, buy ATM in its direction.
- **Exit:** a 2-ATR index stop and an h-minute clock (25% backstop).
- **Grid:** k ∈ {1.5, 2.5} × h ∈ {5, 15} × at most {5, 15} trades a day (8), leave one year out.
- **Controls:**
  - a random side on hot days;
  - the same rules on cold Gold-free days (described).
- **Pass:** SN92's companion rule.

### SN127 — when is buying an option least bad? (description)

The ATM call and put bought at every 15-minute clock 09:20–15:00 and sold 15 minutes later (strict):
- the mean per lot;
- hot vs cold days (10:00 flag) for clocks ≥ 10:00;
- by year.

A map for the system and the partner coach.

### SN128 — the morning implied-volatility crush, without overnight risk

1. **Trade:** sell at 09:16 or 09:20 the iron fly or condor (as SN124), buy back at 09:45 or 10:15.
2. **Grid:** 8 variants, all days and Gold-free, leave one year out.
3. **Control:** the same structure 12:00 → 12:30.
4. **Pass:** SN124's rule.

### SN129 — the gap-day sleeve, assembled from survivors

1. **Pool:** any of SN123–SN128 that passed, plus SN95-L.
2. **Account:** one separate sleeve beside Gold, each component's held-out picks by year, components non-overlapping by clock, one ₹25k sleeve with a 20% day limit, every wallet.
3. **Comparison:** the same money added to Gold (SN116's lesson).
4. **If nothing passed:** the sleeve is not formed, and the best description is shown labelled as such.

### SN130 — synthesis

What profitable humans actually do (the sources above), what the partner's data shows (SN121–SN122), and what a machine can copy. Practical outputs:
- partner-coach suggestions, messages only, the owner's call;
- the forward plan;
- the scoreboard for SN121–SN129.
