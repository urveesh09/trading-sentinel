# Round 28 results — option activity screen rejected

The frozen fixed-strike option activity features did not improve the walk-forward futures forecast and do not advance to option pricing. The study compares an intercept-plus-morning-futures-return reference model to the same model augmented with changes in call/put open-interest balance and unsigned traded-volume balance. It does not identify buyer-initiated trades because the archived minute data do not provide that field.

| Window | Predictions | MSE improvement | Sign accuracy change | Paired points excluding best five | Strong signals | Strong points after 15-point hurdle, excluding best five |
|---|---:|---:|---:|---:|---:|---:|
| 2022 partial | 53 | −1.88% | −9.43 pp | −294.10 | 1 | −35.00 |
| 2023 | 191 | −1.27% | −2.62 pp | −1,096.30 | 0 | 0.00 |
| 2024 | 193 | −0.68% | +1.04 pp | −520.00 | 31 | −863.30 |
| 2025 | 194 | −6.78% | −6.70 pp | −3,656.20 | 11 | −441.85 |
| 2026 available window | 159 | −0.33% | −5.03 pp | −447.40 | 2 | −120.50 |
| Aggregate | 790 | −2.56% | −3.67 pp | −3,858.50 | 45 | −1,249.25 |

Aggregate reference MSE was 6.18699411×10⁻⁶; activity-model MSE was 6.34562428×10⁻⁶. Aggregate strong-signal points after the hurdle were −376.25 before removing the five best incremental days and −1,249.25 after. The advance rule required at least 200 predictions, at least 2% MSE improvement, at least a two-point accuracy gain, positive paired points after the best-five exclusion, at least 20 strong signals, and positive strong-sample points after its best-five exclusion. Only prediction count and strong-signal count passed. No option lifecycle or account P&L was scored.

Coverage receipts show partial historical inputs: 2022 had 30 calendar exclusions, 113 complete feature/target sessions and two missing chain-clock/OI sessions; 2023 had 191 complete sessions plus 52 calendar exclusions and two missing chain/OI sessions; 2024 had 193 complete sessions, 52 calendar exclusions, one missing chain/OI session and two missing futures clocks; 2025 had 194 complete and 54 calendar exclusions; 2026 had 159 complete, 43 calendar exclusions and one missing futures clock. The 2022 panel is partial and 2026 is only the available window.

## November 5 evidence

The separate saved Nov 5 check binds to the same read-only export manifest SHA-256 `8411f16cd034ad7ab5cde936a92c46148ce7ad70effd71bcb2428880d887bfe3`. It identifies the dated non-expiring option series as 2026-11-09 and fixes the basket at strikes 24,350, 24,400 and 24,450 from the 09:29 future mark of 24,380.8. The future marks at 09:29, 09:59, 10:01 and 11:00 are present. However, zero of the 186 required end-of-minute observations across six contracts were available in the export. The state is `UNAVAILABLE`; no Nov 5 activity features, direction, or P&L are inferred.

## Verification and freeze

- R28 research contract: [ROUND28.md](ROUND28.md); freeze: [round28-freeze.json](round28-freeze.json); aggregate/annual outputs and paired observations: [round28-results.json](round28-results.json); Nov 5 receipt: [round28-nov5.json](round28-nov5.json).
- Freeze source hashes were checked against commit `d7679ef39dadf2384730c353cd47d8fe9c63fcfe`. Recalculating aggregate metrics from all 790 saved paired observations using the frozen R28 metric logic reproduces the persisted aggregate exactly. The data manifest/database identities are those recorded in the freeze and annual outputs were not rerun.
- Focused tests, run with Dev’s `python-engine/winvenv/Scripts/python.exe`: `-m pytest docs/research/simulation/2026-11-05-fno-n12/test_round27.py docs/research/simulation/2026-11-05-fno-n12/test_round28.py -q -W error` — 5 passed.
- Dev research only. No production files, runtime settings, broker/order paths, pushes or deployment were changed. Annual scoring was not repeated because the frozen output already exists.
