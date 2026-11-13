"""SN146 - the combined account (PLAN.md): Gold v5 plus the best-evidenced learned gap-day policy (SN144 if it passed,
else SN143 if it passed; if neither, SN132's all-days policy as a labelled description) as a separate Rs 15k sleeve,
2024-2026, against Gold alone (Rs 30k fixed and growing, stop 3)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "2026-11-13-sn116"))
import pe  # noqa: E402,F401
import pc  # noqa: E402

YRS = ("2024", "2025", "2026")

if __name__ == "__main__":
    out_path = HERE / "results-sn146.json"
    if out_path.exists():
        raise SystemExit("SN146 is scored once")
    r144 = json.loads((HERE / "results-sn144.json").read_text(encoding="utf-8"))
    r143 = json.loads((HERE / "results-sn143.json").read_text(encoding="utf-8"))
    if r144["PASS_partial"]:
        label, nets = "SN144 hot-day specialist (passed)", r144["day_nets"]
    elif r143["all days"]["PASS_partial"]:
        label, nets = "SN143 close actions (passed)", r143["all days"]["day_nets"]
    else:
        r132 = json.loads((HERE.parent / "2026-11-13-sn131" / "results-sn132.json").read_text(encoding="utf-8"))
        nets = {}
        for t in r132["all days"]["trade_list"]:
            nets[t[0]] = nets.get(t[0], 0.0) + t[3]
        label = "DESCRIPTION ONLY - nothing passed: SN132's all-days policy"
    sleeve = {y: round(sum(v for d, v in nets.items() if d[:4] == y)) for y in YRS}
    res = {"sleeve": label, "sleeve_by_year": sleeve, "sleeve_total": sum(sleeve.values())}
    for mname, cap in (("fixed", 0), ("grow stop 3", 3)):
        _p, dl = pc.gold_days(pc.C.V5, (f"30k {mname}", 30000.0, "grow", cap))
        g = {y: round(sum(n for d, n in dl if d[:4] == y)) for y in YRS}
        res[f"Gold 30k {mname}"] = {"by_year": g, "total_2024_26": sum(g.values()),
                                    "with_sleeve_total_2024_26": sum(g.values()) + res["sleeve_total"]}
    print("SN146", json.dumps(res), flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
