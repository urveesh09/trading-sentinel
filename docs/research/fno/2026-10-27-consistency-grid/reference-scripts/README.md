# Reference scripts (Oct 27, 2026)

These are copies of the exploration and analysis scripts used on Oct 27, kept so another agent can see exactly what was computed. They are **not** frozen study runners, and they ran on **seen** data, so nothing here is evidence. The frozen runners are `scripts/run_fno_consistency_grid.py`, `scripts/run_fno_evolution.py` and `scripts/run_fno_forward_panel.py`. See `docs/FNO_STRATEGY_TESTING_PLAYBOOK.md`.

The paths inside are absolute to this machine (`C:\Users\Urveesh\Desktop\trading-sentinel\…`) and the datasets they name; adjust them before reuse. Run them with `python-engine\winvenv\Scripts\python.exe`.

| Script | What it does | Data |
| --- | --- | --- |
| `explore.py`, `explore_lib.py` | Hindsight check: how often +₹200 net was reachable within 15 minutes, and which comes first when the side is picked in advance. `explore_lib.py` holds the shared helpers: chain snapshot, strike by delta with the spread cap, net after charges, session bars with ATR and VWAP. | `2026-10-24-entry-arms/_local` (Sep 10 – Oct 23) |
| `arms.py` | 12 quick-scalp single-leg designs: MOMO / PULLBACK / FADE × four exits | same |
| `arms_spread.py` | The same signals as 100-point debit spreads with spread-style exits | same |
| `proto_replay.py` | First CURRENT vs no-EMA full replay, before the grid existed | same |
| `why_quiet.py` | Read-only, run inside the Production `python-engine` container. Lists the live `fno_signals` decisions around each day's break. Run it as `docker exec -i -u quantuser -w /app python-engine python - <day>… < why_quiet.py`. | Production `cache.db`, `mode=ro` |
| `fno_settings_hash.py` | Per-key SHA-256 of every effective `FNO_*` setting; names and hashes only, never values. Run it in Dev and in Production, then compare. | settings |
| `analyse_grid.py`, `extra_grid.py` | The tables in the O27 README: ranks, best per family, axis effects, EMA on/off by window, concentration | the O27 `results.json` and `_local/arms` |
| `winning_days.py` | What window A's winning entries had in common, measured at entry time | the O27 arms (A only), the dataset |
| `analyse_evo.py` | The tables in the O27b README: generations, holdout, top genomes, allele effects | the O27b `results.json` and `_local/FULL` |
