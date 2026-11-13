# SN116–SN120: frozen plan, phase C — the combined learning (committed before any phase C scoring, Nov 13, 2026)

Owner: "SN116 to SN120 ... combined better learning and better perspective and everything."

## What SN91–SN115 established

- **Gold v5:**
  - a direction book whose edge is N11's entry selection;
  - its money scales with capital;
  - every filter or sizing rule tried on it has failed held out.
- **Empty days:**
  - one real signal exists: volatility persistence, captured by the 10:00 straddle;
  - it is thin and lumpy, and fails the concentration and v6 checks;
  - in Gold's own wallet it adds +4.6–4.9% at ₹30k and hurts the growth wallets.
- **Costs:** they are realistic (SN109, SN115).

Phase C stops looking for new signals. It answers the decisions the owner actually faces:
1. where extra capital earns most;
2. what to expect from Gold with real costs;
3. what real money without refills does;
4. whether Gold's edge is genuine after all the selection;
5. what goes forward.

Research only; harnesses imported, never edited; every number is in-sample description unless stated.

## SN116 — where should the next rupee go? (matched total capital)

- **Arms:**
  - Gold v5 at ₹30k;
  - Gold ₹30k + SN95-L in the shared wallet (SN110's rules);
  - Gold ₹30k + a **separate** ₹15k straddle sleeve (SN95-L, ₹15k ceiling, ₹3k room, strict, refilled);
  - Gold v5 at ₹45k (the same ₹45k total);
  - Gold v5 at ₹45k stepping after 50% profit.
- **At ₹50k total:** Gold ₹35k + the sleeve vs Gold ₹50k.
- **Each arm as:** fixed, growing (stop 3) and growing (stop 5).
- **Report:** net, by year, refilled, worst day, maximum drawdown of the cumulative day nets, and net per ₹1,000 of starting capital.

## SN117 — Gold under the measured costs (calibration)

1. **The per-lot equivalent stress, per Production paper entry (SN115's 23 positions):** (fill − decision mid) + (exit mid − exit fill) − the model's half spreads at both prices.
2. **Bootstrap:** 300 resamples of its mean.
3. **Gold v5 rerun at each resampled value:** ₹15k, ₹30k sized, ₹30k fixed, ₹30k growing (stop 3).
4. **Report:** the 5th / 50th / 95th percentile of net, and the point estimate with entries 1 minute late (the upper bound on the measured 39 s delay).
- These are paper fills, not broker fills: labelled.

## SN118 — real money, no refills (every monthly start)

- **Starts:** the first session of every month, Jan 2023 – Jun 2026 (42), each run to Oct 28 2026 with the lab's no-refill account.
  - Equity carries every loss.
  - One lot is kept while equity ≥ ₹7,500; below that the account stops ("dead").
- **Configurations:** ₹30k and ₹50k, sizing equity uncapped or capped at ₹1,01,250 (the deployed top step).
- **Per start:** final equity, lowest equity, maximum drawdown %, dead or not.
- **Summary:** median final multiple, share of starts ending below their start, share dead, the worst final and the worst drawdown.

## SN119 — is Gold's edge real after all the selection? (random-entry Golds)

Gold v5's full machinery (sizing, ITM depth, scale-in, extension, 20% day stop) is fed random entries, 200 draws each:
- `N1`: Gold's own signal days and signal count; the minute is random in 09:30–14:00, the side 50/50, the strike ATM there, and the holding time is the real signal's.
- `N2`: the same count per year on random sessions of that year, with random minute, side and real holding times.

Wallets: ₹15k, ₹30k sized, growing from ₹15k (stop 3), ₹30k growing (stop 3).
- **Output:** v5's percentile in each distribution, and the nulls' mean and 95th percentile.
- **Reading:**
  - v5 above both 95th percentiles: the entries are genuine edge;
  - above N2 but not N1: the edge is day selection;
  - otherwise: the money management, not the entries, makes the money.

## SN120 — the scoreboard and the forward plan

`sn120.py` collects every SN91–SN119 result into one table:
- candidate;
- held-out or in-sample basis;
- ₹30k result vs v5;
- verdict.

The README freezes the forward plan:
- what runs (Gold v5 paper, unchanged);
- what is watched (SN95-L, frozen at SN92);
- the owner's levers with their measured effect;
- what new information would be worth acquiring, in order;
- the decision rules.
