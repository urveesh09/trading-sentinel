# Round 27 results — banked retest rejected

The frozen `BANKED_RETEST` arm did not clear its development gates. The five annual books each reset to ₹250,000 and are independent NIFTY research runs; 2022 is partial, and 2026 is only the available window. N11T is the paired control. These totals are not a unified portfolio result.

| Window | N11T net | BANKED_RETEST net | Change | BANKED_RETEST trades | Worst day | Closed drawdown |
|---|---:|---:|---:|---:|---:|---:|
| 2022 partial | −₹10,602.29 | −₹10,602.29 | ₹0.00 | 28 | −₹4,410.47 | 7.09% |
| 2023 | −₹11,536.98 | −₹11,536.98 | ₹0.00 | 28 | −₹3,526.29 | 6.89% |
| 2024 | +₹95,040.33 | +₹95,040.33 | ₹0.00 | 29 | −₹3,148.16 | 2.13% |
| 2025 | +₹63,478.57 | +₹61,447.60 | −₹2,030.97 | 74 | −₹5,640.85 | 5.33% |
| 2026 available window | +₹127,762.74 | +₹127,762.74 | ₹0.00 | 51 | −₹4,495.26 | 2.91% |
| Sum of independent runs | +₹264,142.37 | +₹262,111.40 | −₹2,030.97 | 210 | −₹5,640.85 | 7.09% max |

The only incremental ticket bought one 65-unit NIFTY put on January 6, 2025, at 12:22:59 IST. Its premium backstop closed it at 12:39:59. The gross loss was ₹1,735.50 and the net loss was ₹2,030.97, including ₹205 modeled extra cost and ₹90.47 fees. Its planned backstop allowed ₹2,000 of loss, and the modeled bid crossed that level. The candidate added no ticket in the other four windows. Native controls matched.

The frozen gate receipt reports a ₹316,970.84 net target (20% above the ₹264,142.37 N11T aggregate), while the candidate finished ₹2,030.97 below control. The best-five-excluded paired increment is also −₹2,030.97. The annual floor, maximum drawdown, worst-day and no-unresolved-exposure checks passed; materiality and best-five-excluded checks failed. The arm did not pass development, so doubled stress and untouched validation were not scored. No qualification follows.

## November 5 observed-session check

The read-only finished-session export at `20261105T103005Z` has manifest SHA-256 `8411f16cd034ad7ab5cde936a92c46148ce7ad70effd71bcb2428880d887bfe3`. Its `fno-replay.sqlite` hash matches the manifest. The three NIFTY `FNO_PAPER` positions reconcile with the saved Nov 5 receipt and `round24-nov5.json`:

- Position 57 closed at 11:00:33 with −₹765.59 net.
- Position 58 closed at 12:03:23 with +₹1,028.70 net. Its underlying exit was 52.5 points beyond entry, about 1.42 times the initial 37.04-point structural risk. Together, the two positions closed by then left ₹263.11 net realized for the session, below the rule’s ₹1,800 settled-profit prerequisite.
- Position 59 remained open through 14:00 and closed at 14:20:43 with +₹4,558.07 net. That later result cannot fund a setup inside the frozen 10:15–14:00 research window.

Therefore there was no eligible booked-gain retest opportunity before the cutoff. The recorded NIFTY singles total of +₹4,821.18 includes the later exit and is not an eligible pre-14:00 profit pool. This is an observed-ledger decision check, not a counterfactual entry replay.

## Verification and freeze

- R27 research contract: [ROUND27.md](ROUND27.md); frozen inputs: [round27-freeze.json](round27-freeze.json); annual outputs: [2022](round27-2022.json), [2023](round27-2023.json), [2024](round27-2024.json), [2025](round27-2025.json), [2026](round27-2026.json); gate receipt: [round27-gates.json](round27-gates.json).
- The source hashes in the freeze were checked against commit `2821b461ec65615c48801f72d3959564c0a08f7e`. Annual candidate nets sum to ₹262,111.40; annual N11T nets sum to ₹264,142.37. The added ticket’s net equals the sole annual change to rounding precision. Costed ticket and ledger amounts were checked against their gross, fee and modeled-extra-cost components.
- Read-only export source: `C:/Users/Urveesh/sentinel-operations/fno-forward-panel-20261028/docs/research/fno/2026-10-28-forward-panel/_local/exports/20261105T103005Z`; only manifest and SQLite reads were used.
- Focused tests, run with Dev’s `python-engine/winvenv/Scripts/python.exe`: `-m pytest docs/research/simulation/2026-11-05-fno-n12/test_round27.py docs/research/simulation/2026-11-05-fno-n12/test_round28.py -q -W error` — 5 passed.
- Dev research only. No production files, runtime settings, broker/order paths, pushes or deployment were changed. Annual replays were not repeated because the frozen outputs were already present.
