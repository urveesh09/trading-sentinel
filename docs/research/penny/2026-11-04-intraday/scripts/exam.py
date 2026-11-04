"""Sealed Jan 1 - Jul 31 2026 check of Smart V3 (opening-auction reversal), opened once.

  exam.py freeze   writes exam-freeze.json (sources, data hashes, finalists, models, rules); refuses if it exists
  exam.py wire     runs the identical pipeline on SEEN development data (Production Kite export Aug 10 -
                   Nov 3; Yahoo minutes Sep 7 - Nov 3 for the V1/V2 replay; daily panel 26b) into
                   results/exam-wire.json; must replay trades or it fails
  exam.py run      verifies every hash, then scores on the Kite minute archive (89 EQ names) and the
                   Jan - Jul 2026 Yahoo daily band universe, writes exam-results.json; refuses if results exist
No broker, Breeze, scheduler or Production access.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE))
import idata  # noqa: E402
import minute_oar as mo  # noqa: E402
import oarsim as o  # noqa: E402
sys.path.insert(0, str(ROOT / "scripts"))

FREEZE = HERE / "exam-freeze.json"
RESULTS = HERE / "exam-results.json"
WINDOW = ("2026-01-01", "2026-07-31")
BANKROLL = 2000.0
PRIMARY = "S1_THIN"
MINUTE_ARMS = {
    # name: policy; the primary is S1_THIN, the others are the same rule under other fill models
    "S1_THIN_close": mo.MPolicy("S1_THIN_close", skip_thin=True),
    "S1_THIN_1515": mo.MPolicy("S1_THIN_1515", exit="1515", exit_bps=25, skip_thin=True),
    "S1_THIN_close_c915": mo.MPolicy("S1_THIN_close_c915", capacity="c915", skip_thin=True),
    "S1_THIN_1515_c915": mo.MPolicy("S1_THIN_1515_c915", exit="1515", exit_bps=25, capacity="c915", skip_thin=True),
    "S1_THIN_close_c915_25": mo.MPolicy("S1_THIN_close_c915_25", capacity="c915", c915_share=0.25, skip_thin=True),
    "S1_THIN_close_e50": mo.MPolicy("S1_THIN_close_e50", entry_bps=50, capacity="c915", skip_thin=True),
    "S1_close": mo.MPolicy("S1_close"),
    "S2_THIN_close_c915": mo.MPolicy("S2_THIN_close_c915", slots=2, capacity="c915", skip_thin=True),
}
DAILY_ARMS = [(o.Policy("S1", slots=1), 2000.0), (o.Policy("OAR_GAP"), 25000.0), (o.Policy("OAR_GAP_3", slots=3), 25000.0)]


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def sources() -> dict:
    files = [HERE / n for n in ("idata.py", "oarsim.py", "minute_oar.py")] + [Path(__file__).resolve()] + \
            [ROOT / "python-engine" / n for n in ("penny_risk.py", "penny_strategy_research.py", "penny_smart_policy.py",
                                                  "penny_smart_v2.py", "adaptive_penny_policy.py", "penny_smart_book.py",
                                                  "research_data_contracts.py", "penny_lifecycle_replay.py", "config.py")]
    return {p.relative_to(ROOT).as_posix(): sha(p) for p in files}


def data_files() -> list[Path]:
    return [idata.EXAM_DB, o.V2 / "yahoo/yahoo.sqlite", o.V2 / "yahoo-split-cuts.json"]


def rules() -> dict:
    return {
        "primary": "S1_THIN: one slot, Rs 2,000, gap <= -2% deepest first, EQ only, skip names whose prior-20-session "
                   "median 09:15 candle volume x 10% < a quarter of the ticket, buy at the official open, sell at the "
                   "official close (lock rule), intraday charges",
        "pass": ["1 S1_THIN_close_c915 (10% of the 09:15 candle): closes >= 30, net > 0 and ex-best > 0",
                 "2 S1_THIN_1515_c915 (15:15 last trade -25 bp, same capacity): net > 0",
                 "3 S1_THIN_close_c915 and S1_THIN_1515_c915 each beat Smart V1 and Smart V2 (run_smart, 10 bp spread, "
                 "same 89 names, same dates, Rs 2,000)",
                 "4 S1_THIN_close_c915 positive in >= 4 of the 7 months",
                 "5 S1_THIN_close_c915 drawdown <= Rs 500 (25% of the book)",
                 "6 daily Yahoo band universe Jan-Jul 2026, S1 at Rs 2,000: robust net (min M1-M8) > 0"],
        "reported_not_pass": ["uncapped S1 and S1_THIN", "25% capacity", "+50 bp entry", "two slots",
                              "daily OAR_GAP / OAR_GAP_3 at Rs 25,000 under M1-M8"],
    }


def freeze():
    if FREEZE.exists():
        raise SystemExit("freeze exists")
    FREEZE.write_text(json.dumps({
        "window": WINDOW, "bankroll": BANKROLL, "source": sources(),
        "data": {p.relative_to(ROOT).as_posix(): sha(p) for p in data_files()},
        "minute_arms": {k: asdict(v) for k, v in MINUTE_ARMS.items()},
        "daily_arms": [[asdict(p), b] for p, b in DAILY_ARMS], "daily_models": {k: asdict(m) for k, m in o.MODELS.items()},
        "seeds": o.SEEDS, "rules": rules(),
        "limits": ["89-name surviving EQ universe of Oct 5", "auction fills are modelled, not observed",
                   "the 09:15 candle volume includes the opening match plus the first minute",
                   "Jan-Jul daily bars were in the overnight development panels (close -> open), not open -> close"],
        "frozen_at": datetime.now(timezone.utc).isoformat(), "opened": False}, indent=2), encoding="utf-8")
    print("frozen", FREEZE)


def smart_baselines(db: Path, names: list, start: str, end: str) -> dict:
    from research_data_contracts import load_daily_dataset, load_intraday_dataset
    from penny_strategy_research import run_smart
    from penny_smart_policy import SMART_PARAMS
    from penny_smart_v2 import SMART_V2_PARAMS
    daily = load_daily_dataset(str(db), tickers=names, before=end)
    tape = load_intraday_dataset(str(db), interval="minute", start=start, end=end, tickers=names)
    out = {}
    for label, params in (("V1", SMART_PARAMS), ("V2", SMART_V2_PARAMS)):
        t0 = time.time()
        r = run_smart(tape, daily, names, start=start, end=end, params=params, bankroll=BANKROLL, spread_bps=10.0)
        months = {}
        for tr in r["trades"]:
            if tr.get("status") == "CLOSED":
                k = str(tr["exit_fill_ts"])[:7]
                months[k] = round(months.get(k, 0.0) + tr["net_pnl"], 2)
        out[label] = {"summary": r["summary"], "months": dict(sorted(months.items())),
                      "unresolved": sum(t.get("status") == "UNRESOLVED" for t in r["trades"]),
                      "events": r["events"], "seconds": round(time.time() - t0, 1)}
        print(label, out[label]["summary"], out[label]["seconds"], "s", flush=True)
    return out


def minute_scores(days: list, start: str, end: str) -> dict:
    fvh = mo.first_volume_history(days)
    out = {}
    for k, p in MINUTE_ARMS.items():
        r = mo.simulate(days, p, start=start, end=end, bankroll=BANKROLL, keep=True, fvh=fvh)
        out[k] = {"summary": r["summary"], "months": r["months"], "outcomes": r["outcomes"],
                  "trades": [{x: (round(v, 4) if isinstance(v, float) else v) for x, v in t.items()} for t in r["trades"]]}
        print(k, r["summary"], r["outcomes"], flush=True)
    return out


def daily_scores(rows: dict, start: str, end: str) -> dict:
    out = {}
    for p, b in DAILY_ARMS:
        out[f"{p.name}@{int(b)}"] = row = o.score(rows, p, start, end, bankroll=b)
        print(p.name, b, {m: row[m]["net"] for m in o.MODELS}, "robust", row["robust"], flush=True)
    return out


def verdict(m: dict, base: dict, dly: dict) -> dict:
    c, l = m["S1_THIN_close_c915"], m["S1_THIN_1515_c915"]
    worst_base = max(base["V1"]["summary"]["net"], base["V2"]["summary"]["net"])
    checks = {
        "1_capped_close_positive": c["summary"]["n"] >= 30 and c["summary"]["net"] > 0 and c["summary"]["ex_best"] > 0,
        "2_capped_1515_positive": l["summary"]["net"] > 0,
        "3_beats_v1_v2": c["summary"]["net"] > worst_base and l["summary"]["net"] > worst_base,
        "4_months": sum(v > 0 for v in c["months"].values()) >= 4,
        "5_drawdown": c["summary"]["dd"] <= 500,
        "6_daily_robust": dly["S1@2000"]["robust"] > 0,
    }
    return {"checks": checks, "pass": all(checks.values())}


def wire():
    t0 = time.time()
    kite = idata.build(idata.DEV_DAILY, idata.DEV_DAILY, "2026-07-30", "2026-11-03", min_bars=1)
    m = minute_scores(kite, "2026-08-10", "2026-11-03")
    assert sum(v["summary"]["n"] for v in m.values()) > 0, "wiring replayed nothing"
    names = json.loads((ROOT / "docs/research/penny/2026-11-04-strategy-search/smart-v2/universe.json").read_text())
    names = names.get("symbols", names) if isinstance(names, dict) else names
    base = smart_baselines(idata.DEV_MINUTE, sorted(names)[:30], "2026-09-07", "2026-09-18")
    rows = o.panels()["rows"]["26b"]
    dly = daily_scores(rows, "2026-08-01", "2026-11-03")
    out = {"mode": "wire (seen development data)", "minute": m, "smart": base, "daily": dly,
           "verdict_shape": verdict(m, base, dly), "seconds": round(time.time() - t0, 1)}
    (HERE / "results/exam-wire.json").write_text(json.dumps(out, indent=1))
    print("wire ok", out["verdict_shape"], out["seconds"], "s")


def run():
    if RESULTS.exists():
        raise SystemExit("results exist: the check is opened once")
    fr = json.loads(FREEZE.read_text())
    if fr["source"] != sources():
        raise SystemExit("source changed after freeze")
    if fr["data"] != {p.relative_to(ROOT).as_posix(): sha(p) for p in data_files()}:
        raise SystemExit("data changed after freeze")
    opened = datetime.now(timezone.utc).isoformat()
    (HERE / "EXAM_OPENED.json").write_text(json.dumps({"opened_at": opened, "freeze_sha256": sha(FREEZE)}, indent=2))
    days = idata.build(idata.EXAM_DB, idata.EXAM_DB, "2025-12-01", WINDOW[1], min_bars=1)
    names = sorted({d.ticker for d in days})
    m = minute_scores(days, *WINDOW)
    base = smart_baselines(idata.EXAM_DB, names, *WINDOW)
    bars = o.load_bars(reserved=None)
    rows = o.build_rows(bars, *WINDOW)
    dly = daily_scores(rows, *WINDOW)
    out = {"opened_at": opened, "window": WINDOW, "names": names, "minute": m, "smart": base, "daily": dly,
           "verdict": verdict(m, base, dly)}
    RESULTS.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("VERDICT", out["verdict"])


if __name__ == "__main__":
    {"freeze": freeze, "wire": wire, "run": run}[sys.argv[1]]()
