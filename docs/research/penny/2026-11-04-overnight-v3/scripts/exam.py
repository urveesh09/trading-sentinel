"""Sealed 2011-2014 check of the frozen overnight-v3 finalists (opened once).

  exam.py freeze   writes exam-freeze.json (sources, data, finalists, models, rules); refuses if it exists
  exam.py run      verifies every hash, builds 2010-2015 day tables from the enrichment's public
                   acquisition with the enrichment's preparation rules (no repair), scores V2 and the
                   finalists under M1-M7 (ten-seed means for M2-M4, M6) and the 200-book ranking null,
                   writes exam-results.json; refuses if results exist.
No broker, Breeze, scheduler or Production access.
"""
from __future__ import annotations

import hashlib
import json
import math
import sqlite3
import sys
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "scripts"))
import v3sim as v  # noqa: E402
from rounds import MODELS, SEEDS  # noqa: E402

ENR = ROOT / "docs/research/penny/2026-11-04-overnight-enrichment"
V2DIR = ROOT / "docs/research/penny/2026-11-04-overnight-v2"
FREEZE = HERE / "exam-freeze.json"
RESULTS = HERE / "exam-results.json"
WINDOW = ("2011-01-01", "2014-12-31")
WARMUP, TAIL = "2010-01-01", "2015-01-10"
FINALISTS = [v.Policy("V2_HI_F3N", rank="strength_hi20", filler="F3", filler_order="night"),
             v.Policy("V2_HI_F3L", rank="strength_hi20", filler="F3", filler_order="value")]
CONTROL = v.Policy("V2")
NULL_BOOKS = 200


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def sources() -> dict:
    files = [HERE / "v3sim.py", HERE / "scripts/rounds.py", Path(__file__).resolve(), V2DIR / "lab.py",
             *[ROOT / "python-engine" / n for n in ("penny_edge_engine.py", "penny_edge_backtest.py", "penny_risk.py", "config.py")]]
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in files}


def data_files() -> list[Path]:
    return [ENR / "_local/older/yahoo.sqlite", ENR / "older-acquisition.json", V2DIR / "_local/yahoo-split-cuts.json"]


def rules() -> dict:
    return {
        "pass": ["closes >= 100 at M1 and no unresolved exposure at the end",
                 "net > 0 under every model M1..M7",
                 "robust net (minimum over M1..M7) >= 1.10 x V2 robust net",
                 "M1 net >= 0.95 x V2 M1 net",
                 "M1 drawdown <= 1.5 x V2 M1 drawdown",
                 "positive in >= 3 of the 4 years at M1"],
        "reported_not_pass": "ranking claim: finalist M1 net above the 90th percentile of 200 random-order books from its own pool",
        "primary": "V2_HI_F3N; V2_HI_F3L is the liquidity-first sibling",
    }


def freeze():
    if FREEZE.exists():
        raise SystemExit("freeze exists")
    FREEZE.write_text(json.dumps({
        "window": WINDOW, "warmup": WARMUP, "tail": TAIL, "source": sources(),
        "data": {p.relative_to(ROOT).as_posix(): sha(p) for p in data_files()},
        "control": asdict(CONTROL), "finalists": [asdict(p) for p in FINALISTS],
        "models": {k: asdict(m) for k, m in MODELS.items()}, "seeds": SEEDS, "null_books": NULL_BOOKS,
        "rules": rules(),
        "preparation": "enrichment prepare(): raw positive finite OHLCV, high/low consistency, positive volume; drop history before the latest archived split (incl. later known splits); NIFTYBEES calendar; no repair",
        "limits": ["current surviving membership", "later-known split cuts", "daily bars only: no fill is proven",
                   "current fees for all years", "single public dataset"],
        "frozen_at": datetime.now(timezone.utc).isoformat(), "opened": False}, indent=2), encoding="utf-8")
    print("frozen", FREEZE)


def prepare() -> list:
    lab = v.lab
    audit = Counter()
    bars = defaultdict(list)
    nifty = []
    cuts = json.loads((V2DIR / "_local/yahoo-split-cuts.json").read_text())
    for r in json.loads((ENR / "older-acquisition.json").read_text())["receipts"]:
        for event in r.get("corporate_actions", {}).get("splits", {}).values():
            d = datetime.fromtimestamp(event["date"], ZoneInfo("Asia/Kolkata")).date().isoformat()
            cuts[r["symbol"]] = max(cuts.get(r["symbol"], ""), d)
    path = ENR / "_local/older/yahoo.sqlite"
    c = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    for t, d, o, h, l, cl, vol in c.execute("SELECT ticker,date,open,high,low,close,volume FROM ohlcv_cache WHERE date <= ? ORDER BY ticker,date", (TAIL,)):
        audit["raw_rows"] += 1
        if any(x is None or not math.isfinite(float(x)) for x in (o, h, l, cl, vol)) or min(o, h, l, cl) <= 0 or vol < 0:
            audit["invalid_cells"] += 1
            continue
        if t == "NIFTYBEES":
            nifty.append({"date": d, "close": float(cl)})
            continue
        if d < cuts.get(t, ""):
            audit["pre_last_split"] += 1
            continue
        if vol <= 0:
            audit["zero_volume"] += 1
            continue
        if l > min(o, cl) * (1 + 1e-7) or h < max(o, cl) * (1 - 1e-7) or h < l:
            audit["inconsistent_ohlc"] += 1
            continue
        bars[t].append({"ticker": t, "date": d, "open": float(o), "high": float(h), "low": float(l), "close": float(cl), "volume": float(vol)})
        audit["retained_equity_rows"] += 1
    c.close()
    nifty.sort(key=lambda x: x["date"])
    days = lab.build_days(dict(bars), nifty, WARMUP, TAIL)
    audit["retained_tickers"] = len(bars)
    audit["scoring_sessions"] = sum(WINDOW[0] <= d.date <= WINDOW[1] for d in days)
    audit["sessions_with_candidates"] = sum(bool(d.cands) and WINDOW[0] <= d.date <= WINDOW[1] for d in days)
    return days, dict(audit)


def score_policy(days, p, start, end):
    row = {}
    for m, fm in MODELS.items():
        seeds = SEEDS if fm.win_fill < 1 else [SEEDS[0]]
        runs = [v.simulate(days, p, fm, start=start, end=end, keep=(m == "M1"), seed=sd) for sd in seeds]
        nets = [x["summary"]["net"] for x in runs]
        row[m] = {"net": round(sum(nets) / len(nets), 2), "net_min_seed": round(min(nets), 2),
                  "dd": round(max(x["summary"]["dd"] for x in runs), 2), "closes": runs[0]["summary"]["n"],
                  "open_at_end": max(x["open_at_end"] for x in runs)}
        if m == "M1":
            row["years"] = v.by_year(runs[0]["trades"])
            row["summary"] = {k: runs[0]["summary"][k] for k in ("n", "net", "ex_best", "dd", "pf", "win", "mean_pct")}
            row["outcomes"] = runs[0]["outcomes"]
    row["robust"] = min(row[m]["net"] for m in MODELS)
    return row


def verdict(f, c):
    years = f["years"]
    checks = {
        "1_closes_and_resolved": f["M1"]["closes"] >= 100 and f["M1"]["open_at_end"] == 0,
        "2_positive_all_models": all(f[m]["net"] > 0 for m in MODELS),
        "3_robust_vs_v2": f["robust"] >= (1.10 * c["robust"] if c["robust"] >= 0 else c["robust"] * 0.90),
        "4_full_fill_vs_v2": f["M1"]["net"] >= 0.95 * c["M1"]["net"],
        "5_drawdown": f["M1"]["dd"] <= 1.5 * c["M1"]["dd"],
        "6_years_positive": sum(x > 0 for x in years.values()) >= 3,
    }
    return {"checks": checks, "pass": all(checks.values())}


def run():
    if RESULTS.exists():
        raise SystemExit("results exist: the check is opened once")
    fr = json.loads(FREEZE.read_text())
    if fr["source"] != sources():
        raise SystemExit("source changed after freeze")
    if fr["data"] != {p.relative_to(ROOT).as_posix(): sha(p) for p in data_files()}:
        raise SystemExit("data changed after freeze")
    days, audit = prepare()
    out = {"opened_at": datetime.now(timezone.utc).isoformat(), "window": WINDOW, "audit": audit, "arms": {}}
    out["arms"]["V2"] = control = score_policy(days, CONTROL, *WINDOW)
    print("V2", {m: control[m]["net"] for m in MODELS}, "robust", control["robust"], flush=True)
    for p in FINALISTS:
        row = score_policy(days, p, *WINDOW)
        row["verdict"] = verdict(row, control)
        nulls = []
        for k in range(NULL_BOOKS):
            q = v.Policy(p.name + "_NULL", rank="random", filler=p.filler, filler_order="random",
                         extra={"null_seed": 7000 + k})
            nulls.append(v.simulate(days, q, MODELS["M1"], start=WINDOW[0], end=WINDOW[1])["summary"]["net"])
        nulls.sort()
        row["null"] = {"p10": nulls[19], "p50": nulls[99], "p90": nulls[179], "rank_pct": round(100 * sum(x < row["M1"]["net"] for x in nulls) / len(nulls), 1)}
        out["arms"][p.name] = row
        print(p.name, {m: row[m]["net"] for m in MODELS}, "robust", row["robust"], row["verdict"], row["null"], flush=True)
    RESULTS.write_text(json.dumps(out, indent=2), encoding="utf-8")
    fr["opened"] = True
    (HERE / "EXAM_OPENED.json").write_text(json.dumps({"opened_at": out["opened_at"], "freeze_sha256": sha(FREEZE)}, indent=2))


if __name__ == "__main__":
    {"freeze": freeze, "run": run}[sys.argv[1]]()
