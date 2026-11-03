"""Post-score diagnostic: the put side sized by RISK_PLAN.md's frozen limits (2026-11-03-expiry-auction/riskdial.py's
skeptical bootstrap: best day removed, half the mean day subtracted, 20,000 years of 52 expiries in blocks of four).
Arms: puts at 2x, 3x, 4x with calls at 1x and with no calls; E03.1's absolute brakes. -> putdial.json. IN-SAMPLE.
"""
from __future__ import annotations
import json, random, sys
from dataclasses import replace
from pathlib import Path
import r8b_lab as R

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "2026-11-03-expiry-auction"))
import riskdial as D  # noqa: E402  (skeptical(), bootstrap(), drawdown(), SEED; no replay)


def main():
    T = R.L.tapes(); both = T[2024] + T[2025]; out = {}
    arms = {"E031": {}, "PE_ONLY": dict(call_mult=0.)}
    for k in (2., 3., 4.):
        arms[f"PUT{k:g}"] = dict(put_mult=k); arms[f"PE{k:g}_ONLY"] = dict(put_mult=k, call_mult=0.)
    for name, extra in arms.items():
        rule = replace(R.E031, **extra); row = {}
        for sc in ("ordinary", "adverse", "catastrophe"):
            days = R.run(both, rule, sc)["days"]; nets = [d["net"] for d in days]
            row[sc] = dict(net=round(sum(nets), 2), worst=round(min(nets), 2), drawdown=round(D.drawdown(nets), 2),
                           y2024=round(sum(n for d, n in zip(days, nets) if d["day"] < "2025"), 2), y2025=round(sum(n for d, n in zip(days, nets) if d["day"] >= "2025"), 2))
            if sc == "adverse":
                row["skeptical"] = D.bootstrap(D.skeptical(nets), random.Random(D.SEED))
        row["passes_risk_plan"] = dict(loss_year=row["skeptical"]["loss_year_chance"] <= .30, drawdown=row["skeptical"]["drawdown_p95"] <= 5000,
                                       severe=row["catastrophe"]["net"] >= -6250)
        out[name] = row
        print(name, json.dumps(dict(o=row["ordinary"], a=row["adverse"]["net"], sev=row["catastrophe"]["net"], skeptical=row["skeptical"],
                                    passes=row["passes_risk_plan"])), flush=True)
    (HERE / "putdial.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
