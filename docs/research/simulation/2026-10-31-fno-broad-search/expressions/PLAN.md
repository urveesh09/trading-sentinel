# O31i-E: additional option-expression mechanics, frozen before pricing

Research only; no change to the48-genome parent experiment, its selection or
source files. The owner's broad authorization includes testing option types.
Existing parent71fa7df tests debit and inverse-credit verticals. This separate
slice adds SAME-FORECAST credit verticals (bull put for a bullish signal, bear
call for a bearish signal) and neutral ironfly/condor expressions at the SAME
reproduced entry/exit clocks. No new entry decision is inferred from old trades.

Freeze50/100/150-point vertical widths; iron structures offsets0/50/100 points
from contemporaneous futuresATM, widths50/100 points; extraRs200/400 per complete
structure; normalized65 units. Four-order fees for verticals, eight-order for
four-leg structures, actual exact-minute positive-volume candles, adverse
modeled bid/ask. Enforce vertical midpoint bounds at BOTH clocks; absent,
nonpositive-volume or incoherent quotes remain UNAVAILABLE, never zero.

Full width cash per vertical reserved, two widths per iron structure (deliberate
over-collateralization); fixedRs200 planned fee buffer per vertical, credit never
reused for financing. Entry-only risk bound plus buffer/extra must fitRs5000 for
the current-risk-compatible subset. Not historical broker margin/legging proof.
The hedge and cash are virtual joint fills, not permission to sell naked options.

Original single-leg economics must reproduce the parent record on the common
cohort. Every row binds parent-eval SHA256, record index, exact contract/quantity,
entry/exit clock, entry/exit price and stored risk fields BEFORE recording its
paired delta. Retain raw evidence privately and publish summary/coverage and
per-member slices (including EFF), never sum paired returns into main equity.
After parent control parity, seal their file and per-record economic hashes in
committed parent-evidence.json BEFORE pricing. Reject mismatched records; a
matching identifier alone does not validate economics. Stored closing stop
fields are not represented as immutable initial stops; spread exits are not
being re-simulated in this diagnostic.

Exploratory lead rule identical to parent diagnostic:>=95% requested cohort is
priced AND entry-risk-compatible EACH year;>=12/year and>=40total; positive after
Rs400 extra in EVERY year, positive without each year's best day, better than
the same-cohort original single leg EVERY year. Even a pass is NOT qualified:
spread-specific exits/admissions, actual margins, partial fills, shared cash and
fresh samples still need a real lifecycle study. No2023 exam or candidate changes.

Files: expression_lab.py, test_expression.py, freeze.json, summary/crosschecks.
Acceptance: pure cash/payoff/fee tests, missing-data refusal, entry-risk causality,
exact source/input bindings and baseline repricing. Commit source/freeze and
update guide/plan/checklist before any pricing. Parent workers continue read-only;
this folder is outside the parent's bound flatPython source set.

Rollout/rollback: offline Dev diagnostics only, stop worker; no app source,
settings, migrations, Production edits, deployment, orders or notifications.
