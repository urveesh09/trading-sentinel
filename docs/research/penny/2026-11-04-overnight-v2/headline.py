"""Headline: today's book at its measured entry cost (BASE, E36) against v2 (TWO_NIGHT) at
E36 (no execution change) and PC (post-close entry), fixed Rs 25k, every window."""
import json, sys
from dataclasses import replace
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab, round2
from exam import FINALISTS
from arms import MODELS
out = {}
for panel, s, e, tag in (("kite", "2025-07-01", "2026-09-30", "Kite Jul 2025-Sep 2026 (dev)"),
                         ("yahoo", "2023-01-01", "2026-10-30", "Yahoo 2023-Oct 2026 (dev)"),
                         ("yahoo", "2019-04-01", "2022-12-30", "Yahoo 2019-2022 (exam, now seen)")):
    days = lab.load(HERE / f"_local/days-{panel}.pkl")
    row = {}
    for name, arm, model in (("today_book_E36", FINALISTS["BASE"], "E36"), ("v2_rules_E36", FINALISTS["TWO_NIGHT"], "E36"),
                             ("v2_postclose_PC", FINALISTS["TWO_NIGHT"], "PC"), ("today_book_PC", FINALISTS["BASE"], "PC")):
        eb, xb = MODELS[model]
        row[name] = lab.run_book(days, replace(arm, entry_bps=eb, exit_bps=xb, compound=False), start=s, end=e, keep_trades=False)["summary"]
    out[tag] = row
    b = row["today_book_E36"]["net"]
    print(tag)
    for k, v in row.items():
        print(f"  {k:16s} net={v['net']:>9,.0f} ({100*(v['net']/b-1):+.0f}%) n={v['n']} mean/trade={v['mean_pct']:+.2f}% "
              f"DDpk={v['dd_pct_peak']:.1f}% years:" + " ".join(f"{y}:{x:,.0f}" for y, x in v['by_year'].items()))
(HERE / "results/headline.json").write_text(json.dumps(out, indent=1))
