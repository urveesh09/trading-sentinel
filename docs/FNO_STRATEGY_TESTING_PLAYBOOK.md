# F&O strategy testing playbook

This is the complete record of how the NIFTY F&O strategy tests of October 27, 2026 were done: the data, the tools, every strategy tested, the results, and the daily forward test now running. Written for the owner and for any agent who will test their own strategies the same way.

Read [RESEARCH_TESTING_METHOD.md](RESEARCH_TESTING_METHOD.md) first: freeze before scoring, never tune on seen data, tests ≠ profitability.

> **Update, Oct 30, 2026:** testing has moved on to year-long ICICI Breeze data: NIFTY Jan–Oct 2026, all of 2025, and 2024 as a one-time exam.
> - **The method and a copy-ready template:** [FNO_YEAR_DATA_TESTING_METHOD.md](FNO_YEAR_DATA_TESTING_METHOD.md).
> - **What was found:** [FNO_RESEARCH_2026-10-30_SUMMARY.md](FNO_RESEARCH_2026-10-30_SUMMARY.md).
> - **Superseded here:** the window ledger in section 8. The current ledger is section 11 of the method document.
>
> This playbook still describes the archive-quote replays, the grid, the evolution and the daily forward panel.

---

## 1. The three tests at a glance

| Test | Question | Data | What ran | Verdict | Folder | Commits |
| --- | --- | --- | --- | --- | --- | --- |
| **O27 consistency grid** | Of many entry × exit mixes, which is the most *consistent*, not the most earning? | 29 archived sessions, Sep 10 – Oct 26 | 360 arms (10 entries × 36 exits) plus a parity arm, each through the full live book | The frozen pick `OR20\|LOCK_LATE\|T75\|TR1.5` made **0 trades** in the check window, so it is unconfirmed. CURRENT ranked 27th of 32 eligible. | `docs/research/fno/2026-10-27-consistency-grid/` | freeze `d4cfb7e`, results `32f4271`, docs `9831184` |
| **O27b evolution** | Breed the good strategies like genes, add literature parameters, and test again | Same 29 sessions; evolution saw only Sep 10 – Oct 9 | 517 genomes (17 genes), 10 generations | `NONE_PASSED_KEEP_SHIPPED`. The finalists earned +₹15–21k on the selection window but made 0–1 trades on the hidden Oct 12–26 window. | `docs/research/fno/2026-10-27-evolution/` | freeze `3f97f2c`, results `080330d`, docs `93d7e77` |
| **O27c forward panel** | Do the best candidates beat the shipped book on *new* days? | Every session from Oct 28 to Nov 27 (forward, untouched) | 6 arms replayed daily at 16:00 IST from a pinned copy | Running; the decision is read on Nov 27 | `docs/research/fno/2026-10-28-forward-panel/` and the pinned copy (section 9) | `e6af14b` (first freeze), `3dc3342` (16:00 re-freeze), docs `22b3144`, `3f76666` |

Also run that day (exploration on seen data, not frozen): quick-scalp designs and spreads (section 6.2), and the "why were Oct 21/23/26 quiet" diagnosis (section 6.1). Reference copies of those scripts are in `docs/research/fno/2026-10-27-consistency-grid/reference-scripts/`.

---

## 2. Ground rules (non-negotiable)

1. **Production is read, never edited.** The data comes from a read-only copy of the Production data volume (section 3). There are no Production writes, no Kite calls from research, and no order or broker code. Changes are made in Dev (`C:\Users\Urveesh\Desktop\trading-sentinel`) and promoted only through GitHub on the owner's word.
2. **Freeze before scoring.** The study definition, its windows and its decision rule are written to `freeze.json` and committed before the first result is computed. The runners refuse to score if any bound source file, dataset file or effective `FNO_*` setting changed after the freeze.
3. **Seen data is seen.** Never tune on a window and then call it evidence. The ledger is in section 8, and in `RESEARCH_TESTING_METHOD.md`.
4. **The shipped book is the control.** Every study replays the current live book next to the candidates, and a parity check proves the replayed control is the live book.
5. **Proving weeks and real money.** During a proving week (Oct 26–30, 2026) the paper single-leg entry and exit rules do not change. The real-money test (`FNO_LIVE_TEST_ENABLED`, Nov 2–6) mirrors the paper book, and only the owner flips that switch. A research "pass" never changes either.
6. **Secrets.** Research needs none. Never print `.env` values, API keys, tokens or the tunnel files. Settings comparisons print names and hashes only.
7. **Machine.** 6 physical / 12 logical cores and 16 GB RAM, shared with Production.
   - During market hours: at most 4 workers.
   - After hours: 6–10 workers (Production then idles at about 1% CPU and 0.8 GB). CPU, not RAM, is the limit, so stopping Production gains nothing.
8. **Honesty.** Report what the rule says, including when the rule had a gap (the O27 zero-trade pass). Never call a replay result a profit promise.

---

## 3. Where the data comes from (Production, read-only)

### 3.1 What Production records

The live engine (`python-engine`, container `python-engine`) keeps a **research archive** on the Docker named volume `production_trading-sentinel_trading_data`, which is mounted at `/data` in the containers.

| Path on the volume | Content | Written by |
| --- | --- | --- |
| `/data/research/quotes/<YYYY-MM-DD>/` | Every quote batch, about every 60 s, 09:15–15:40 IST: the NIFTY and SENSEX front futures, plus ATM±5 calls and puts for two expiries, as raw Kite REST full-quote packets (bid/ask depth, LTP, OI, volume, timestamps). | `research_quote_collector.py` |
| ↳ `quotes.jsonl.open` | The day's journal while the day is open. It is sealed into `quotes-<hash>.jsonl.gz` plus a `.manifest.json` when a later session starts. | |
| `/data/research/collection-runs/<day>/runs.jsonl` | One record per collector tick, including off-session ticks. Not used by the replay. | `research_archive.record_collection_run` |
| `/data/research/fno_exit_paths/<day>.jsonl` | Every look the fast exit loop took at a held option (~10 s). Exported, but not yet used by the replay. | `fno_exit_paths.py` |
| `/data/cache.db` (SQLite) | `intraday_cache_by_token` (5-minute futures candles), `fno_signals` (every live F&O evaluation with its regime and accept/reject reason), `fno_positions` and `fno_dr_positions` (paper positions). | engine |

The collector's last quote tick is **15:40 IST** (the F&O close; `research_quote_collector.research_quote_collection_tick`). After that the day's quote journal no longer changes.

### 3.2 The export (how the data leaves Production)

`scripts/export_fno_replay_dataset.py` uses the standard library only and runs **inside a throwaway container** made from the Production engine image. The Production volume is mounted **read-only** (`:ro`), and SQLite is opened in `mode=ro`:

```powershell
docker run --rm --memory 1g `
  -v production_trading-sentinel_trading_data:/data:ro `
  -v "C:/Users/Urveesh/Desktop/trading-sentinel/docs/research/fno/<dated>/_local/dataset:/out" `
  -v "C:/Users/Urveesh/Desktop/trading-sentinel/scripts:/scripts:ro" `
  --entrypoint python production_trading-sentinel-python-engine:latest `
  /scripts/export_fno_replay_dataset.py --data /data --out /out [--include-finished-today]
```

From Git Bash, prefix the command with `MSYS_NO_PATHCONV=1`. The output folder must be empty, because exports are written once.

**Output layout** (about 210 MB for 29 sessions; it lives in a `_local/` folder, which git ignores):

| File | Content |
| --- | --- |
| `quotes/<day>/…` | Byte copies of the archive segments; unsealed journals are copied as-is. |
| `fno_exit_paths/<day>.jsonl` | Byte copies, finished sessions only. |
| `fno-replay.sqlite` | `fut_candles` (every cached candle of every NIFTY/SENSEX future token the archive saw), plus `fno_signals`, `fno_positions` and `fno_dr_positions`. |
| `manifest.json` | `schema` (`sentinel_fno_replay_dataset_v1`), `source`, `exported_at_utc`, `quote_days`, `unsealed_days`, `nifty_future_tokens`, `option_expiries` (per underlying, every expiry ever quoted: the replay's expiry calendar), `row_counts`, and `files_sha256` (every file). |

**Which days are included:**
- Every sealed session.
- A past session whose journal is still open (copied, and listed in `unsealed_days`).
- **Not** the active day (its folder date is ≥ today's UTC date), unless `--include-finished-today` is given **and** it is 15:50 IST or later. That flag was added on Oct 27 for the 16:00 forward run.

**Datasets made on Oct 27:**
- `docs/research/fno/2026-10-27-consistency-grid/_local/dataset`: 29 sessions, Sep 10 – Oct 26, all sealed. The manifest hash is bound in both study freezes.
- The earlier `docs/research/fno/2026-10-24-entry-arms/_local`: 28 sessions to Oct 23, with Oct 23 unsealed at the time. The exploration scripts used it.

### 3.3 Other read-only access to Production used

**Settings parity.** Every effective `FNO_*` setting was compared between Dev and Production by per-key SHA-256, printing names only: all 123 were equal. The script is `reference-scripts/fno_settings_hash.py`, run as:

```bash
MSYS_NO_PATHCONV=1 docker exec -i -u quantuser -w /app python-engine python - < fno_settings_hash.py   # Production
PYTHONPATH=python-engine python-engine/winvenv/Scripts/python.exe fno_settings_hash.py              # Dev
```

**Live decisions.** `reference-scripts/why_quiet.py` read `fno_signals` with `sqlite3.connect("file:<DB_PATH>?mode=ro", uri=True)` inside the running container. That showed the EMA rejections on Oct 21, 23 and 26.

**Rules for this kind of access:**
- Use `docker exec -u quantuser` (the gateway has no `quantuser`).
- Never call a write path mid-day.
- Never pass a `file:...?mode=ro` URI to `market_calendar.is_trading_day`.
- Never make an ad-hoc Kite call.

---

## 4. The replay engine (`python-engine/fno_policy_replay.py`)

### 4.1 What it reproduces

It re-runs the **shipped NIFTY single-leg paper book** on the archived evidence, calling the production code itself.

| Part | Production code called | Replay specifics |
| --- | --- | --- |
| Signal | `fno_engine_mom.evaluate_fno_mom`, or `fno_shadow._variant_signal` for a research variant | Uses the 21-calendar-day 5-minute futures frame (`fut_candles`) and the **live logged regime** per bar (`fno_signals`, point-in-time). |
| Chain view | `fno_chain._parse_quote_entry`, `ChainSnapshot` | Built from each archived batch. |
| Strike, gates, sizing, max loss, reward/risk | `fno_entry_plan.plan_single_leg_entry` | — |
| Loss brakes | `fno_shared_risk.entry_halts` | — |
| Adaptive size and the two-strike day halt | `fno_adaptive_risk.risk_stance` | Seeded with every real paper close before the window. The defined-risk book's actual closes are added at their real times, the same for every arm. |
| Exit ladder | `fno_exit_rules.evaluate_single_leg_exit` | Underlying stop, premium backstop, target → trail, time stop, profit lock, hard flat at 15:10. |
| Fills and costs | `fno_costs.calc_fno_costs` | Buy at the ask, sell at the bid (else LTP); real charges. |
| Clock | — | Entries on the 90 s live grid, aligned to that day's logged live tick phase. Management on **every archived batch** (~60 s) when `manage_every_observation` (fast exit) is on, as live. |
| Expiry calendar | — | Every NIFTY expiry the archive ever quoted, so expiry days are blocked as live. |

**Not replayed:**
- the defined-risk (spread) book's decisions;
- shared-risk reservations across books;
- broker rejections and partial fills;
- SENSEX;
- holds that drift outside the archived ATM±5 strikes (unpriceable: the trade is reported `UNRESOLVED`, as on Oct 21 for the 23050 PE);
- the live fast exit's 10 s looks (the archive is ~60 s);
- entries before 09:45 (`FNO_ENTRY_START_MIN`), so a 15- or 20-minute range cannot trade a 09:30–09:40 break.

### 4.2 API

```python
from fno_policy_replay import ReplayData, ReplayPolicy, run_replay
result = run_replay(dataset_folder, start="YYYY-MM-DD", end="YYYY-MM-DD",
                    policy="CURRENT" | "<declared name>" | ReplayPolicy(...),   # [O27] a ReplayPolicy object is accepted
                    data=None | ReplayData(...))                               # [O27] pass a cached reader
```

**`ReplayPolicy` fields:**
- `name`;
- `manage_every_observation` (fast exit; live is True);
- `partial_at_target`, `pyramid_house_money`, `trend_day_filter` (research switches);
- `exit_overrides`, a tuple of `(setting, value)` applied to the exit ladder. The keys are those of `fno_exit_rules.live_single_leg_exit_params`: `FNO_TRAIL_ATR_MULT`, `FNO_TIME_STOP_MIN`, `FNO_TIME_STOP_MIN_R`, `FNO_TIME_STOP_RESPECTS_PREMIUM`, `FNO_STOP_PREMIUM_PCT`, `FNO_PROFIT_LOCK_ENABLED`, `FNO_PROFIT_LOCK_ARM_R`, `FNO_PROFIT_LOCK_FLOOR_R`, `FNO_PROFIT_LOCK_KEEP_FRACTION` and `FNO_PROFIT_LOCK_CONFIRM_SEC`;
- `reentry_confirmation`;
- `signal_variant`: a `fno_shadow.VARIANTS` name or an `FnoShadowVariant` object.

**`result` contains:**
- `trades`, one record per trade: entry/exit time and premium, exit reason, `net_pnl`, `r_multiple`, `lots_at_exit`;
- `summary` (closed, net, net excluding the best winner, max drawdown, win rate, profit factor, exit reasons);
- `funnel` (why signals were refused);
- `notes`;
- `decisions` (every fired signal);
- `parity_vs_live` (replayed vs live paper trades);
- `dataset`;
- `expiry_calendar`.

**Speed.** Parsing one session's quotes takes about 4.3 s and 30 MB. A pickled parse is about 2 MB and loads in 0.12 s, so use `run_fno_consistency_grid.CachedReplayData` or `run_fno_forward_panel.SessionCache`. One arm over 29 sessions takes about 1 minute per worker.

### 4.3 Entry signal variants (`python-engine/fno_shadow.py`)

`FnoShadowVariant` describes an opening-range-break entry. The recorded live shadows (`VARIANTS`: FNO_BASE, FNO_CONFIRM_1, FNO_OR_20, FNO_OR_45, FNO_CONTINUATION) never set the research fields below, and every default leaves the base behavior unchanged.

| Field | Meaning | Default |
| --- | --- | --- |
| `opening_range_minutes` | Opening-range length | — |
| `freshness` | `crossing` (only the bar that crosses), `first_confirmation`, or `crossing_or_pullback` | — |
| `confirmation_bars`, `max_extension_atr`, `pullback_atr` | Settings of those modes | — |
| `ema_filter` [O27] | Require the multi-day EMA trend agreement | True |
| `ema_spans` [O27b] | EMA spans of the trend check | `FNO_EMA_FAST/SLOW` (21/50) |
| `buffer_atr` [O27b] | Break buffer beyond the range, in ATR | `FNO_OR_BUFFER_ATR` (0.25) |
| `stretch_buffer` [O27b] | Crabel stretch: the prior 10 sessions' mean open-to-nearer-extreme | False |
| `min_rvol` [O27b] | Time-adjusted relative volume minimum | `FNO_MIN_RVOL` (1.2) |
| `vwap_side` [O27b] | The break closes on the trade's side of today's VWAP | False |
| `or_bias` [O27b] | `with` / `against` the range's own drift (its last close vs the day's open) | None |
| `gap_align` [O27b] | Only with today's opening gap (when the gap is ≥ 0.1%) | False |
| `max_or_width_ratio` [O27b] | Range width ≤ this × the prior 10 sessions' mean | None |
| `narrow_prior_days` [O27b] | NR-n: the previous session's range is the narrowest of the last n | None |
| `latest_entry_min` [O27b] | No signal at or after this IST minute | None |
| `stop_atr_mult` [O27b] | Stop = max(range opposite, close − k·ATR) | `FNO_STOP_ATR_MULT` (1.5) |
| `target_r` [O27b] | Target (arms the trail) in R | `FNO_TARGET_R` (1.8) |

**Where each check sits:**
- The latest-entry and EMA-span checks come before the break test, and the buffer sets the break level.
- On a fresh break, `_gene_reject` applies VWAP, bias, gap, width and NR in that order.
- `min_rvol`, `stop_atr_mult` and `target_r` replace their settings at the usual places.
- `_prior_sessions(closed, day, or_minutes)` provides causal daily OHLC and range widths, cached per frame window.

**Parity.** The shipped break evaluated through the variant code path (any name except `FNO_BASE`) trades **exactly** as `evaluate_fno_mom`. This was checked on all 29 sessions (O27 parity arm) and again on Sep 10 – Oct 9 (O27b).

---

## 5. Metrics used

| Metric | Definition |
| --- | --- |
| Net | Sum of trade `net_pnl` (after charges) for trades **entered** in the window. Sizing carries over between windows, as live. |
| Net excluding the best winner | Net − max(best trade, 0). Does the result depend on one trade? |
| Net excluding the best day | Net − max(best day, 0), where day = entry day. Stricter: one lucky day. |
| Max drawdown | Largest peak-to-trough fall of the cumulative net, trades in exit-time order, starting from 0. |
| CS (O27) | Net excluding the best winner ÷ max(max drawdown, ₹1,000). |
| Plateau CS (O27) | Median CS of the arm and its one-step exit neighbours, so a lone lucky setting scores low. |
| Fitness (O27b) | On window A: (net − best day) ÷ max(DD, ₹1,000) − 0.5 × (A halves with net < 0). Fewer than 8 trades scores −5 + trades ÷ 8. |
| Plateau fitness (O27b) | Median fitness of the genome and all one-step neighbours (each gene ±1 allele). |
| Green / red days, green weeks | Days (or ISO weeks) with net > 0 or < 0. A week with no trades is neither. |
| Net per lot | Σ net ÷ lots at exit. The real-money test trades one lot. |
| Unresolved | Holds that could not be priced (outside the archived strikes). Excluded from the net and reported. |

---

## 6. Every strategy tested on Oct 27, 2026

### 6.1 The shipped book (control, "CURRENT" / "SHIPPED")

**Entry:** a 30-minute opening range (09:15–09:45). The trade is taken on the **first** 5-minute close beyond the range ±0.25 ATR(14, Wilder, 5-min futures), and only that crossing bar counts ("fresh break"). The entry must also pass:
- the regime is not `REGIME_3_CRISIS`;
- EMA(21) and EMA(50) of the multi-day 5-minute frame agree with the direction;
- time-adjusted RVOL ≥ 1.2;
- the entry window is 09:45–14:45, with at most 3 trades a day;
- the expiry-day block;
- the reward/risk gate of 1.3 on premium.

**Option:** strike chosen by delta (`select_strike_by_delta`), with a spread cap, bought at the ask.

**Stop:** max(the range's opposite edge, close − 1.5 ATR); the target is 1.8R.

**Exits:**
- underlying stop;
- premium backstop −25%;
- trail 1.0 ATR once the target arms it;
- time stop after 45 minutes when the move is under 0.5R;
- profit lock (arms at 0.4R, floor 0.1R, keeps 50% of the best gain, 8 s confirm);
- hard flat at 15:10;
- fast exit every 10 s live (~60 s in replay).

**Sizing:** the ₹2.5L paper bankroll, at most 2 lots, the adaptive stance and the 15% drawdown halt.

**Diagnosis (Production `fno_signals`):** on Oct 21 (10:10 short), Oct 23 (09:45 short) and Oct 26 (09:50 long) the break fired on the right bar, but the lagging EMA check refused it. Fresh-break-only then lost the trend day: NIFTY moved 311, 264 and 197 points.

### 6.2 Exploration (seen data, Sep 10 – Oct 23; not frozen; reference scripts)

**"Is ₹100–200 available?"** (`explore.py`):
- In 1,087 of 1,218 five-minute moments, a CE or PE reached +₹200 net within 15 minutes, in hindsight.
- Picking the side in advance (2,254 cases), +₹200 came first in 951, −₹300 first in 1,223, and neither in 80.
- Charges plus spread are about ₹75 a round trip.

**Quick-scalp single-leg designs** (`arms.py`, `explore_lib.py`): one position at a time, 1 lot, ask in / bid out, real charges. Exploration ATR is a simple 14-bar mean; VWAP is today's cumulative. Strike by delta with the `FNO_MAX_SPREAD_PCT` cap. Entries 09:45–14:30, at most 6 a day.

| Signal | Rule (on a closed 5-minute futures bar) |
| --- | --- |
| MOMO | Close above all earlier highs today and above VWAP, with a body ≥ 50% of the range (mirror for short). |
| PULLBACK | 6 bars above VWAP, then a bar dipping to VWAP + 0.25 ATR that closes green above the prior high (mirror). |
| FADE | The previous bar made a new day high, and this bar closes below its low and is red (mirror). |

| Exit | Rule |
| --- | --- |
| X1_200_300_15 | +₹200 net target, −₹300 net stop, 15 min |
| X2_ATR06_20 | ±0.6 ATR on the underlying, 20 min |
| X3_200_BARSTOP_20 | +₹200, stop at the signal bar's extreme, 20 min |
| X4_400_400_30 | ±₹400, 30 min |

All 12 combinations lost, from −₹427 to −₹8,932. The best was MOMO/X2 at −₹2,147 (70 trades, PF 0.93).

**Debit-spread versions** (`arms_spread.py`): buy the chosen strike and sell 100 points further out. Exits were "half of max profit / 60% of max loss" held to square-off, the same with 60 minutes, or "⅓ of max / 50% / 30 minutes". MOMO held to square-off made +₹962 over 22 trades (DD ₹7,632), which is noise; the others lost.

**No-EMA prototype** (`proto_replay.py`):
- CURRENT: 13 trades, +₹10,801, DD ₹1,991.
- No EMA check: 24 trades, +₹20,949, DD ₹4,406.

The gain came from Oct 21 and 23, the motivating days, so it is not evidence.

### 6.3 O27 consistency grid (`scripts/run_fno_consistency_grid.py`)

- **Entries (10):** OR30 (shipped), OR20, OR45, CONFIRM1 (one confirming bar, extension ≤ 0.35 ATR) and CONT (break or pullback-resume within 0.25 ATR), each with and without the EMA check.
- **Exits (36):** lock TIGHT (arms at 0.25R, keeps 60%) / LIVE (0.4R, 50%) / LATE (0.8R, 50%) / OFF × time stop 30/45/75 min × trail 0.6/1.0/1.5 ATR.
- **Windows:** A_select Sep 10 – Oct 9 (19 sessions); B_check Oct 12 – 26 (10 sessions).
- **Rule:** eligible on A with ≥ 8 trades, net > 0 and net excluding the best winner > 0. Rank by plateau CS. Check on B: net ≥ 0 and DD ≤ max(1.5 × CURRENT, ₹5,000). The first ranked arm that passes is recommended.
- **Result:** pick `OR20|LOCK_LATE|T75|TR1.5`, with A at 11 trades, +₹12,916, DD ₹2,877, and **0 trades in B**.
- **The gap:** "net ≥ 0" passed a zero-trade arm. The gap is reported, not repaired; later checks require trades.

**Cross-arm lessons:**
- 20-minute ranges are the most robust.
- A 30-minute time stop is worst.
- Lock and trail settings barely matter.
- CONT with the EMA check loses.
- The EMA check depends on the regime: removing it raised net in only 1–4 of 36 exits on A, but in all 36 on B.
- No arm earns daily.

Full tables: the study README.

### 6.4 O27b evolution (`scripts/run_fno_evolution.py`)

**Genome (17 genes, alleles in neighbour order):**

| Gene | Alleles | Source |
| --- | --- | --- |
| or_minutes | 15, 20, 30, 45 | O27; the stocks-in-play ORB study (5–25 min) |
| freshness | crossing, first_confirmation | O27 (continuation dropped as a loser) |
| trend | ema_21_50, ema_9_21 (our own variation), off | O27 regime finding |
| buffer | 0.10, 0.25, 0.40 ATR, stretch | Crabel |
| min_rvol | 0.8, 1.0, 1.2, 1.5 | stocks-in-play (RVOL > 1) |
| vwap_side | off, on | ORB practice |
| or_bias | with, off, against | window-A winners analysis |
| gap_align | off, on | gap studies |
| or_width_ratio | off, 1.25, 1.0, 0.8 | Crabel compression |
| narrow_prior_days | off, 4, 7 | Crabel NR4/NR7 |
| latest_entry | 12:00, 13:30, 14:45 | time cutoff |
| stop_atr | 1.0, 1.5, 2.0 | ATR stop |
| target_r | 1.2, 1.8, 2.5 | — |
| lock | TIGHT, LIVE, LATE, OFF | O27 |
| time_stop | 45, 60, 75, 90, off (O27's 30 dropped) | O27 |
| time_min_r | 0.25, 0.5 | — |
| trail | 0.6, 1.0, 1.5, 2.0 | O27 |

**How it bred:**
- **Seeds:** the 31 eligible O27 arms (T30 and CONT removed), filled with random genomes to 40.
- **Breeding:** tournament of 3, uniform crossover, 12% per-gene mutation (70% one step, otherwise any allele), 4 elites and 4 immigrants per generation, 10 generations, seed 20261027.
- **Selection window:** A only.
- **Finalists:** the top 5, ranked by plateau fitness, then checked once on B, requiring **≥ 3 trades**, net ≥ 0 and DD ≤ max(1.5 × shipped, ₹5,000). "B without Oct 21/23/26" was shown for information.

**What window A's winners had in common** (`winning_days.py`, 43 distinct grid entries, A only):
- A few afternoon trend-day breakdowns in the gap's direction made most of the money.
- Breaks *against* the range's drift did better.
- With-gap entries were better, a narrower range was mildly better, and NR4 was worse.
- VWAP side never differed.

**Result:** `NONE_PASSED_KEEP_SHIPPED`.
- The finalists earned +₹15,330 to +₹21,110 on A (shipped: +₹7,286), but **0–1 trades on B**. They all kept EMA 21/50, which refused the late-October trends.
- **Allele lessons:** first confirmation, both bias filters, NR4/NR7, range caps ≤ 1.0×, a 12:00 cutoff, stretch and RVOL 1.5 mostly killed trading. The shipped RVOL, target, stop, buffer and cutoff sit at or near the best alleles. EMA 9/21 did not beat 21/50 on A.
- **Interaction:** genes are not independently good. The let-it-run exits on the shipped entry lowered A to +₹2,917.

### 6.5 O27c forward panel arms

| Arm | Genome (non-shipped genes) |
| --- | --- |
| SHIPPED | — (control) |
| EVO_PLATEAU_1 | OR20, buffer 0.4, width ≤ 1.25×, stop 1.0 ATR, lock off, T75, trail 1.5 |
| EVO_BEST_FITNESS | OR30, buffer 0.4, RVOL 1.0, with the gap, width ≤ 1.25×, lock off, T75, trail 1.5 |
| EVO_OR20_LET_RUN | OR20, lock off, T75 needing 0.25R, trail 1.5 |
| O27_PICK | OR20, lock late, T75, trail 1.5 |
| O27_OR20_NOEMA | O27_PICK without the EMA check |

Exact genomes are in `scripts/run_fno_forward_panel.py` `PANEL` and its `freeze.json`. The tests tie each one to its source result.

---

## 7. How to test your own strategy (recipe for another agent)

### Step 1: get data

Use the newest export, or make one (section 3.2) into `docs/research/fno/<dated-study>/_local/dataset`. Check that `manifest.json` lists the sessions you expect. If you need same-day data after 15:50 IST, add `--include-finished-today`.

### Step 2: choose honest windows

Read the ledger (section 8).
- Everything up to Oct 26, 2026 has been seen for single-leg entries **and** exits.
- Develop on seen data if you must, but score only on sessions nobody has tuned on: forward sessions, or a window you declare untouched *before* looking.

### Step 3: express the strategy

**a. A combination of existing knobs** (most ideas). Build a genome with `run_fno_evolution.GENES`, or a `ReplayPolicy` directly:

```python
import sys
from dataclasses import replace
from pathlib import Path
sys.path[:0] = ["python-engine", "scripts"]
from fno_policy_replay import ReplayPolicy, run_replay
from fno_shadow import VARIANTS
import run_fno_consistency_grid as grid

DATA = Path("docs/research/fno/2026-10-27-consistency-grid/_local/dataset")
CACHE = Path("docs/research/fno/<my-study>/_local/observations"); CACHE.mkdir(parents=True, exist_ok=True)
entry = replace(VARIANTS["FNO_BASE"], name="MY_ENTRY", opening_range_minutes=20, ema_filter=False, min_rvol=1.0)
arm = ReplayPolicy(name="MY_ARM", manage_every_observation=True, signal_variant=entry,
                   exit_overrides=(("FNO_TIME_STOP_MIN", 60.0), ("FNO_TRAIL_ATR_MULT", 1.5)))
result = run_replay(DATA, start="2026-09-10", end="2026-10-09", policy=arm,
                    data=grid.CachedReplayData(DATA, CACHE))
print(result["summary"], result["funnel"])
```

Run it with `python-engine\winvenv\Scripts\python.exe` from the repo root. A variant named `FNO_BASE` goes to `evaluate_fno_mom` directly, so give yours another name.

**b. A new entry idea.**
1. Add a field to `FnoShadowVariant` whose default leaves behavior unchanged.
2. Implement it in `_variant_signal` (before the break) or `_gene_reject` (on a fresh break), reading closed bars only (causal).
3. Add a unit test showing what it changes and that the default is the base evaluator.
4. Never edit the recorded `VARIANTS` rows or `evaluate_fno_mom` for research.

**c. A new exit idea.** If it is one of the exit-ladder keys (section 4.2), use `exit_overrides`. Anything else changes `fno_exit_rules.py`, which the **live** book uses. It needs a default that keeps live behavior, tests, and the owner's promotion, and it is never allowed in a proving week.

**d. Not supported by this replay:** multi-leg spreads (see `reference-scripts/arms_spread.py` for a simplified approach), SENSEX, and stocks. Penny, Momentum, EDGE and Swing use `scripts/run_preregistered_study.py` and the backtest tools; see `RESEARCH_TESTING_METHOD.md`.

### Step 4: pre-register

- **One candidate against the baseline:** add a `Study` with `runner="fno_replay"` to `scripts/run_preregistered_study.py`.
- **Many combinations:** copy `run_fno_consistency_grid.py`.
- **A search:** copy `run_fno_evolution.py`.

Whichever you use:
1. Put the rule in the script (`RULE`, `FITNESS`, `CHECK`).
2. Bind `SOURCES` (every module the result depends on, plus the script itself), the dataset manifest, and the `FNO_*` settings hash.
3. Write a study README with the question, data, rule and limits, and a `## Results` line left pending.
4. Commit the README and `freeze.json` **before** `run`.

**Lessons from Oct 27:**
- Require trades in every check window.
- Discount the best day.
- Use neighbourhood plateaus.
- Keep a window the search never sees.

### Step 5: run

`python scripts/<runner>.py run --out <study> --jobs N`. Watch memory and CPU (section 2.7). The runners resume after a crash (each arm file is written once) and refuse to rescore.

### Step 6: report

- Write the results below the line in the study README. Never edit the frozen part.
- Report the frozen verdict even when it is inconvenient, and show the control and its parity.
- Say plainly what is seen, contaminated or post hoc.
- Commit `results.json`.
- Follow the doc ritual in `AGENTS.md`: update `SYSTEM_GUIDE`, the `NEXT_AGENT_PLAN` slice and `HANDOVER_CHECKLIST`; run `python scripts/build_system_code_atlas.py`; record the commit identity.
- In this checkout another agent's uncommitted doc edits may exist. Stage only your own sections (hash-object/update-index; see the O27 docs scripts pattern) and never `git stash`.

### Step 7: forward test

Make a new dated panel (copy `run_fno_forward_panel.py`), with a new `START`/`END`/`PANEL`/`RULE`. Freeze it **before `START`** and commit, then set up a pinned copy and a task as in section 9. You cannot add arms to a running panel: after `START` it is frozen, so start a new one.

---

## 8. Window ledger for F&O single-leg (after Oct 27, 2026)

> **Superseded on Oct 30, 2026.** NIFTY Jan–Oct 2026 and all of 2025 are now seen, and 2024 is reserved for a one-time exam. See section 11 of [FNO_YEAR_DATA_TESTING_METHOD.md](FNO_YEAR_DATA_TESTING_METHOD.md). The table below is kept as it stood on Oct 27.

| Window | Status |
| --- | --- |
| Sep 10 – Oct 9, 2026 | Seen: the development and selection window of O27 and O27b; earlier exit and entry studies |
| Oct 12 – Oct 26, 2026 | Seen: the decision window of the Oct 24 entry study, and the check window of O27 and O27b. Oct 21/23/26 motivated the no-EMA idea, so they are contaminated for it. |
| Oct 27, 2026 | An expiry day (no single-leg entries). Seen in the partner and paper reviews. |
| **Oct 28 – Nov 27, 2026** | **Untouched**: the O27c forward panel's window. Do not tune on it while it runs. |

---

## 9. The daily recurring test (O27c forward panel), in full

### 9.1 What it is

Every weekday at 16:00 IST, six arms (section 6.5) are replayed through the whole live book on every session from Oct 28 to the newest finished one. It runs on the same machine as Production, **after** the 15:40 F&O close.
- It writes a report; nothing trades.
- It reads Production through a read-only throwaway container. It never touches the running containers, the database or Kite.

### 9.2 Files and places

| What | Where |
| --- | --- |
| Study definition (committed) | `docs/research/fno/2026-10-28-forward-panel/README.md` and `freeze.json` (re-frozen at commit `3dc3342`, before any forward session) |
| Runner (committed) | `scripts/run_fno_forward_panel.py` |
| **Pinned copy** (what actually runs) | `C:\Users\Urveesh\sentinel-operations\fno-forward-panel-20261028\`, holding byte copies of `python-engine\*.py`, the four scripts (`run_fno_forward_panel.py`, `run_fno_evolution.py`, `run_fno_consistency_grid.py`, `export_fno_replay_dataset.py`), and `docs\research\fno\2026-10-28-forward-panel\freeze.json` + `README.md` |
| Launcher | `…\fno-forward-panel-20261028\run_panel.cmd` (logs to `panel.log` in the same folder) |
| Task registration | `…\fno-forward-panel-20261028\register_task.ps1` |
| **Report** | `…\fno-forward-panel-20261028\docs\research\fno\2026-10-28-forward-panel\_local\REPORT.md` |
| Machine-readable state | `…\_local\latest.json` (metrics, every trade, decision), `…\_local\history.jsonl` (one line per run) |
| Working data | `…\_local\exports\<UTC stamp>\` (only the newest export is kept, ~210 MB and growing ~7 MB per session) and `…\_local\observations\` (parsed sessions, ~2 MB each) |
| Interpreter | `C:\Users\Urveesh\Desktop\trading-sentinel\python-engine\winvenv\Scripts\python.exe` (Dev's venv; only its packages are used, not Dev's source) |

**Why a byte copy and not `git archive`.** The Dev checkout has Windows line endings (`core.autocrlf=true`) and Git stores Unix ones. The run checks file hashes against the freeze, so only an exact byte copy of the committed working files matches. Pinning also means later Dev work, by anyone, cannot change the running test.

### 9.3 What one run does (`run_panel.cmd` → `run_fno_forward_panel.py run --jobs 3`)

1. Refuses to start if any bound source in the pinned copy, or the effective `FNO_*` settings, differ from `freeze.json`. Dev's `.env` sets no `FNO_*` key, so the pinned copy, which has no `.env`, has the same values.
2. Exports the Production archive read-only into `_local\exports\<stamp>\`: `docker run --rm --memory 1g`, the volume mounted `:ro`, the image `production_trading-sentinel-python-engine:latest`, and `--include-finished-today`. About 40 s.
3. Re-hashes every exported file. A finished but unsealed newest session is accepted; it is parsed again after it is sealed, because the cache is keyed by file content.
4. Replays all six arms from Oct 28 to the newest session (3 processes; about 1–5 minutes as the month fills).
5. Writes `latest.json` and `REPORT.md`, appends to `history.jsonl`, and deletes the older exports.

### 9.4 Schedule

- **Windows Task Scheduler**, task `Sentinel F&O forward panel`: Monday to Friday at 16:00 local time (IST), `StartWhenAvailable` (if the PC was off at 16:00 it runs at the next start), one instance at a time, 1-hour limit.
- **It was moved from 06:30** on the owner's instruction (Oct 27), because the PC is usually off in the morning, and 16:00 includes that day's own session.
- **Registering.** The agent's own attempt was refused by the permission check (persistence), so the owner registers it once:

```
! powershell -ExecutionPolicy Bypass -File C:\Users\Urveesh\sentinel-operations\fno-forward-panel-20261028\register_task.ps1
```

  It prints the next run time. Until it is registered, ask an agent to run `run_panel.cmd`.
- **Stopping it:** `Unregister-ScheduledTask -TaskName "Sentinel F&O forward panel" -Confirm:$false`, then delete the pinned folder if no longer needed.
- **Holidays and weekends:** no new session, so the numbers do not change; weekends have no trigger.

### 9.5 Reading the report

`REPORT.md` has:
- the status (`NO SESSIONS YET` / `PROVISIONAL` / `FINAL`);
- a table per arm: trades, net, net without its best day, max drawdown, days traded, green and red days, and "promising?" (against the frozen rule, provisional until Nov 27);
- the daily net table: one row per session, one column per arm;
- any unpriceable holds.

Compare each candidate with SHIPPED on the same days.

### 9.6 The decision (Nov 27, 2026)

After the Nov 27 16:00 run, the status is `FINAL`. A candidate is **promising** when it has:
- ≥ 5 trades;
- net > 0;
- net without its best day > 0;
- net > SHIPPED;
- max DD ≤ max(1.5 × SHIPPED, ₹5,000).

**With six candidates, one can pass by chance.** A pass leads to the owner's decision and the normal Dev → GitHub → Production promotion. It never lands in a proving week, and the real-money test keeps mirroring the paper book until the owner says otherwise.

### 9.7 Troubleshooting

| Symptom (in `panel.log` or the report) | Cause and fix |
| --- | --- |
| `bound inputs changed since freeze` | A file in the pinned copy was edited, or a `FNO_*` default or the environment changed. Do not edit the copy. If Production's settings were changed on purpose, the panel's control no longer matches live; note it and keep the frozen comparison. |
| `docker: … cannot connect` | Docker Desktop is not running. Start it (Production needs it anyway) and run `run_panel.cmd`. |
| `No such image` / volume errors | A deploy renamed the image or volume (they are currently `production_trading-sentinel-python-engine:latest` and `production_trading-sentinel_trading_data`). Update only by making a new panel version. |
| `exported file changed` | The disk or copy was interrupted; the next run makes a fresh export. |
| No new session after a trading day | The run happened before 15:50 IST (it then covers up to the previous day), or the collector did not record (check Production's research collection telemetry). |
| `UNRESOLVED` / unpriced holds | A big trend took the held strike outside ATM±5; it is reported separately. |
| Task never ran | It is not registered (section 9.4), or Windows reports it in Task Scheduler → History. |

---

## 10. File index

| File | Role |
| --- | --- |
| `scripts/export_fno_replay_dataset.py` | Read-only export of the Production archive |
| `python-engine/fno_policy_replay.py` | Full-book single-leg replay (policy objects, cached reader) |
| `python-engine/fno_shadow.py` | Entry variants and the research genes |
| `scripts/run_fno_consistency_grid.py` | O27 grid: freeze/run, window metrics, the plateau rule, `CachedReplayData` |
| `scripts/run_fno_evolution.py` | O27b genetic search: genes, fitness, plateau, holdout, allele effects |
| `scripts/run_fno_forward_panel.py` | O27c forward panel: export, replay, report, frozen rule |
| `scripts/run_preregistered_study.py` | Single-candidate pre-registered studies (all modules) |
| `python-engine/tests/test_fno_consistency_grid.py`, `test_fno_evolution.py`, `test_fno_forward_panel.py`, `test_fno_shadow.py`, `test_fno_policy_replay.py`, `test_oct18_sim_fidelity.py` | Tests for all of the above |
| `docs/research/fno/2026-10-27-consistency-grid/` | O27 README, `freeze.json`, `results.json`, `reference-scripts/` |
| `docs/research/fno/2026-10-27-evolution/` | O27b README, `freeze.json`, `results.json` |
| `docs/research/fno/2026-10-28-forward-panel/` | O27c README, `freeze.json` |
| `docs/RESEARCH_TESTING_METHOD.md` | The general method and the window ledger for all modules |

Sources used for the literature genes:
- [Opening Range Breakout for Stocks in Play (QuantConnect)](https://www.quantconnect.com/research/18444/opening-range-breakout-for-stocks-in-play/)
- [NexusFi: Opening Range Breakout](https://nexusfi.com/a/strategies/opening-range-breakout)
- [NR4/NR7 with Breakouts](https://in.tradingview.com/script/sA6AFgk7-NR4-NR7-with-Breakouts-LuxAlgo)
