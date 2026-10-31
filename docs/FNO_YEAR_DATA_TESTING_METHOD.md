# How to test an F&O strategy on the year-long NIFTY data

This is the method behind the Oct 29–30, 2026 studies (O29f–O30m), written so another agent can test their own strategy the same way and get comparable, honest numbers.
- **What those studies found:** [FNO_RESEARCH_2026-10-30_SUMMARY.md](FNO_RESEARCH_2026-10-30_SUMMARY.md).
- **The earlier archive-quote method** (Sep–Oct 2026 quotes, the grid, the evolution, the forward panel): [FNO_STRATEGY_TESTING_PLAYBOOK.md](FNO_STRATEGY_TESTING_PLAYBOOK.md).
- **The general research rules:** [RESEARCH_TESTING_METHOD.md](RESEARCH_TESTING_METHOD.md).
- **Testing size in rupees, not per lot:** section 15, with the worked study [FNO_EARNING_POWER_2026-10-30.md](FNO_EARNING_POWER_2026-10-30.md).
- **The 2024 exam's results (Oct 31):** [FNO_2024_EXAM_2026-10-31.md](FNO_2024_EXAM_2026-10-31.md). Running an exam like it: section 14.
- **The final-strategy study (Oct 31):** [FNO_FINAL_STRATEGY_2026-10-31.md](FNO_FINAL_STRATEGY_2026-10-31.md). A worked example of testing changes on three seen years without fooling yourself: one change at a time, help in every year, held-out-year selection, and a plateau check (`docs/research/fno/2026-10-31-final-book/`).

**The fastest way in:** copy `docs/research/fno/study_template/`, put your entry rule into `entries()`, and follow section 8. The template already does everything below, on all three years. Proven on Oct 31: 2 checks pass; bindings and the January plumbing run work for 2024 (10 trades), 2025 (15) and 2026 (10); the three-year analysis reproduces the live book's figures.

---

## 1. Ground rules

1. **Assess Production, change Dev, promote through GitHub.** Research runs only in the Dev checkout (`C:\Users\Urveesh\Desktop\trading-sentinel`). It never writes to Production, never calls Kite or Breeze for orders, and never changes a runtime setting.
2. **Freeze before scoring.** Commit the books, the pass/fail rule and the analysis script (`freeze.json`, and push it) before the first replay of anything you will judge. The runners refuse to score if a bound file, a dataset or an `FNO_*` setting changed since the freeze.
3. **Seen data is seen** (ledger in section 11). Choosing anything by looking at a year makes that year in-sample for it. Report in-sample results as description, never as proof.
4. **Compare, don't admire.** Every study replays the live book (`REF|LIVE`) and 20 random-entry books beside the candidate.
5. **Every year separately.** A rule must work in 2024, 2025 and 2026 on its own, and in most half-years. A good total alone means nothing. O31 is why: 13 of the 14 strategies positive in both 2025 and 2026 lost money in 2024.
6. **One-time exams.** The NIFTY 2024 exam was scored once on Oct 31 and is used up (section 14). The forward panels are still scored once, unchanged. Never tune on an exam.
7. **No promises.** A replay is not a profit promise. Never write "max loss" or "breakeven" for real money.
8. **Secrets.** Research needs none. Never print `.env`, `breeze.env`, tokens or keys.
9. **The machine is shared with Production.**
   - **Market hours (09:00–15:45 IST):** at most 4 workers, and at least 2 GB of RAM free.
   - **After hours:** up to 6 workers (1.5 GB free).
   - **Never stop Production for research.** The Runner's memory guard enforces these limits.

---

## 2. The data

| Year | Sessions | Sealed dataset (on this PC; `_local/` is git-ignored) | How it was made |
| --- | --- | --- | --- |
| Jan 1 – Oct 28, 2026 | 203 | `docs/research/fno/2026-10-29-year-genome/_local/dataset-nifty` | `yeardata.py export` (O29f) |
| 2025 | 248 (Oct 21 Muhurat dropped) | `docs/research/fno/2026-10-30-nifty-2025-test/_local/dataset-nifty-2025` | `lab_t.py mirror` + `export` (O30) |
| 2024 | 248 (Nov 1 Muhurat dropped) | `docs/research/fno/2026-10-30-day-router/_local/dataset-nifty-2024` | `O30F_YEAR=2024 lab_f.py mirror24` + `export24`; fingerprint `2026-10-30-day-router/data-binding-2024.json` |

- **The source** is ICICI Breeze 1-minute history, in `C:\Users\Urveesh\sentinel-operations\breeze-history-20261029\data\breeze-history.sqlite`.
  - It holds the index, the front futures with a 21-day pre-roll, the nearest weekly options (calls 4 strikes below the day's low to 4 above its high, puts up to 7 above), and daily NIFTY and NIFTY BANK bars.
  - **Downloading** follows that folder's `DOWNLOAD_GUIDE.md`: limits, owner login, verification with `verify_download.py`.
  - **Research never downloads.**
- **Sealed copies:** a study never reads the download while it may be written.
  - It first copies its rows in short read-only pieces into `_local/mirror.sqlite` (or `mirror-2024.sqlite`).
  - Then `yeardata.export` makes a hashed dataset (`breeze.sqlite` + `manifest.json`) that is never rewritten.
- **The candle model** (declared in `docs/research/fno/2026-10-29-year-genome/yeardata.py`):
  - **Observations:** one per minute, at the minute's close.
  - **Option bid/ask:** the close ± half the 75th-percentile spread the quote archive recorded at that premium level.
  - **The underlying:** the front future.
  - **Lot:** 65 (today's contract) in every year.
  - **Regime:** the swing regime label is the live one where Production logged it (Jul 14 – Oct 28, 2026), else UNKNOWN.
- **Known caveat:** candles came out about **₹100–200 per trade per lot better** than the recorded quotes on the overlap. Compare books per lot, and remember that books with many trades are flattered more.
- **Known data quirks:**
  - Jan 31, 2025 and Jan 30, 2026 have no index bars before about 11:53 (a Breeze gap).
  - Dec 31 of a year has no weekly expiry inside that year's data, so no options.
  - Diwali Muhurat days (Oct 21, 2025 and Nov 1, 2024) are not sessions.
  - Mar 2 and May 18, 2024 are half-days: futures exist only 09:15–09:59 and 11:30–12:30, so nothing can trade in the break or after 12:30. A leg still open at the last bar is stored `UNRESOLVED` with no rupee result, and `check_book` counts it. Jan 20, 2024 is a full Saturday session.
  - Expiry sessions have no same-day options, in every year, by design: the book makes no entries then, so the downloads skip them. The funnel shows `chain_unavailable:calendar_expiry_not_archived` on those days.
  - NIFTY BANK's daily bar for Apr 19, 2024 is invalid at source (open and low). It is preserved. No scored book reads NIFTY BANK.

---

## 3. The replay stack

```
sealed dataset --YearData--> fno_policy_replay.SingleLegReplay (the shipped book: entry planner, contract choice,
                             sizing, brakes, drawdown halt, exit ladder, costs, bid/ask fills; unchanged)
                  --BookReplay (O29f lab.py)--> members in priority order; the first member whose gate is open
                             and whose signal fires on the closed 5-minute bar takes the trade; each leg keeps its
                             own member's exits
                  --Runner--> a process pool under the memory guard; every replay saved as _local/evals/<key>.json
                  --analysis--> per-lot metrics per year / half-year / both years (analyze_g.per_lot, one_lot_weeks)
```

- **A replay's identity** is `task_key(book, "year", window)` = `year_<first>_<last>_<digest of the book>`.
  - The same book on the same data gives the same key, so finished replays are reused across studies (`lab_m._seed` copies them) and an interrupted run resumes.
- **Named-signal memo:** the four named strategies' signals are computed once per session (`warm`) and reused. The run asserts that no signal changed within a closed bar.
  - 2026: `2026-10-29-year-genome/_local/named-signals-year.pkl`.
  - 2025: `2026-10-30-nifty-2025-test/_local/named-signals-year.pkl`.
- **The regime table:** one row per session, with every day "side" a gate can read (section 6).

---

## 4. The module chain and how a year is chosen

| Module (`docs/research/fno/…`) | Adds |
| --- | --- |
| `2026-10-29-year-genome/lab.py` (O29f, `Y`) | BookReplay, members (NAMED / LAB), the Runner, the memo, the 20 random books (`null_fixed()`), freeze helpers |
| `2026-10-29-why-study/lab_g.py` (O29g, `G`) | NEW families (NOISE_BAND, LATE_MOMO), the day-regime sides (ADX, volatility, 20-day move…), `_signal()` |
| `2026-10-29-sideways-study/lab_i.py` (O29i) | the range-day families (FADE, VWAP_REVERT, PDL_FADE, RSI2) |
| `2026-10-30-nifty-2025-test/lab_t.py` (O30) | the sealed 2025 copy and dataset; points everything at 2025 |
| `2026-10-30-case-study/lab_c.py` (O30c, `C`) | **`O30C_YEAR=2025 \| 2026`** chooses the year; the DMI / EMA direction sides; "case" books |
| `2026-10-30-case-study/lab_c2.py` | per-member cases (`dmi_breakouts`, `window_10_14`) |
| `2026-10-30-day-router/lab_m.py` (O30m) | the 134-strategy library; the router gate grammar (`a:HIGH&b:UP&dir=with`); reuse of earlier replays |
| `2026-10-30-day-router/lab_f.py` (O30f) | the 2024 exam; **`O30F_YEAR=2024`** points everything at 2024 |
| `2026-10-30-earning-power/lab_s.py`, `lab_s2.py` (O30s) | RAW one-lot replays, adds to winners, the HOLD exit, the stretch reading, the pass-over-stretched rule |

- **Patches go at module level.** Each module patches the one below it when it is imported (paths, the table function, the signal dispatch, the routing). Windows starts each worker by re-importing your main script, so a patch made inside a function would be missing in the workers.
- **Choose the year with an environment variable, never in code.**
  - PowerShell: `$env:O30C_YEAR="2025"`.
  - Git Bash: `O30C_YEAR=2025 python ...`.
  - `run_slice.py --env O30C_YEAR=2025`.
  - **For 2024, use `O30F_YEAR=2024` and leave `O30C_YEAR` unset.** Your script must `import lab_f` before `lab_c` (the template does). `lab_c` itself only knows 2025 and 2026, so `C.YEAR` reads 2026 on that path: use the template's `YEAR`, and `C.WINDOW` for the window.

---

## 5. Python and commands

- **Interpreter:** `python-engine\winvenv\Scripts\python.exe`. A bare `python` on this PC is a Store stub that hangs.
- **Tests:** `python -m pytest <study>\test_*.py -q --timeout=300 -p no:cacheprovider`. pytest-xdist is not installed.
- **Long runs:** `docs\research\fno\run_slice.py` runs one command for at most `--seconds` (default 540), then stops it and its workers cleanly.
  - Repeat it until the log shows `DONE`. Finished replays are kept, so slices add up to one run.
  - Use it whenever your shell limits command time or stops idle background jobs.
  - Example: `python docs\research\fno\run_slice.py --env O30C_YEAR=2025 --log <study>\_local\run-2025.log -- <study>\lab_x.py run --jobs 4`.

---

## 6. Expressing a strategy

**A member** is one strategy with its gate and exits:

| Kind | Constructor | Notes |
| --- | --- | --- |
| Named (the four live strategies) | `Y.named(name, gate="ALWAYS", exit_="OWN", vwap="OFF")` | `name` in SHIPPED, OR20, EFF, TPB; `exit_` in OWN (its own), LIVE, LATE, LOOSE, RUN |
| Lab genome (O27f families) | `Y.lab(genome, gate)`, `Y.random_lab_genome(family, rng)` | families TREND_PULLBACK, PDL_BREAK, VWAP_BAND, MOMO_BURST; genes in `O27F.FAMILY_GENES` |
| New family | `G.new_member(family, gate, **params)` | NOISE_BAND, LATE_MOMO, the range-day families, **or your own** (section 7) |
| Range-day family | `lab_i.side_member(family, gate=..., **genes)` | FADE, VWAP_REVERT, PDL_FADE, RSI2; grids in `lab_i.GRID` |

**Exits** (`O27F.EXITS`):
- LIVE: the shipped exits (profit lock, 45-minute time stop, 1-ATR trail).
- LATE: 75-minute time stop, 1.5-ATR trail, lock at 0.8R.
- LOOSE: 60 minutes, 1.5-ATR, no lock.
- RUN: 120 minutes, 2-ATR, no lock.
- A VWAP-lost exit can be added (`vwap="ON"` / `vwap_exit`).

**A book** is members in priority order:
- `Y.book_of([...])` makes canonical members, drops duplicates and keeps at most 4.
- For more than 4 members, build `{"members": [Y.canonical_member(m), ...]}` directly.
- `Y.FIXED` holds UNION, UNION_DRIVE and each strategy alone. `C.four(gate_for)` builds the four with a gate each (e.g. the live book `C.book(C.four(lambda c: C.ADX))`).

**Gates** are read from the session's row of the regime table, before the session. Each side is HIGH/LOW (or UP/DOWN).
- **From yesterday's daily bars:**

  | Side | Meaning |
  | --- | --- |
  | `adx_abs25` / `adx_abs20` | Wilder ADX(14) ≥ 25 / 20 |
  | `adx14`, `rv20`, `ret20_abs`, `prev_range_rel`, `prev_body` | ADX, 20-day realised volatility, the size of the 20-day move, yesterday's range, yesterday's body; each above or below its median over the previous 60 sessions |
  | `trend_regime` | at least 2 of ADX, volatility and 20-day move HIGH |
  | `dmi_dir` | +DI vs −DI: UP or DOWN |
  | `ema_dir` | close vs its 20-day EMA: UP or DOWN |

- **At 09:45 (the O28 table; each versus its median over the previous 20 sessions):**

  | Side | Meaning |
  | --- | --- |
  | `open_drive` | efficiency of the first 30 minutes |
  | `or_width` | the 09:15–09:45 range against the 5-session average range |
  | `gap` | the open against the previous close |
  | `nr` | the previous day's range against the 5 before it |
  | `trend5` | the 5-day efficiency of the closes |

  Entries start at 09:45, so a 09:45 side never looks ahead.

**Gate forms:**
- **Simple:** `"ALWAYS"` or `"feature:SIDE"`.
- **Router form** (`lab_m.route`; the book needs `"router": "o30m"`): `"adx_abs25:HIGH&dmi_dir:UP&dir=with"`. All the conditions must hold. `dir=with` / `dir=against` keep only signals with or against the daily DMI trend.
- **Book-level cases** (`lab_c`): `{"members": [...], "case": "dmi" | "ema" | "both"}` takes signals only in the daily trend's direction.
- **Per-member cases** (`lab_c2`): `"case": "dmi_breakouts"`, `"window_10_14"`, or both joined by `+`.

---

## 7. Adding your own entry rule

Follow `docs/research/fno/study_template/lab_x.py`.

1. **Write `entries(m, f)`.** It gets the day's features `f = O27F.day_features(frame, day)`:
   - `f["t"]`: today's 5-minute bars with `open, high, low, close, volume, atr, vwap, vsd, rvol, minute, er4, body`, among others;
   - `f["stamps"]`: the bar times;
   - `pdh` / `pdl` / `pdc`: yesterday's high, low and close;
   - `orh` / `orl`: the first 20 minutes' high and low;
   - `complete_open`.

   It returns `{bar_ts: +1 | -1}`. **Bar i may read only bars ≤ i and earlier sessions.**
2. **Turn it into a signal** with `G._signal(frame, regime, now, m, direction, bar_ts, f)`. That sets the stop (`stop_atr` × ATR) and target (`target_r` × risk), and refuses REGIME_3_CRISIS. You can override `stop_underlying` / `target_underlying` as `lab_i.side_signal` does.
3. **Register it** by wrapping `G.new_signal` at module level (the template's `new_signal`). Build members with `G.new_member(FAMILY, gate, **genes)`.
4. **Prove causality** in `test_*.py`: change the bars after a cut and check that the answers up to the cut are unchanged (the template's `test_entry_is_causal`).
5. **Run the plumbing check:** `O30C_YEAR=2025 python lab_x.py smoke` replays the candidate over January only. It proves the wiring and scores nothing.

---

## 8. The protocol, step by step

1. **Folder:** copy `study_template/` to `docs/research/fno/<yyyy-mm-dd>-<name>/` and rename the files if you like.
2. **The question:** write the owner's question and the hypothesis in the module docstring.
3. **The books:** your candidate(s), with one textbook setting each where possible, plus `REF|LIVE`, `REF|LIVE+tpb_all_days` (it failed the 2024 exam; a comparison only) and the 20 random books. The best candidate after the exam is the four strategies with the stretched-entry rule (`lab_s2.books("shipped")["LIVE|skip"]`).
   - A grid multiplies the chance of a lucky pass; keep it small and say how many variants you tried.
4. **The rule (`RULE`) and the analysis script:** written now.
   - Minimum: the candidate beats its reference in **2024, 2025 and 2026 separately**, is not worse in at least 4 of the 6 half-years, makes at least 40 trades a year, and beats the random books' median.
   - **If you select among variants:** choose on one year and score on the other, both ways (the O30m check). Only a method that passes both ways may choose on both years.
5. **Tests:** `pytest` (causality, books).
6. **Freeze:** `python lab_x.py freeze` writes `freeze.json`. It holds the per-year bindings: the engine and study file hashes, the dataset manifests, the daily bars and the settings. **Commit and push it alone,** without the other agent's working files: stage only your study paths.
7. **Run each year** in slices until `DONE`.
8. **Analyse:** `python analyze_x.py` applies the frozen rule and writes `results.json`.
9. **Sanity check:** your `REF|LIVE` must reproduce the stored numbers exactly (+₹21,762 on 2024, +₹271 on 2025, +₹80,912 on 2026). If it doesn't, something in the setup differs; stop.
10. **Write up:** a study `README.md` (question, freeze commit, tables, verdict, caveats, files). Commit `results.json` and the README.
11. **The docs ritual (AGENTS.md):** a section in `docs/NEXT_AGENT_PLAN.md`, `docs/HANDOVER_CHECKLIST.md` and `docs/SYSTEM_GUIDE.md` (research only, no runtime change), staged without touching other agents' unstaged edits.
12. **Next step for a pass:** a pass is a candidate for an unseen check (the forward panels, real fills), not a go-live. All three years are now seen, so a pass on them is no longer an exam. A runtime change is a separate Dev change → PR → deploy on the owner's word.

**Ideas you find by looking at results** (slicing tables, the investigation): freeze them separately as in-sample "Tier 2" (`lab_c2.py`). Never count them as proof. O30c showed such ideas failing even in-sample once built into the book.

---

## 9. Metrics

- **Per lot:** `net_pnl / lots_at_exit` per trade, summed per day (`analyze_g.per_lot`).
- **What `per_lot` reports:** `net`, `without_best_day`, `worst_day`, `dd` (the largest fall of the running total), green/red months and weeks, and `monthly`.
- **Windows:**
  - 2024: H1 Jan–Jun, H2 Jul–Dec.
  - 2025: H1 Jan–Jun, H2 Jul–Dec.
  - 2026: H1 Jan–May, H2 Jun–Oct.
  - All years: concatenate the trade lists and the session lists.
- **One-lot weeks** (`analyze_g.one_lot_weeks`): the real-money rules played week by week. Each week starts at ₹15,000 and stops below ₹7,000, with at most 3 trades a day, one position at a time, and lot 65 with the shipped charges. It reports up / down weeks and the worst week's end.
- **Slicing versus exact:** cutting a strategy's always-on trades by kind of day is a fast estimate that ignores the book's state (brakes, drawdown halt, slot taken). Anything you would act on must be replayed exactly as a book.

---

## 10. Honesty checks every study carries

| Check | Why |
| --- | --- |
| `REF|LIVE` (and its exact stored numbers) | Proves the setup is the same and gives the bar to beat |
| 20 random-entry books (`Y.null_fixed()`) | A rule that also "works" on random entries is a market or direction effect, not an entry skill |
| Both years separately, and the half-years | A good total can hide one bad year |
| Choose on one year, score on the other | Measures selection luck (O30m: a router chosen on 2026 made +₹1,10,602 there and −₹34,803 on 2025) |
| Freeze committed before replays; bindings asserted at run time | Nothing can be adjusted after seeing a result |
| Exact replay of anything estimated by slicing | The book's own state changes outcomes |

---

## 11. Window ledger (F&O single-leg, as of Oct 31, 2026)

| Data | Status |
| --- | --- |
| NIFTY Jan 1 – Oct 28, 2026 (Breeze year data; the Sep 10 – Oct 26 quote archive) | **Seen**: the ADX gate, the fades and the router choices were all made on it |
| NIFTY 2025 | **Seen** since O30 (Oct 30): the clean test, then the case study and the router |
| SENSEX Jan – Oct 2026 | Partly downloaded (2,384 of 4,057 option requests on Oct 31); the paper book runs SENSEX, but no strategy was chosen on it. The day sides are NIFTY's, so it is not independent for day rules. |
| **NIFTY 2024** | **Seen since Oct 31, 2026.** The one-time exam is used up: sheet 1 `2026-10-30-day-router/freeze-2024.json` (`2a57ede`), sheet 2 `2026-10-30-earning-power/freeze-2024.json` (`ff08fca`), sheet 3 `2026-10-30-risk-spectrum/freeze-2024.json` (`bc5a93a`), scored once each. Nothing may now be called unseen-tested on it. |
| NIFTY 2023 and earlier | Not downloaded, and availability not probed. The only possible further exam year. |
| **Forward sessions from Oct 29, 2026** | **Unseen** for strategy work. Forward panels A–D (O27c, O27g, O28b, O29b) run Oct 28 – Nov 27 (Oct 28 itself was used by O29b and the year data). |

---

## 12. Pitfalls and fixes

| Symptom | Cause and fix |
| --- | --- |
| `bound inputs changed since the freeze` | A bound file changed after the freeze (often `test_*.py` or the analysis). Never edit them after freezing; start a new freeze for a new question. |
| `freeze not committed` | Commit (and push) `freeze.json` before `run`. |
| Bindings never match although nothing changed | Compare JSON-round-tripped values (tuples become lists): the template does `json.loads(json.dumps(..., default=str))`. |
| `files changed since the O29i freeze` | The engine (`python-engine/*.py`) changed, so the stored replays are no longer comparable. Run from a worktree at the study's freeze commit (`git worktree add ../ts-research <sha>`). |
| A run was killed or the PC stopped | Run the same command again; saved replays are reused. Warm-ups in `lab_t` / `lab_f` save one part per session. |
| `database is locked` | Something read the live download for a long time while the downloader was writing. Always read through a sealed mirror. |
| A book with 5+ members came out with 4 | `book_of` keeps at most 4; build `{"members": [...]}` directly. |
| A day with no trades where you expected some | Check the gate's side for that day in `_local/table-<year>.json`. A missing reading closes the gate (ADX needs about 60 daily bars). |
| CRLF warnings on `git add` | Harmless; freezes compare parsed JSON. |
| Workers didn't apply your patch | It was made inside a function. Move it to module level. |
| `JSONDecodeError` on a `results-*.json`, or `FileExistsError` when you rerun | A slice was stopped while it wrote that file (`Y.write_new` is not atomic). Delete only that file and run the same command again: the replays in `evals/` are kept. New code should write to a temporary file and `os.replace` it (`exam_s.run`). |
| A gated book shows months with no trades | Do not assume a bug, and do not assume it is fine. Compute the gate independently from the sealed daily bars (O31: NIFTY's ADX really stayed under 25 from Feb to late Sep 2024, so the live book sat out by design). |
| `check_book` reports `unresolved`, or a replay's `notes` shows `unresolved_at_session_end` | A leg was open at a session's last bar, normally on a half-day. It has no rupee result. Report it, and re-apply the verdict without those days and with the leg closed at the last bid (`2026-10-31-exam-2024/report_x.py`). |
| A good setting looks like a lone spike | Two different causes look the same. Replay a surface at one lot with brakes off, so one changed trade cannot change the rest, and bucket the trades by the setting's own measure (`report_o.py`). O31c: the rule's limit is a real slope, not luck, but it still failed the test fixed in advance, and that result stands. |
| A sized plan's exact replay differs from the simulator by one big trade | The shipped minimum-pool gate (premium x 65 x 25% <= 2% of the money) reads the real equity, so a bigger or smaller account admits different high-premium trades. Report both. |

---

## 13. File index

| Path | What |
| --- | --- |
| `docs/research/fno/study_template/` | `lab_x.py`, `analyze_x.py`, `test_lab_x.py`: copy this |
| `docs/research/fno/2026-10-31-exam-2024/` | O31: `report_x.py` (the three sheets together, three-year tables, half-days, one lot on the real-money terms) |
| `docs/research/fno/2026-10-31-final-book/` | O31b/c: `lab_o.py` (one change at a time, the carried three-year account), `lab_o2.py` (the plateau surface, new ADX sides, random controls), `report_o.py` (stretch buckets) |
| `docs/research/fno/2026-10-30-earning-power/` | O30s: `analyze_s.sim` (the rupee simulator), `exact_s.py` (exact sized replay), `reference_s.py` (hindsight ceiling, option selling), `exam_s.py` (2024 sheet 2) |
| `docs/research/fno/run_slice.py` | run a long command in bounded slices |
| `docs/research/fno/2026-10-29-year-genome/` | O29f: `yeardata.py` (candle model, export), `lab.py` (BookReplay, Runner), 2026 dataset |
| `docs/research/fno/2026-10-29-why-study/` | O29g: `lab_g.py`, `features.py` (day features, `split_table`), `analyze_g.py` (metrics) |
| `docs/research/fno/2026-10-29-sideways-study/` | O29i: `lab_i.py` (range-day families) |
| `docs/research/fno/2026-10-30-nifty-2025-test/` | O30: `lab_t.py` (2025 mirror, export, warm), the 2025 dataset |
| `docs/research/fno/2026-10-30-case-study/` | O30c: `lab_c.py` (year setup, direction cases), `lab_c2.py`, `diagnose_c.py` |
| `docs/research/fno/2026-10-30-day-router/` | O30m / O30f: `lab_m.py` (library, routers), `analyze_m.py`, `persistence_m.py`, `lab_f.py` + `freeze-2024.json` (the 2024 exam) |
| `C:\Users\Urveesh\sentinel-operations\breeze-history-20261029\` | the data download (`DOWNLOAD_GUIDE.md`, `download*.py`, `verify_download.py`) |

---

## 14. Running a one-time exam (the NIFTY 2024 exam, run Oct 31, 2026)

**The 2024 exam is finished and cannot be run again as a test.** The sheets refuse to write their results twice. These are the exact steps, kept as the worked example for another unseen year. Results: [FNO_2024_EXAM_2026-10-31.md](FNO_2024_EXAM_2026-10-31.md).

**Before any data exists:** freeze the books, the rules and the scorer, and commit them (`2a57ede`, `ff08fca`, `bc5a93a`).

Run from the repo root with `python-engine\winvenv\Scripts\python.exe` as `python`. Set `DAY=docs/research/fno/2026-10-30-day-router`, `POWER=docs/research/fno/2026-10-30-earning-power` and `RISK=docs/research/fno/2026-10-30-risk-spectrum`.

1. **Check the download.** Its folder's own venv: `verify_download.py NIFTY 2024-01-01 2024-12-31`. No downloader may be running. Also read the download agent's receipt: it lists data problems for you to decide on.
2. **Seal the data.** Commit nothing from `_local/`.
   - `O30F_YEAR=2024 python $DAY/lab_f.py mirror24`
   - `O30F_YEAR=2024 python $DAY/lab_f.py export24`
3. **Record the fingerprint and data decisions, and commit them before any replay** (`$DAY/data-binding-2024.json`, `d1da1dc`): the hashes, row and session counts, bad-row counts, and a written decision for every oddity (half-days, invalid bars, stray bars, expiry days). Decide these now, while no result exists.
4. **Sheet 1, replay:** `python docs/research/fno/run_slice.py --seconds 550 --env O30F_YEAR=2024 --log $DAY/_local/run-2024.log -- $DAY/lab_f.py run --jobs 5`, repeated until `DONE`.
   - It warms the 2024 memo, then replays the 23 frozen books and the 134-strategy library. The log must say `reused 0 earlier replays`.
   - About 27 minutes at 5 workers, after hours. `--jobs` does not change results; keep to the limits in section 1.
5. **Check the replays' health before scoring:** every book covered every session, no `memo_conflict` and no `named_memo_miss` in `notes`, all entries inside the year.
6. **Sheet 1, score once:** `python $DAY/analyze_f.py`. It applies `RULE_2024` and writes `results-2024.json` once.
7. **Sheet 2, replay:**
   - `python docs/research/fno/run_slice.py --env O30F_YEAR=2024 --env O30S2_MODE=shipped -- $POWER/exam_s.py run --jobs 5`, until `DONE` (about 1 minute);
   - the same with `O30S2_MODE=raw` (about 7 minutes).
8. **Sheet 2, score once:** `O30F_YEAR=2024 python $POWER/exam_s.py score`.
9. **Sheet 3, replay:** `python docs/research/fno/run_slice.py --env O30F_YEAR=2024 -- $RISK/exam_r.py run --jobs 5`, until `DONE` (about 1 minute).
10. **Prove it with `analyze_r.check_book`, then score once:** `O30F_YEAR=2024 python $RISK/exam_r.py score`.
11. **Report them together:** `python docs/research/fno/2026-10-31-exam-2024/report_x.py`. It checks the data hashes, that the sheets reproduce each other trade for trade, and that each sheet's rule reproduces its stored verdict, then re-states every verdict without the half-days.
12. **Look hard at anything odd before believing it,** especially a good result. Then commit `results-2024.json` from each sheet and write it up. Do not change any book or rule.

**If the engine changed after a freeze,** sheets 2 and 3 refuse to run. Run from a worktree at that sheet's freeze commit. Sealed data in `_local/` is not in git, so point the worktree's `_local` at this checkout's.

**Reading a scored rule honestly:** O31's `level_confirmed` came out true because the chosen level lost less per rupee of fall than the bigger one. Both lost money, so it confirms nothing. Report what a pass means, not only that it passed.

---

## 15. Testing size in rupees (O30s)

Everything above compares strategies per lot. A question about money ("how much can it earn on ₹2.5 lakh, and what does that cost?") needs rupees, and size changes the answer in ways per-lot numbers hide: a losing run takes the cash, the account can then afford fewer lots, and the recovery arrives too small. **Trades that made +₹10,125 on one lot lost ₹2,08,331 on ten.**

**The method:**

1. **Replay once as RAW.** One lot, kill switches off, up to 6 trades a day (`lab_s.RAW`, applied in the worker initializer, never at import, so the freeze's bindings still read the shipped settings).
2. **Size afterwards.** `analyze_s.sim(rows, rule, brakes, stress, half, capital, day_cap, reserve)` walks the trades in time order. Before each entry it settles closed trades, applies brakes, sizes from the money known then, and checks own cash.
   - `rule`: `("fixed", lots)`, `("risk", share of the money lost at the premium backstop)`, or `("shipped",)`, the shipped sizing.
   - `brakes`: `NONE`, `SHIPPED`, `THROTTLE` (size cuts in a fall, no stop), `THROTTLE+DAY`.
   - `stress`: extra rupees per lot per trade (an added lot pays it too).
   - `half`: half size when the entry is stretched.
3. **Prove the simulator.** `analyze_s.parity` runs the shipped sizing and brakes through it and compares with stored exact replays. The O30s difference was at most ₹2,416 a year and one trade.
4. **Run the same sizing on the 20 random books.** Size must beat luck under the same size.
5. **Replay exactly what you would act on** (`exact_s.py`, shipped code at real lots).
   - Without brakes the simulator was about one trade from exact.
   - With brakes it can be wrong: one frozen pass went from +₹11,895 simulated to −₹41,332 exact, because a skipped trade changes which later trades happen.
6. **Choose size only across years.** The best combination on 2026 alone made +₹5.42 lakh there and −₹2.42 lakh on 2025 (a 97% fall).
7. **Report the plan's fall, not only its profit:** the fall with and without the extra cost, the worst day and month, and the chance table (`analyze_s.boot`, one-year paths redrawn week by week from both years, which is a good case because those years are seen).
8. **Check one-day dependence.** Feb 1, 2026 alone was 58% of the live book's 2026; `analyze_s2.per_lot` reports `without_budget_day` and `without_best_day`.

**Kelly** (`analyze_s.kelly`) gives the lots above which long-run growth falls. Use it as a ceiling only: it is an estimate from seen data, and the literature advises betting a fraction of it.

**Reading a bar's stretch:** `lab_s.stretch_at(frame, now, direction)`, and the pass-over rule is `lab_s2.route` (book field `"skip": 0.5`). Both use completed bars only. They are recorded on each trade as `stretch`.

**Adding your strategy:** copy the book definition into your own study's `books()` with `"o30s": "raw1"`, apply `lab_s.apply_raw` in your worker initializer, freeze, run, then call `sim`.

**Testing a whole risk ladder exactly (O30r, `2026-10-30-risk-spectrum/lab_r.py`):** every limit is a setting, so a level is a `cfg` on the book, applied per replay by `lab_r.run_book`.
- Put extra cost inside the money path (`"cost": [per_lot, per_lot_per_lot]`). Subtracting it afterwards is wrong at high risk, because a smaller account buys fewer lots.
- Carry the account across years (`"carry": <2025 replay key>`), so a wipe-out stays wiped out. Run 2025 first.
- Prove every replay with `analyze_r.check_book`: charges, day cap, own cash, and lots from the planner's formula.
- As-replayed rows at high risk reach hundreds of lots with no slippage. Never report them as achievable.
- Results: [FNO_RISK_SPECTRUM_VERDICT_2026-10-30.md](FNO_RISK_SPECTRUM_VERDICT_2026-10-30.md).
