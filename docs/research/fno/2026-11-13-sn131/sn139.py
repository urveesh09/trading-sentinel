"""SN139 - confidence sizing at Rs 30k / Rs 6k room (PLAN.md), for each of SN132 / SN137 / SN138: 1 lot when the
prediction is in (theta, 2 theta], 2 lots in (2 theta, 4 theta], 3 lots above (theta 0 -> 1 lot); against 1 lot."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run  # noqa: E402
import sm  # noqa: E402
import sn138  # noqa: E402

YRS = ("2024", "2025", "2026")


def lots(p, th):
    if th <= 0:
        return 1
    return 1 if p <= 2 * th else (2 if p <= 4 * th else 3)


if __name__ == "__main__":
    out_path = HERE / "results-sn139.json"
    if out_path.exists():
        raise SystemExit("SN139 is scored once")
    data = sm.build()
    pb, vb, pa_, pe = sn138.ensemble(data)
    r132 = json.loads((HERE / "results-sn132.json").read_text(encoding="utf-8"))
    engines = {"SN132 base": (pb, vb, None), "SN137 adaptive": (pa_, None, r132["all days"]["thetas"]), "SN138 ensemble": (pe, vb, None)}
    res = {}
    for name, (p, v, th) in engines.items():
        one, t1, chosen = run.policy(data, p, v, "all days", room=6000.0, thetas=th)
        sz, t2, _ = run.policy(data, p, v, "all days", room=6000.0, thetas=chosen, lots=lots)
        res[name] = {"one_lot": sm.per_year(one, t1), "sized": sm.per_year(sz, t2)}
        s = res[name]["sized"]
        print(f"=== SN139 {name}: 1 lot {res[name]['one_lot']['total']} | sized {s['total']} {[s[y]['net'] for y in YRS]} "
              f"worst day {s['worst_day']}", flush=True)
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
