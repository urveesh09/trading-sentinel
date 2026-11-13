"""SN118 - real money, no refills, every monthly start Jan 2023 - Jun 2026 (PLAN.md). The lab's no-refill account:
equity carries every loss; one lot is kept while equity >= Rs 7,500, below that the account stops. Rs 30k / Rs 50k,
sizing equity uncapped or capped at Rs 1,01,250."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pc  # noqa: E402

C = pc.C
CONFIGS = {"30k uncapped": (30000.0, None), "30k capped 1,01,250": (30000.0, 101250.0),
           "50k uncapped": (50000.0, None), "50k capped 1,01,250": (50000.0, 101250.0)}


def starts():
    days = sorted(d for y in C.YEARS for d in C.years()[y].sessions)
    out, seen = [], set()
    for d in days:
        if d[:7] not in seen and d <= "2026-06-30":
            seen.add(d[:7])
            out.append(d)
    return out


if __name__ == "__main__":
    out_path = HERE / "results-sn118.json"
    if out_path.exists():
        raise SystemExit("SN118 is scored once")
    st = starts()
    res = {"starts": st, "configs": {}}
    for name, (W0, cap) in CONFIGS.items():
        rows = []
        for s in st:
            v = {**C.V5, "from_day": s, "float_floor": 7500.0, "float_cap": cap or 1e18}
            _p, dl = pc.gold_days(v, ("F", W0, "float", None))
            eq = W0 + np.cumsum([n for _d, n in dl]) if dl else np.array([W0])
            peak = np.maximum.accumulate(np.concatenate([[W0], eq]))
            dd = float(((peak[1:] - eq) / peak[1:]).max())
            rows.append({"start": s, "final": round(float(eq[-1])), "lowest": round(float(min(W0, eq.min()))),
                         "max_drawdown_pct": round(100 * dd, 1), "dead": bool(eq.min() < 7500.0)})
        fin = np.array([r["final"] for r in rows])
        summ = {"starts": len(rows), "median_final_multiple": round(float(np.median(fin / W0)), 2),
                "share_below_start": round(float(np.mean(fin < W0)), 3), "share_dead": round(float(np.mean([r["dead"] for r in rows])), 3),
                "worst_final": int(fin.min()), "worst_start": rows[int(fin.argmin())]["start"],
                "worst_drawdown_pct": max(r["max_drawdown_pct"] for r in rows),
                "starts_2026_median_final": round(float(np.median([r["final"] for r in rows if r["start"] >= "2026-01-01"])))}
        res["configs"][name] = {"summary": summ, "rows": rows}
        print(f"=== {name}: {summ}", flush=True)
        for r in rows:
            print("    ", r)
    out_path.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
