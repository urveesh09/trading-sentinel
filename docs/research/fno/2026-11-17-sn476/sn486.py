"""SN486 (own): the failed-add rule's neighbours (PLAN.md SN486, frozen at bf895633; details fixed here before any number), plus
SN480b (supplementary, PLAN A2): the self-funded ledger with Gold's own wallet ceiling.

SN486: theta in {+0.5, 0, -0.5, -1.0} (adds sold when the future closes through c[i] + d*theta*atr[i] against the trade, next
minute's bid, Rs 23.60 a sale) and theta 0 with the same-minute bid ("same", Gold's own exit convention). GOLD_30K, 2022 and
2023-26, Rs 205 / 400; paired totals with sn480's block CI. Plateau-stable only if all four thetas (next-minute) share the sign
of the paired difference in both paths at both stresses. ONE_15K reported beside it (information only).
SN480b: SELF_30K with float_cap = Rs 1,01,250 (Gold's ceiling after three steps: lots = floor(min(W, 1,01,250) / 15k)), Gold and
the SN480 challenger, both paths and stresses; plus, for the uncapped SELF_30K at Rs 400 (SN480's cell), the first session the
wallet fell below Rs 7,500 (no trade after it) and the wallet path's minimum.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sn480 as A  # noqa: E402

goldx, g = A.goldx, A.g
OUT = HERE / "results-sn486.json"
OUT_B = HERE / "results-sn480b.json"
THETAS = (0.5, 0.0, -0.5, -1.0)
CAP = 101250.0


def main():
    if OUT.exists() or OUT_B.exists():
        raise SystemExit("SN486 / SN480b are scored once")
    goldx.install()
    cells = {}
    for lname, wallet in (("GOLD_30K", goldx.GOLD_30K), ("ONE_15K", goldx.ONE_15K)):
        for pname, years in A.PATHS:
            for st in A.STRESSES:
                sb, db, lb = A.run(years, st, wallet)
                for th in THETAS:
                    sc, dc, lc = A.run(years, st, wallet, fail_theta=th, fail_exec="next", fail_fee=23.6)
                    cells[f"{lname} {pname} @{int(st)} theta={th:+.1f}"] = A.compare(sb, db, lb, sc, dc, lc)
                sc, dc, lc = A.run(years, st, wallet, fail_theta=0.0, fail_exec="same", fail_fee=23.6)
                cells[f"{lname} {pname} @{int(st)} theta=+0.0 same"] = A.compare(sb, db, lb, sc, dc, lc)
    signs = {th: [cells[f"GOLD_30K {p} @{int(s)} theta={th:+.1f}"]["diff_total"] > 0 for p, _y in A.PATHS for s in A.STRESSES] for th in THETAS}
    flat = [x for th in THETAS for x in signs[th]]
    plateau = all(flat) or not any(flat)
    res = {"cells": {k: {x: v[x] for x in v if x != "fail_events"} for k, v in cells.items()},
           "plateau": {"stable_sign": plateau, "all_positive": all(flat), "signs": {f"{th:+.1f}": s for th, s in signs.items()}}}
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    capped = ("30k self-funded capped", 30000.0, "float", None)
    B = {}
    for pname, years in A.PATHS:
        for st in A.STRESSES:
            sb, db, lb = A.run(years, st, capped, float_cap=CAP)
            sc, dc, lc = A.run(years, st, capped, float_cap=CAP, **A.CHALLENGER)
            B[f"SELF_30K_CAPPED {pname} @{int(st)}"] = {**{x: v for x, v in A.compare(sb, db, lb, sc, dc, lc).items() if x != "fail_events"},
                                                       "gold_min_wallet": round(min(w for _d, w, _n, _t, _l in db)),
                                                       "gold_end_wallet_plus_day": round(db[-1][1] + db[-1][2]) if db else None}
    s4, d4, _l4 = A.run(g.Y2326, 400.0, goldx.SELF_30K)
    eq = 30000.0
    bust, low = None, 30000.0
    for d, w, n, _t, _l in d4:
        eq = w + n
        low = min(low, eq)
        if bust is None and eq < 7500.0:
            bust = d
    B["SELF_30K uncapped 2023-2026 @400 path"] = {"first_session_below_7500": bust, "min_equity": round(low), "sessions_logged": len(d4), "net": s4["net"]}
    OUT_B.write_text(json.dumps(B, indent=1), encoding="utf-8")
    for k, c in cells.items():
        print(f"{k:44s} diff {c['diff_total']:>9} ci {c['diff_ci90']} w/o {c['diff_without_most_affected']:>8} worst {c['worst_day']} fails {c['failed_add_sales']}")
    print(json.dumps(res["plateau"]))
    for k, c in B.items():
        print(k, {x: c[x] for x in c if x in ("gold", "challenger", "diff_total", "diff_ci90", "worst_day", "gold_min_wallet", "first_session_below_7500", "min_equity", "net")} if "gold" not in c
              else (c["gold"]["net"], c["challenger"]["net"], c["diff_total"], c["diff_ci90"], c["worst_day"], c["gold_min_wallet"], c["gold"]["final_wallet"]))


if __name__ == "__main__":
    main()
