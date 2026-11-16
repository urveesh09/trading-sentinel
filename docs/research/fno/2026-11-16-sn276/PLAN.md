# SN276–SN285: learn from every earlier strategy, on all the data at once (plan, frozen before any number)

**Owner (Nov 16, 2026):** "10 slots more. Try some other perspective … with that same wallet, size and cover the [gap] case … specific for gap days … we have so much research done already and so much data already, you can take and learn from the good points of strategies … use whatever you want."

**The constraints are SN251's:**
- Gold v5's wallet;
- bought options only (Tier A);
- one lot per decision in the research tables;
- a ₹3,000 stop (10% of ₹30k) on minute closes;
- Zerodha charges + ₹205 per lot per leg (`gl.py`, `legs.py` of `2026-11-16-sn251`, unchanged).

**The new perspective:**
- Every single gap-day signal failed alone. Several carried a little information somewhere:
  - volatility persistence (SN101, p = 0.002 in 2023–26);
  - the opening range predicting big days (SN84);
  - gaps; yesterday's range; breakouts (positive on both exams in SN258);
  - pre-holiday sessions (positive on all four samples in SN272);
  - the ADX gate; days to expiry; RBI days.
- SN276–SN280 combine them, on the **largest sample ever used here**: NIFTY Oct 2020 – Oct 2026 plus SENSEX Oct 2024 – Apr 2026, about 1,480 sessions, pooled.
- Learners are scored **strictly walk-forward**. Each half-year from 2022 H1 to 2026 H2 is decided by a model trained only on earlier sessions (both indices), so every scored decision is out of sample for its model.
- **Disclosure:** every session has been seen by earlier studies, and the feature list comes from them. Walk-forward removes the model's look-ahead, not the researcher's.

## Slots

- **SN276: the pooled dataset.**
  - Every session (DEV, TEST, EXAM-N, EXAM-S).
  - Features known at 10:00:
    - R_today (SN95);
    - the 30-minute opening range ÷ open;
    - the gap (signed, absolute) and the move from open to 10:00;
    - the index vs the futures VWAP ÷ ATR;
    - yesterday's range and return, and 5-day realised volatility;
    - the 10-day breakout state at yesterday's close;
    - yesterday's ADX and DMI direction;
    - sessions to expiry and the weekday;
    - pre-holiday, turn-of-month and RBI flags;
    - the ATM straddle ÷ index;
    - the futures basis change since yesterday's close;
    - the futures volume 09:15–10:00 ÷ its mean over the last 5 available sessions;
    - the instrument.
  - Outcomes of four actions at 10:00, each held to 15:10 with the ₹3,000 stop: the ATM straddle (S), the ATM call (C), the ATM put (P), none (N). Each also at ₹400 and one minute late.
  - Recorded: base rates only.
- **SN277: walk-forward action-value learner.**
  - One LightGBM regressor per action predicts its net. Hyperparameters fixed: 300 trees, learning rate 0.03, 8 leaves, 40 per leaf, 0.8 row / column sampling, seed 277.
  - Each session takes the best action if its prediction is > τ, else none. τ ∈ {₹0, ₹300}.
  - Folds: half-years 2022 H1 … 2026 H2; training = every session before the fold.
- **SN278: walk-forward two-stage classifier.**
  - P(up) predicts "index at 15:10 > index at 10:00". P(big) predicts "the straddle ends positive".
  - Trade: the call or put when |P(up) − 0.5| ≥ δ (δ ∈ {0.08, 0.12}); otherwise the straddle when P(big) is in the training predictions' top 15%; otherwise none.
- **SN279: a transparent vote (no fitting).** Seven frozen signals each vote:
  - R_today ≥ 1.332 (SN95's DEV threshold);
  - the opening range in the causal top 20% of the same index's earlier sessions;
  - |gap| ≥ 0.5%;
  - a pre-holiday session;
  - yesterday's range in the causal top 20%;
  - yesterday's close beyond the prior 10 days' high or low;
  - an RBI day.
  - Buy the 10:00 straddle when votes ≥ k, k ∈ {2, 3}.
  - Scored on DEV, TEST, EXAM-N and EXAM-S. Null: as many random sessions of the same sample, 200 draws.
- **SN280: controls and robustness.** Run on the best of SN277–SN279, chosen by the pooled out-of-sample net (SN279's pooled net = the sum over all sessions from 2022 on, to match):
  - shuffled-label learners (labels permuted within each training set, 50 runs) for SN277 / SN278;
  - a random action at the same frequency (200 draws);
  - ₹400; one minute late; without the best 10 days.
- **SN281: cheaper expressions** of the two signals that were positive on unseen data (pre-holiday calls; the 10-day breakout swing, held one session).
  - Compared: the ATM call, an ITM call (one strike in), and the debit spread "buy ATM, sell two strikes out".
  - All four samples. Description only (both are post-hoc).
- **SN282: SN126-L** (hot-day burst scalps, the last frozen watch never exam-run), ported with parity on 2023–26 if the port matches, then scored on 2022, TEST, EXAM-N and EXAM-S. If the port does not match to the rupee, it is recorded as "not portable".
- **SN283: the cash-equity paper books** (Penny Smart V3, Momentum ORB shadow): their Production forward records (read-only) and whether a cash leg fits Gold's intraday wallet. Description only.
- **SN284: the one-wallet account** (`ow.py`) for anything that passes. Not run if nothing does.
- **SN285: synthesis.**

## Pass rule (frozen)

**Learners (SN277 / SN278):**
- out-of-sample net > 0 at ₹205;
- ≥ 6 of the 10 half-year folds positive;
- the NIFTY and SENSEX subtotals both > 0;
- the shuffled-label control's 95th percentile is beaten;
- ₹400 and one minute late both > 0.
- **Picking between a slot's two variants:** the better worst fold.

**The vote (SN279):**
- net > 0 on all four samples;
- DEV beats its null's 95th percentile;
- ₹400 and one minute late > 0 on DEV.

**Anything that passes** goes to SN284. Everything else is reported as it comes out, with no reruns.
