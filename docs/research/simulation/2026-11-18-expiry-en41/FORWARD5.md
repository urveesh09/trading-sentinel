# Forward test registered for EN55: frozen before its first session

> **Erratum, Nov 18 (before the first session):** the first sessions are SENSEX **Nov 19** and NIFTY **Nov 23**, not Nov 20 / 24. The 20-session result is a comparison only, and a separate qualification layer (first 40 expiries per index, ≥ 20 parents, positive at ordinary and adverse fills) is registered in [ERRATA-20261118.md](ERRATA-20261118.md). The rule below is unchanged.

Written Nov 18, 2026, after the round-5 score and before the cohort's first session. The first session is SENSEX on Nov 20, 2026; the first NIFTY session is Nov 24, 2026.

**What it tests:** EN55, the "learned E03.2", against E03.2 unchanged. This is not a qualification for real money.
- **EN55:** E03.2 plus EN28's patient entry, EN27's half-first scout and EN29's stall runner. Its rule is `en_lab5.ARMS["EN55"]`.
- **E03.2:** unchanged.

**Cohort:** the first 20 expiry sessions per index after Nov 18, 2026.
- Both arms read the same recorded sessions.
- Each runs in its own Rs 30,000 wallet, with brakes on the trading high-water and 50% profit sweeps.

**Data:** no runtime code or flag changes now.
- The sessions come from Breeze 1-minute afternoon chains (download skill) plus index and futures. TR01 depth is used where it exists.
- If the owner wants live paper rather than replay, that is a separate implementation through the normal GitHub path, on the owner's word.

**Decision, once, after both indices have 20 sessions.** EN55 earns the owner's promotion review only if all of these hold on each index:
- wallet net ≥ E03.2's;
- fixed-cap ordinary and adverse net ≥ E03.2's;
- net without its best expiry ≥ E03.2's;
- worst expiry no worse than E03.2's.

Even then it becomes a paper main candidate only. No size increase and no real money follow from this test.

**Never:** stopping early because a hero appears, changing the cohort, or re-running with altered rules.
