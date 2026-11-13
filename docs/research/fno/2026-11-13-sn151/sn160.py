"""SN160 - the scoreboard for SN151-SN159 (PLAN.md), read from the saved result files; nothing is rescored."""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def j(n):
    p = HERE / f"results-{n}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


if __name__ == "__main__":
    rows = []
    for sn in ("sn151", "sn152"):
        r = j(sn)
        if r:
            rows += [(sn[2:], f"{k}", r[k]["verdict"]) for k in r]
    r = j("sn153")
    if r:
        rows.append(("153", "expiry-day hot straddle (score half)", {"pick": r["pick"], **r["verdict"]}))
    r = j("sn154")
    if r:
        for k in ("gold-free", "all days"):
            rows.append(("154", f"learned probability ({k})", r[k]["sn154_verdict"]))
            rows.append(("155", f"rule + model consensus ({k})", r[k]["sn155"]))
    r = j("sn156")
    if r:
        for k, v in r.items():
            rows.append(("156", f"leg out ({k})", v["preference"]))
    r = j("sn157")
    if r:
        rows.append(("157", "1-second hot-day momentum", {k: v for k, v in r.items() if k not in ("choose",)}))
    r = j("sn158")
    if r:
        rows.append(("158", "hot-day book vs Gold", {k: v for k, v in r.items() if k != "sn159_bootstrap"}))
        rows.append(("159", "bootstrap intervals", r["sn159_bootstrap"]))
    for sn, what, val in rows:
        print(f"SN{sn} | {what:40s} | {json.dumps(val, default=str)[:330]}")
    (HERE / "results-sn160.json").write_text(json.dumps([{"SN": a, "what": b, "result": c} for a, b, c in rows], indent=1, default=str),
                                             encoding="utf-8")
