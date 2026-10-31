# O31g: complementary entries on days the main book sits out

Research only. Source checkout: Dev `416984f`; Production is read-only.

Problem: the ADX-30 main book sits out most sessions. Previously tested fades,
opening retests, failed breaks and squeezes did not reliably fill that gap.
Test TWO new entry mechanisms, not a search over threshold combinations:

1. **INTRADAY_DMI:** completed five-minute ADX(14) >=25 and rising against three
   bars ago, directional indicator at least 1.5 times its opposite, a close
   beyond the preceding six bars and on the correct side of session VWAP.
   ADX uses continuous prior-session futures bars, with at least 60 bars of
   warmup. Entries 09:45–13:30, at most one per direction/session. Stop 1.5 ATR,
   target 2R; existing RUN exit policy.
2. **SHOCK_RECOVERY:** five-minute range >=2 times the median range of the
   preceding 12 consecutive same-session bars; a body >=60% of range, closing
   in the outer 20%. Within six subsequent consecutive bars, require two
   closes in the opposite direction, recovery through the shock midpoint and
   a close beyond the previous bar's extreme. Trade the recovery, with a stop
   beyond the shock/recovery extreme plus 0.1 ATR, at least 0.5 ATR and no more
   than 2 ATR away. Target 1.5R, existing LIVE exits. Mirrored calls AND puts;
   no direction selected from results. Entries 10:20–13:30, one per direction.

Both operate only when yesterday's daily ADX is below 30, with missing daily
readings ineligible. Test alone at one lot with diagnostic brakes disabled,
and integrated with the main book using its shared cash, existing lot limits,
premium/risk caps, entry/exit deadlines and brakes. The skip rule stays on.
Do not sum independent books as a portfolio. TPB-put complement is a control.

Contracts/files: `lab_gap.py`, `analyze_gap.py`, `test_gap.py`, `configuration.json`,
`freeze.json`; immutable existing three-year candle datasets, saved NIFTY daily
inputs, exact main-book control, existing random closed-day controls. No
application source, settings, migrations, broker calls or notifications.

Acceptance fixed before scoring: exact main-book parity (+16,371/+5,710/+30,540)
and all financial/causal checks must hold. A research candidate needs positive
standalone net EVERY year after Rs200/lot/trade, >=8 trades/year and >=40 total,
>=5/6 nonnegative half-years, positive net after removing each year's best day,
weekly t >=2 and total above the best stored random closed-day control. Its
integrated book must improve main in EVERY year, paired weekly t >=2, with
drawdown <=main +1 percentage point EVERY year. Rs300 sensitivity is reported.
None of these tests corrects for the hundreds of previous strategies tried.

Rollout: frozen offline study only. A pass permits prospective paper research,
not deployment. Rollback: stop the research worker; all finished results remain.
No changes to the fixed 2023 exam or its candidate list; no 2023 data acquisition.
Remaining: run, reconcile, report EVERY failure, preserve source/data hashes,
update the system guide/active plan/checklist. Raw prices and trades stay ignored.
