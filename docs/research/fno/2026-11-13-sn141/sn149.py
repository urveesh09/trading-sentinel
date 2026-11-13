"""SN149 - the scoreboard for SN131-SN148 (PLAN.md), read from the saved result files; nothing is rescored."""
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
D = HERE.parent / "2026-11-13-sn131"


def j(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


if __name__ == "__main__":
    rows = []
    r = j(D / "results-sn131.json")
    if r:
        rows.append(("131", "learned forecast: IC by target (out of sample)", {t: round(v["ic_all"], 3) for t, v in r["targets"].items()}))
    for sn, name in (("132", "learned policy"), ("137", "adaptive"), ("138", "ensemble")):
        r = j(D / f"results-sn{sn}.json")
        if r:
            rows.append((sn, f"{name} (all days, 2024-26)", {"total": r["all days"]["per_year"]["total"], "random_95th": r["all days"]["random_95th"]}))
    r = j(D / "results-sn133.json")
    if r:
        rows.append(("133", "learned exit vs fixed", {"learned": r["all days"]["learned_exit"]["total"], "fixed": r["all days"]["fixed"]["total"]}))
    r = j(D / "results-sn134.json")
    if r:
        rows.append(("134", "learned event selection", {"learned": r["learned"]["total"], "all events": r["all_events"]["total"], "random_95th": r["random_95th"]}))
    for sn in ("135", "136"):
        r = j(D / f"results-sn{sn}.json")
        if r:
            keep = ("theta", "test", "test_at_100", "test_at_205", "random_95th", "PASS")
            rows.append((sn, "1-second learner" if sn == "135" else "order-book learner", {k: v for k, v in r.items() if k in keep}))
    r = j(D / "results-sn139.json")
    if r:
        rows.append(("139", "confidence sizing at Rs 30k", {k: v["sized"]["total"] for k, v in r.items()}))
    r = j(D / "results-sn140.json")
    if r:
        eng = {k: {kk: vv for kk, vv in v.items() if kk != "by_quarter"} for k, v in r["engines"].items()}
        rows.append(("140", "honesty checks", {**eng, "shuffled": r["shuffled_label_control"]["total"]}))
    for sn in ("141", "142", "143", "144", "145", "146", "147"):
        r = j(HERE / f"results-sn{sn}.json")
        if r is None:
            continue
        if sn == "141":
            rows.append((sn, "learning curve (mean IC)", {**{k: v["mean_ic"] for k, v in r.items() if k.startswith("test")}, "more_data_helps": r["MORE_DATA_HELPS"]}))
        elif sn == "142":
            rows.append((sn, "cost curve (total 2024-26)", {k: v["per_year"]["total"] for k, v in r.items()}))
        elif sn == "143":
            rows.append((sn, "close actions", {k: v["per_year"]["total"] for k, v in r.items()}))
        elif sn == "144":
            rows.append((sn, "hot-day specialist vs fixed straddle", {"learned": r["learned"]["total"], "fixed": r["fixed_sn95l_straddle_same_days"]["total"]}))
        elif sn == "145":
            rows.append((sn, "learned extension for Gold vs v5", {"learned": r["learned_exit_total"], "v5": r["v5_exit_total"]}))
        elif sn == "146":
            rows.append((sn, "combined account", r))
        elif sn == "147":
            rows.append((sn, "1-second learner swapped", r["test_on_A"]))
    for sn, what, val in rows:
        print(f"SN{sn} | {what:48s} | {json.dumps(val)[:300]}")
    (HERE / "results-sn149.json").write_text(json.dumps([{"SN": a, "what": b, "result": c} for a, b, c in rows], indent=1), encoding="utf-8")
