"""SN366 gate W, chain stage (PLAN.md section 1): N11's own chain replayed on N08's TEST2025 repoint (sealed 2025 data with
known results) into an EMPTY results folder, then compared with the stored parents and N11's stored 2025 N11 book.

Books: N11's control books (N08, VOL_CLOCK = N09.1's size-by-volatility clock, N10 retry) and its N11 panel book. Pass =
every task key equals the stored key and every book's economics (trades and nets) equal the stored evals.
Windows workers re-import this file, so the repoint and the empty results folder are set at module level.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ["N08_YEAR"] = "TEST2025"
HERE = Path(__file__).resolve().parent
N11 = HERE.parents[1] / "simulation" / "2026-11-02-fno-n11"
sys.path.insert(0, str(N11))
import n11_lab as L  # noqa: E402

EVALS = HERE / "_local" / "gatew-n11-evals"
L.Y.EVALS = EVALS
EVALS.mkdir(parents=True, exist_ok=True)
OUT = HERE / "results-sn366-gateW-chain.json"


def main():
    if OUT.exists():
        raise SystemExit("gate W (chain) is run once")
    assert not any(EVALS.glob("*.json")), "gate W must start from an empty results folder"
    T, Y, Z, M, B = L.T, L.Y, L.Z, L.M, L.B
    books = {**L.control_books(), "N11": L.panel_books()["N11"]}
    keys = {n: Y.task_key(b, "year", B.C.WINDOW) for n, b in books.items()}
    stored = {"N08": (json.loads((Z.LOCAL / "keys-diag-2025.json").read_text())["N08"], Z.LOCAL / "evals-2025"),
              "VOL_CLOCK": (json.loads((M.HERE / "_local" / "keys-primary-2025.json").read_text())["VOL_CLOCK"], M.HERE / "_local" / "evals"),
              "N10": (json.loads((T.HERE / "_local" / "keys-panel2-2025.json").read_text())["R2_THIRD_CW"], T.HERE / "_local" / "evals"),
              "N11": (json.loads((N11 / "_local" / "keys-panel-2025.json").read_text())["N11"], N11 / "_local" / "evals")}
    L.Z.N.run_books(books, 3)
    out = {"route": "TEST2025", "evals": str(EVALS), "books": {}}
    for n, (skey, sdir) in stored.items():
        mine = T.load(keys[n], EVALS)
        old = T.load(skey, sdir)
        out["books"][n] = {"key_equal": keys[n] == skey, "economics_equal": T.economics(mine) == T.economics(old),
                           "trades": len(mine), "net": round(sum(t["net_pnl"] for t in mine), 2),
                           "seconds": json.loads((EVALS / f"{keys[n]}.json").read_text(encoding="utf-8")).get("seconds")}
    out["pass"] = all(v["key_equal"] and v["economics_equal"] for v in out["books"].values())
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
