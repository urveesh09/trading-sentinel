# Successor inheritance — Trading Sentinel, October 4, 2026 (IST, late evening)

The previous agent's session ends here because the owner is shutting the PC down.
This is everything the next agent needs to continue without the conversation.
Revalidate every claim against the checkout and runtime before acting on it.
The earlier [October 3 inheritance](2026-10-03-successor-inheritance.md) still
holds for older history.

## 1. Do this first (in order)

1. **Production gateway was crash-looping on October 4 at about 22:35 IST.**
   `node-gateway` restarted endlessly with `SQLITE_READONLY` from
   `services/account-cash-reservations.js`. Fixed in Dev (see §4, "Container uid
   fix"). Confirm the owner merged and **rebuilt** the images
   (`docker compose up -d --build`; a plain restart keeps the old images). Then
   check `docker ps`: every container healthy, gateway not "Restarting".
2. **Read the round-3 Kite scoring results** (October 5, after 17:07 IST). The
   Windows Task Scheduler job `Sentinel-Round3-KiteScoring` runs
   `scripts/run_round3_kite_scoring.ps1`:
   - it waits until 21:00 for that day's Kite login, acquires January–July 2026
     history, freezes `momentum-smart-t3` and `penny-noise-t3`, commits and
     pushes the freeze, scores each study once, then commits and pushes
     `results.json`;
   - log: `docs/research/kite/2026-10-05-round3-run.log`;
   - results: `docs/research/kite/2026-10-05-momentum-smart-t3/` and
     `.../2026-10-05-penny-noise-t3/`.

   Your job: read the log and results, record each verdict (do not re-score or
   re-tune), update the study docs, RESEARCH_TESTING_METHOD ledger (Kite
   Jan–Jul 2026 becomes *seen*), SYSTEM_GUIDE, NEXT_AGENT_PLAN and
   HANDOVER_CHECKLIST, then commit and push. If the task did not run (PC off, no
   login, Docker down), say so and ask the owner whether to rerun the script
   after their next Kite login. The previous session's in-chat reminder for
   this was cancelled, so nothing else will prompt it.
3. **Check the first forward paper days** (only counts and health; no tuning):
   EDGE overnight book entries at 15:20 and exits at 09:17, the `MOM_SELECTIVE`
   shadow, and the smart-Penny shadow.

## 2. Authority and boundaries (owner rules, verbatim where possible)

- **"Assess Production. Change Dev. Promote through GitHub. Never edit Production
  directly."** Dev: `C:\Users\Urveesh\Desktop\trading-sentinel`. Production:
  `C:\Users\Urveesh\Desktop\Production_Trading-sentinel`, read-only for you.
  Production data is read through Docker with the volume mounted `:ro`.
- **Branch flow.** Dev works on `codex/production-correction-hedge-p0` and
  pushes there. Production runs `evolve/smart-strategies`. The owner merges via
  GitHub PR (latest: PR #101, merge `25a795d`, which contains Dev `285b27c`) and
  pulls/rebuilds Production themselves. `origin/main` is stale (June 14); it is
  not the deploy branch, so ignore "not in main" signals.
- **Money.** Own cash only: no margin, no leverage, no averaging down. Never
  loosen F&O hard limits (caps, kill switches, defined loss).
- **Live trading is OFF; everything runs on paper** for the next few days. The
  owner wants to see the impact of the new strategies. Do not switch any live
  flag on. `OWNER_LIVE_ENTRY_HALT=true` blocks every real entry (including manual
  EXEC taps) while paper keeps running.
- **Code quality.** Top quality, remove unused code instead of appending cruft,
  re-read sources instead of guessing. The owner explicitly warned about
  hallucination: verify, then claim.
- **Documentation ritual on every commit** (AGENTS.md): update SYSTEM_GUIDE,
  NEXT_AGENT_PLAN, HANDOVER_CHECKLIST; regenerate the atlas
  (`python scripts/build_system_code_atlas.py`); record commit identity,
  verification commands and results, and whether the change is Dev-only, pushed
  or deployed.
- **Security.** Never print or log the Kite access token or bot tokens; log only
  exception types where text may contain URLs or tokens. Never send the owner's
  email to external services.
- **Commit trailer:**
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` and
  `Claude-Session: https://claude.ai/code/session_015nJ1dM85rM3Kin6rcgqED2`.

## 3. The owner's vision

- Each module should act like a **smart, fast human trader** who earns consistent
  daily profit "like a daily job": quick, well-judged entries and exits, not an
  ever-growing stack of filters.
- The owner likes the existing hard risk controls; keep them.
- F&O goal: about ₹20k/month on ₹2.5L, no crazy losses, no long losing streaks.
- It is still a "minor testing phase". Creative or drastic ideas are welcome,
  but **every change is judged by the pre-registered method**
  ([RESEARCH_TESTING_METHOD](RESEARCH_TESTING_METHOD.md),
  `scripts/run_preregistered_study.py` list / freeze / run). Freeze and commit
  before scoring; score once; four checks (net > 0, net excluding the best
  winner > 0, beats baseline, drawdown ≤ max(1.5 × baseline, floor)).
  "Promising" only means keep paper/shadow trading.
- Tests passing is never proof of profit; deployment is never proof of
  qualification.

## 4. What was done on October 4 (all pushed; all inside Production `25a795d` except the uid fix)

| Commit | What |
| --- | --- |
| `72ff8d0` | NIFTY and SENSEX future candles recorded after each session (research). |
| `e8d93c3`, `792bffb` | F&O growth slice: adaptive risk, SENSEX paper book, multi-lot capped-loss book; drawdown cut shrinks to one lot instead of halting. |
| `a4f1a54` | Momentum direct-trading path (`MOMENTUM_AUTO_EXECUTE`, default **false**); round-3 candidates `MOM_SELECTIVE`, `PEN_NOISE_STOP`; `scripts/acquire_kite_history.py`. |
| `a674740` | Owner selected the Penny noise-floor stop for the runtime (paper). |
| `9c5becb` | Forward paper evidence: `MOM_SELECTIVE` Momentum shadow variant, `PENNY_SMART_SHADOW_ENABLED=True`, the owner's smart-Penny controller committed as-is ([doc](2026-10-05-forward-paper-evidence.md)). |
| `2298e77`, `1e5c904`, `b5969b1` | `EDGE_OVERNIGHT` research candidate, freeze and one-time score ([doc](2026-10-05-edge-overnight-study.md)); round-3 Kite job script. |
| `285b27c` | EDGE overnight **paper book** (₹25k) and corrected delivery (CNC) costs. |
| this commit | Container uid fix for the gateway crash, plus this inheritance doc. |

### Key findings to carry

- **EDGE's return is overnight.** Candidates gain close → next open (+0.90%;
  +1.98% at strength ≥ 0.8) and lose next open → close (−0.38%). The shipped
  clock buys at 09:30, so it misses the gain and holds the fade.
  - `edge-overnight-t1` on untouched Mar 2024–Dec 2025, ₹25k book: baseline
    −₹22,008; `EDGE_OVERNIGHT` +₹2,22,864 (19.1% peak drawdown); S60 arm
    +₹2,52,507.
  - Verdict `NOT_SUPPORTED_STAYS_OFF`: it failed only the drawdown check,
    because that check divides by *starting* capital (153%). Do not re-score.
    Future compounding studies must declare a peak-relative drawdown before
    freezing.
  - The ₹3k book is ruined by the ₹15.93 DP charge per sell: about ₹25k minimum.
- **EDGE overnight paper book** (`edge_overnight_paper.py`): 15:20 paper buy of
  up to 3 picks (LTP + 25 bps, ≤ 1% of day's traded value, own cash), 09:17 paper
  sell at the opening auction (−5 bps), separate store
  `<DB_PATH>.edge-overnight-paper.db`, Telegram summaries, no order capability.
  Compare with EDGE_PAPER after 10+ sessions, from Oct 5 only.
- **Delivery costs were wrong before Oct 5.** `calc_penny_costs(is_intraday=False)`
  now charges no brokerage, 0.1% STT on both legs, 0.015% buy stamp duty and
  ₹15.93 DP per sell. Older EDGE/CNC paper P&L was overstated and was not
  migrated.
- **Penny: fewer trades is better.** The owner's smart-Penny experiment
  (`penny-smart-t4`) lost: incumbent +₹91.72 / 38 trades vs combined −₹47.50 /
  153. Ranking was a no-op (the cap never filled). Seen September data is
  exhausted; only forward days and Kite history are honest tests.
- **Momentum:** ordinary breakouts lost after costs in a falling market;
  `MOM_SELECTIVE` took zero trades on seen data (no verdict either way).
- **F&O:** shipped book still best in replay (+₹13,306 vs +₹7,128). Go-live bar:
  40 days / 60 trades / PF ≥ 1.2, then a separately authorised 1-lot pilot.
- **Already-seen data** (never tune on it): Penny MIS Sep 7–Oct 1 2026; daily
  modules Jan–Sep 2026; EDGE 2024–2025 daily; Momentum Aug 10–Oct 1 2026; F&O
  archive Sep 10–Oct 1 2026. After round 3 runs, Kite Jan–Jul 2026 intraday is
  seen too. Still untouched: Range/Swing 2024–2025 daily, F&O sessions from
  Oct 5 2026.

### Container uid fix (this commit)

- **Cause.** `919e042` (Oct 3) made the gateway write the shared `cache.db`
  (account cash reservations). The gateway's `appuser` was an Alpine system
  user (uid 100); `cache.db` belongs to the engine's `quantuser` (uid 1000,
  mode 644). The gateway could not write it and crashed on start. Its WAL/SHM
  files, created as uid 100, would also block the engine after its next restart.
- **Fix.**
  - Both images now use uid/gid 1000: `quantuser` explicitly, and the gateway's
    `appuser` after removing the base image's `node` user.
  - Each entrypoint (running as root) chowns its databases' `-wal`/`-shm` files;
    the gateway also repairs `cache.db-wal`/`-shm`.
- **Verified locally.** Built both images (`id` → uid 1000 in each). On a
  scratch volume reproducing Production's ownership (cache.db 1000/644, WAL/SHM
  and app.db files 100:101), the gateway entrypoint then a better-sqlite3 write
  succeeded, and the engine entrypoint then a sqlite3 write succeeded.
- **Rollout.** Merge, then rebuild images. Rollback: revert the commit and
  rebuild (the gateway then crashes again, so do not).

## 5. Scheduled and pending items

| When | What | Where |
| --- | --- | --- |
| Oct 5, 15:20 / Oct 6, 09:17 | First EDGE overnight paper entry and exit | Production scheduler (needs the rebuilt deploy) |
| Oct 5, 17:07 | `Sentinel-Round3-KiteScoring` (needs PC on, owner logged in, Docker running, Kite login before 21:00; runs on battery, wakes from sleep, runs late if missed) | Windows Task Scheduler |
| After 5+ sessions | `MOM_SELECTIVE` vs `MOM_BASE`; smart-Penny shadow vs Penny paper | `/api/experiments/momentum`, decision-quality report |
| After 10+ sessions | EDGE overnight book vs EDGE_PAPER (corrected costs) | overnight store, EDGE paper rows from Oct 5 |
| Open | Fix the three Penny paper `exit_price` blob rows; Penny D1 live-risk reconciliation; F&O SENSEX replay export and BFO live exit support | NEXT_AGENT_PLAN |
| Owner's call | `MOMENTUM_AUTO_EXECUTE` stays OFF; any live switch | owner |

## 6. Verification state

- Engine suite at `285b27c`: 4,930 pass / 4 skip. There are 4 known
  pre-existing failures (`test_dev_acceptance_harness`, `test_integrated_dev_demo`,
  the `test_mark_to_market` F&O DR fixture, `test_proactive_intelligence`). The
  run also caught the cron-gating guard, which was fixed; its targeted tests
  pass. The full suite was not rerun after that fix.
- Run the suite from `python-engine` with `python -m pytest -q` (no `-x`: the
  first pre-existing failure would stop it). Scheduler goldens:
  `TS_UPDATE_GOLDEN=1`.
- Windows notes: the Dev checkout uses `core.autocrlf=true`, so Python
  `write_text` produces CRLF files locally. Git normalises them on commit, but
  test containers built from the working tree need LF entrypoints. Use
  `contextlib.closing` for sqlite on Windows (temporary files stay locked
  otherwise). In Git Bash, prefix Docker commands that use `/data` paths with
  `MSYS_NO_PATHCONV=1`.

## 7. Recommended first instruction for a fresh session

> Read AGENTS.md, then docs/2026-10-04-successor-inheritance.md, SYSTEM_GUIDE,
> NEXT_AGENT_PLAN and HANDOVER_CHECKLIST. Confirm Production is healthy after the
> uid-fix rebuild, then read and record the round-3 Kite scoring results
> without re-scoring.
