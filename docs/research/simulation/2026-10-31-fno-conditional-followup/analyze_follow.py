"""O31h fixed analysis; new entries must pass BOTH standalone and combined rules."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
PRIOR = HERE.parent / "2026-10-31-fno-complements"
sys.path[:0] = [str(HERE), str(PRIOR)]
import analyze_gap as A  # noqa: E402

FIN = A.A.A
YEARS = ("2024", "2025", "2026")


def load(p):
    return json.loads(p.read_text(encoding="utf-8"))


def main():
    import lab_follow as X
    freeze = load(HERE / "freeze.json")
    keys = {y: load(HERE / f"_local/keys-{y}.json") for y in YEARS}
    sessions = {y: [d for d in load(ROOT / freeze["bindings"][y]["dataset"] / "manifest.json")["sessions"] if d <= A.A.LAST[y]] for y in YEARS}
    every = [d for y in YEARS for d in sessions[y]]
    cache, problems = {}, {}
    for name, book in freeze["books"].items():
        cache[name] = {}
        for year in YEARS:
            obj = load(HERE / "_local/evals" / f"{keys[year][name]}.json")
            assert obj["book"] == book
            rows = obj["trades"]
            cache[name][year] = rows
            bad = FIN.check_book(rows, {"cfg": book["cfg"]}, FIN.CAPITAL, book.get("cost"), book["cfg"].get("FNO_MAX_TRADES_PER_DAY", 3))
            notes = {k: v for k, v in obj["notes"].items() if "conflict" in k or k == "named_memo_miss"}
            if bad or notes:
                problems[f"{year}|{name}"] = {"financial": bad, "memo": notes}
    assert not problems, problems

    def exact(name):
        ys = {y: FIN.path(cache[name][y]) for y in YEARS}
        days = {d: v for row in ys.values() for d, v in row["daily"].items()}
        return {"years": ys, "weekly": A.A.weeks_of(days, every),
                "unresolved": sum(t.get("net_pnl") is None for y in YEARS for t in cache[name][y])}

    base = exact("EX|MAIN")
    assert tuple(base["years"][y]["net"] for y in YEARS) == (16371, 5710, 30540)
    for old in ("INTRADAY_DMI", "SHOCK_RECOVERY"):
        for y in YEARS:
            key = load(PRIOR / f"_local/keys-{y}.json")["RAW|" + old]
            before = load(PRIOR / "_local/evals" / f"{key}.json")["trades"]
            assert cache["RAW|" + old][y] == before, (old, y, "parity failed")
    random_best = load(PRIOR / "results.json")["random_closed"]["best"]
    out = {"schema": "o31h_results_v1", "qualification": "NOT_ASSESSED", "can_place_orders": False,
           "correctness": {"fresh_replays": 21, "problems": problems, "main_and_two_old_entries_parity": True},
           "rule": freeze["rule"], "sessions": {y: len(sessions[y]) for y in YEARS},
           "main": {y: FIN.pub(base["years"][y]) for y in YEARS}, "candidates": {}}
    for family in X.FAMILIES:
        rows = cache["RAW|" + family]
        raw, ex = A.raw_summary(rows, sessions), exact("EX|" + family)
        old = "INTRADAY_DMI" if family == "DMI_VWAP_RETEST" else "SHOCK_RECOVERY"
        old_raw = A.raw_summary(cache["RAW|" + old], sessions)
        out["candidates"][family] = {**A.judge(raw, ex, base, random_best), "standalone": raw,
            "stress_300": A.raw_summary(rows, sessions, 300), "combined": {y: FIN.pub(ex["years"][y]) for y in YEARS},
            "increment_vs_main": {y: ex["years"][y]["net"] - base["years"][y]["net"] for y in YEARS},
            "increment_vs_old_raw": {y: round(raw["years"][y]["net"] - old_raw["years"][y]["net"], 2) for y in YEARS}}
    out["passing"] = [n for n, v in out["candidates"].items() if v["passes"]]
    X.P.write(HERE / "results.json", out)
    X.P.write(HERE / "_local/daily-results.json", {"sessions": sessions, "trades": cache})
    print(json.dumps({"passing": out["passing"], "candidates": {n: {"standalone": r["standalone"]["years"], "combined": r["combined"],
        "checks": r["checks"]} for n, r in out["candidates"].items()}}, indent=2))


if __name__ == "__main__":
    main()
