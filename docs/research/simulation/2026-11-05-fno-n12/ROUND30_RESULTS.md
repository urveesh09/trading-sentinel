# Round 30 results. The trend lock was the stronger component

The study froze both arms at `7011f4b`. N11 and N11T receipts reconciled in every window. The trend-only arm also reproduced the earlier 2023–2026 trend-lock report’s annual net, daily net, counts, worst day and closed drawdown. The partial 2022 trend extension is new research on previously seen dates.

| Window | N11T net | Trend exit only | Trend exit and entry mix |
|---|---:|---:|---:|
| Partial 2022 | −₹10,602.29 | −₹10,297.38 | −₹10,297.38 |
| 2023 | −₹11,536.98 | −₹11,131.51 | −₹11,616.41 |
| 2024 | +₹95,040.33 | +₹95,040.33 | +₹95,040.33 |
| 2025 | +₹63,478.57 | +₹65,415.09 | +₹67,344.90 |
| Available 2026 | +₹127,762.74 | +₹129,167.29 | +₹129,505.44 |
| Five independent ₹250,000 accounts | +₹264,142.37 | +₹268,193.82 | +₹269,976.88 |

The entry-and-exit mix added ₹5,834.51 (2.21%) and the trend exit alone added ₹4,051.45 (1.53%). Both had a worst day of −₹5,640.85 and maximum annual closed drawdown of 6.97% versus 7.09% for N11T. Both met the annual downside floor and resolved every position. The mix lost ₹1,295.40 versus N11T without its five best incremental days. The trend-only improvement still held at ₹710.38. Neither reached the ₹316,970.84 materiality gate. Keep the trend exit as a component, with its smaller and more consistently distributed improvement. [Paired gates](round30-gates.json).

On November 5 the earlier fixed-admission held-path test reconciled all three native exits. The trend exit changed the modeled singles net from ₹4,821.18 to ₹5,872.16, a ₹1,050.98 increase. The mix’s entry components had no eligible change on the recorded November 5 refusals and paths. With the separately recorded spread held fixed, the conditional total is ₹8,418.07 versus recorded ₹7,367.09. This conditions on the observed admissions and paper bid model, so changes to later admissions cannot be priced from this check. [Held-path results](../2026-11-05-fno-expiry-followup/regular-today-results.json), [entry eligibility](round24-nov5.json).

Use `pytest -q test_round30.py` and `python round30.py` with `N12_YEAR` set to each window. All five frozen annual runs completed. Two dispatch tests passed. Neither arm reached new doubled-cost or untouched validation in this round. The earlier four-window trend exit stress remains separate. Dev research only, with no broker orders, runtime settings, migration, deployment or push from this study.
