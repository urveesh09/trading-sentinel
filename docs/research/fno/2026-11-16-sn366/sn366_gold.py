"""SN366, last part: Gold v5 unchanged on the 2022 N11 signal stream (PLAN.md section 1).

Gold v5 = N11's and R0.85's entries (C.V5["books"]) with Gold's sizing, scale-in, extension, ITM choice and growth from a
Rs 30,000 wallet (ow.GOLD_30K), Rs 205 and Rs 400 stress. Nothing in the Gold files changes; at run time only:
  - the year lists of sn03 / lab / common become ("2022",) (Gold's vol table then has no reading for the first 60
    sessions, as Jan - Mar 2023 had none in the development replay);
  - sn01_data.DATASETS["2022"] = SN366's 2022 dataset, and its sessions are built into SN366's _local (sn01's caches are
    never written);
  - sn03.stream reads the exam's own N11 / R0.85 2022 results (keys-exam-2022.json, exam-evals-2022) with sn03's
    conversion code.
    python sn366_gold.py parity   the same patches pointed at the original sources and years must give Rs 8,50,882
    python sn366_gold.py 2022     the 2022 result (written once)
"""
from __future__ import annotations

import collections
import json
import pickle
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FNO = HERE.parent
sys.path.insert(0, str(FNO / "2026-11-16-sn331"))
import sn339_350 as Q  # noqa: E402

ow, C, L = Q.ow, Q.C, Q.L
B = L.B
D = B.D
MODE = sys.argv[1] if len(sys.argv) > 1 else None
assert MODE in ("parity", "2022"), "usage: sn366_gold.py parity | 2022"
_orig_stream, _orig_load = B.stream, D.load_year


def stream_2022(year, book="N11"):
    if year != "2022":
        return _orig_stream(year, book)
    keys = json.loads((HERE / "_local" / "keys-exam-2022.json").read_text(encoding="utf-8"))
    data = json.loads((HERE / "_local" / "exam-evals-2022" / f"{keys['panel|' + book]}.json").read_text(encoding="utf-8"))
    out = []
    for t in data["trades"]:                                    # sn03.stream's conversion, line for line
        ctx = t["n091_entry"]["native_gate_context"]
        sym = t["tradingsymbol"]
        out.append({"day": t["entry_time"][:10], "i": B.minute_of(t["entry_time"]), "j": B.minute_of(t["exit_time"]),
                    "strike": int(round(ctx["strike"])), "opt": "CE" if ctx["is_call"] else "PE",
                    "expiry": f"20{sym[5:7]}-{sym[7:9]}-{sym[9:11]}", "reason": t["exit_reason"],
                    "expert": t["entry_expert"], "gate": t.get("entry_gate") or "", "book": book,
                    "sig_key": (t["entry_time"][:16], int(round(ctx["strike"])), ctx["is_call"])})
    return out


def load_2022(year):
    if year != "2022":
        return _orig_load(year)
    p = HERE / "_local" / "sn01-cache-2022.pkl"
    if not p.exists():
        data = D.build_year("2022")
        p.write_bytes(pickle.dumps(data, protocol=pickle.HIGHEST_PROTOCOL))
    return pickle.loads(p.read_bytes())


def install(years):
    B.stream = stream_2022
    D.load_year = load_2022
    for mod in (B, L, C):
        mod.YEARS = years


def month_table(days):
    by = collections.defaultdict(float)
    for d, _w, n, _t, _l in days:
        by[d[:7]] += n
    return {m: round(v) for m, v in sorted(by.items())}


def main():
    Q.install()
    if MODE == "parity":
        install(("2023", "2024", "2025", "2026"))
        row, days, _log = Q.run(205.0)
        assert row["net"] == 850882, row["net"]
        print("PARITY OK", row["net"], len(days), flush=True)
        (HERE / "results-sn366-gold-parity.json").write_text(json.dumps({"net": row["net"], "sessions": len(days), "pass": True}, indent=1), encoding="utf-8")
        return
    out_path = HERE / "results-sn366-gold-2022.json"
    assert not out_path.exists(), "run once"
    D.DATASETS["2022"] = HERE / "_local" / "dataset-nifty-2022"
    install(("2022",))
    # mechanical fix (before any 2022 number): common.panel skips wallets without a "2023" year; this runner never uses
    # the panel row (only the day log and the trade log), so the panel is bypassed for the 2022 run
    C.panel = lambda r: {w: {} for w in r}
    res = {}
    for st in (205.0, 400.0):
        row, days, log = Q.run(st)
        mt = month_table(days)
        nets = [n for _d, _w, n, _t, _l in days]
        res[f"@{int(st)}"] = {"net": round(sum(nets)), "sessions": len(days), "trades": len(log), "days_won": sum(n > 0 for n in nets),
                              "days_lost": sum(n < 0 for n in nets), "worst_day": round(min(nets)), "best_day": round(max(nets)),
                              "refilled": round(sum(-n for n in nets if n < 0)), "months": mt,
                              "months_positive": sum(v > 0 for v in mt.values()), "worst_month": min(mt.values()),
                              "without_best_day": round(sum(nets) - max(nets)), "final_wallet": round(days[-1][1]) if days else None,
                              "by_reason": dict(collections.Counter(x["reason"] for x in log))}
        print(int(st), json.dumps({k: v for k, v in res[f"@{int(st)}"].items() if k != "months"}), flush=True)
    res["months@205"] = res["@205"]["months"]
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
