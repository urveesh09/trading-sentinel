"""SN366: the frozen N11 (EXAM_2022_N11.md) and N10 (EXAM_2022.md) exams on NIFTY 2022, through the house chain unchanged
(N08 -> N09 -> N09.1 -> N10 -> N10b -> N101 -> N11, n08_lab loaded through n08_shim with the 2022 / 2021L points).

Set the environment, not arguments (Windows workers re-import this file and inherit the environment):
  SN366_MODE=w2     N08_YEAR=TEST2025   evidence readers replaced by functions that read the ORIGINAL sources and years;
                                        N11, N09.1 CUSHION, N10 one try (STRICT) and N10 retry must equal their stored
                                        2025 trades (trade for trade) from an empty results folder
  SN366_MODE=w2neg  N08_YEAR=TEST2025   N11 with an EMPTY paper stream: must DIFFER from the stored N11 (the replacement
                                        reaches the workers); equality with the stored NO_STAND is reported
  SN366_MODE=diag   N08_YEAR=2021L|2022 N09's diag books (N08 and its one-lot brakes-off paper twin) into _local/n09
  SN366_MODE=exam   N08_YEAR=2022       every book both sheets need, once, into an empty folder; paper evidence = N11 sheet:
                                        2021L + 2022 one-lot paper trades (N101.paper_rows); N10 sheet: 2022 only (N10b
                                        WATCH shadow); only exits strictly before each decision are read (the house rule)
Scoring (house measures, screen_view.stats on a fresh Rs 2.5 lakh): net, worst day, worst fall %, worst trade, trades.
Answers exactly as the sheets state them; the stand-aside's fires = NO_STAND entries (entry time + contract) that N11 did
not take (a proxy for "real entries held back", disclosed). Random-entry median = median net of the 10 RANDOM BASE books.
"""
from __future__ import annotations

import json
import os
import statistics
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL = HERE / "_local"
MODE = os.environ.get("SN366_MODE")
assert MODE in ("w2", "w2neg", "diag", "exam", "score"), MODE
sys.path.insert(0, str(HERE))
import n08_shim  # noqa: E402

N = n08_shim.install()
SIM = HERE.parents[1] / "simulation"
sys.path.insert(0, str(SIM / "2026-11-02-fno-n11"))
import n11_lab as L  # noqa: E402
import screen_view as V  # noqa: E402

U = L.U
Bb = U.B
T, M, Z, Y = Bb.T, Bb.M, Bb.Z, Bb.Y
import no_retry  # noqa: E402

N09_ORIG = Z.LOCAL
N09_MINE = LOCAL / "n09"
YEAR = Z.B.YEAR if hasattr(Z, "B") else N.B.YEAR


def paper_rows_from(folder, years):
    rows = []
    for y in years:
        key = json.loads((folder / f"keys-diag-{y}.json").read_text())["DIAG"]
        for t in json.loads((folder / f"evals-{y}" / f"{key}.json").read_text())["trades"]:
            rows.append((datetime.fromisoformat(t["exit_time"]), t))
    return tuple(sorted(rows, key=lambda r: (r[0], r[1]["entry_time"], r[1]["tradingsymbol"])))


def install_evidence(folder, n11_years, watch_years):
    Z.LOCAL = folder
    cache = {}

    def paper_rows():
        if "p" not in cache:
            cache["p"] = paper_rows_from(folder, n11_years)
        return cache["p"]

    def shadow_names():
        return tuple(f"evals-{y}/{json.loads((folder / f'keys-diag-{y}.json').read_text(encoding='utf-8'))['DIAG']}.json" for y in watch_years)
    U.paper_rows = paper_rows
    Bb.shadow_names = shadow_names
    L.paper_stream.cache_clear()


ORIG_YEARS = ("2023", "2024", "2025", "2026")
if MODE == "w2":
    install_evidence(N09_ORIG, ORIG_YEARS, ORIG_YEARS)
    Y.EVALS = LOCAL / "w2-evals"
elif MODE == "w2neg":
    Z.LOCAL = N09_ORIG
    U.paper_rows = lambda: ()
    L.paper_stream.cache_clear()
    Y.EVALS = LOCAL / "w2neg-evals"
elif MODE == "diag":
    Z.LOCAL = N09_MINE
    Y.EVALS = N09_MINE / f"evals-{N.B.YEAR}"
elif MODE in ("exam", "score"):
    install_evidence(N09_MINE, ("2021", "2022"), ("2022",))
    Y.EVALS = LOCAL / "exam-evals-2022"
Y.EVALS.mkdir(parents=True, exist_ok=True)


def key_of(b):
    return Y.task_key(b, "year", N.C.WINDOW)


def run(books, jobs=3):
    assert not any(Y.EVALS.glob("*.json")) or MODE == "diag", "must start from an empty results folder"
    N.run_books(books, jobs)
    return {n: key_of(b) for n, b in books.items()}


def load(key, folder=None):
    return T.load(key, folder or Y.EVALS)


def w2():
    out_path = HERE / "results-sn366-gateW2.json"
    assert not out_path.exists()
    books = {"N11": L.panel_books()["N11"], "CUSHION": M.candidates()["CUSHION"], "STRICT": no_retry.strict("R2_THIRD_CW_STRICT"),
             "N10": L.control_books()["N10"]}
    keys = run(books)
    n11l, n091l, n10l = SIM / "2026-11-02-fno-n11/_local", SIM / "2026-11-01-fno-n091/_local", SIM / "2026-11-01-fno-n10/_local"
    ref = {"N11": (json.loads((n11l / "keys-panel-2025.json").read_text())["N11"], n11l / "evals"),
           "CUSHION": (json.loads((n091l / "keys-primary-2025.json").read_text())["CUSHION"], n091l / "evals"),
           "STRICT": (json.loads((n10l / "keys-strict-2025.json").read_text())["STRICT"], n10l / "evals"),
           "N10": (json.loads((n10l / "keys-panel2-2025.json").read_text())["R2_THIRD_CW"], n10l / "evals")}
    res = {}
    for n, (k, d) in ref.items():
        mine, old = load(keys[n]), load(k, d)
        res[n] = {"economics_equal": T.economics(mine) == T.economics(old), "trades": len(mine), "net": round(sum(t["net_pnl"] for t in mine), 2),
                  "stored_net": round(sum(t["net_pnl"] for t in old), 2)}
    res["pass"] = all(v["economics_equal"] for v in res.values() if isinstance(v, dict))
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


def w2neg():
    out_path = HERE / "results-sn366-gateW2-negative.json"
    assert not out_path.exists()
    keys = run({"N11": L.panel_books()["N11"]})
    n11l = SIM / "2026-11-02-fno-n11/_local"
    panel = json.loads((n11l / "keys-panel-2025.json").read_text())
    mine = load(keys["N11"])
    stored, nostand = load(panel["N11"], n11l / "evals"), load(panel["NO_STAND"], n11l / "evals")
    res = {"differs_from_stored_N11": T.economics(mine) != T.economics(stored), "equals_stored_NO_STAND": T.economics(mine) == T.economics(nostand),
           "trades": len(mine), "net": round(sum(t["net_pnl"] for t in mine), 2), "stored_N11_net": round(sum(t["net_pnl"] for t in stored), 2),
           "stored_NO_STAND_net": round(sum(t["net_pnl"] for t in nostand), 2)}
    res["pass"] = res["differs_from_stored_N11"]
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


def diag():
    keys = run(Z.diag_books())
    (N09_MINE / f"keys-diag-{N.B.YEAR}.json").write_text(json.dumps(keys, indent=1), encoding="utf-8")
    counts = {n: len(load(k)) for n, k in keys.items()}
    print("DIAG", N.B.YEAR, json.dumps(counts), flush=True)          # counts only; the paper trades are evidence, scored in the exam


def stats(trades):
    # disclosed fix (Nov 16, after the replays, before any score was computed or shown): screen_view.stats needs an exit
    # time; a trade with status UNRESOLVED has none (only RANDOM|09 BASE / ADD, one trade each, entry 2022-04-29 10:25).
    # Such trades are left out of the stats and counted.
    done = [t for t in trades if "exit_time" in t]
    s = V.stats(done)
    return {"net": round(s["net"]), "worst_day": round(s["worst_day"]), "fall_pct": round(s["fall"], 2), "worst_trade": round(s["worst_trade"]), "trades": s["n"],
            "unresolved": len(trades) - len(done)}


def exam():
    out_path = HERE / "results-sn366-exam-2022.json"
    assert not out_path.exists(), "the exam is run once"
    books = {**{f"panel|{k}": v for k, v in L.panel_books().items()}, **{f"ctrl|{k}": v for k, v in L.control_books().items()},
             "CUSHION": M.candidates()["CUSHION"], "STRICT": no_retry.strict("R2_THIRD_CW_STRICT"),
             **{f"rand|{k}": v for k, v in L.random_books().items()}}
    keys = run(books)
    (LOCAL / "keys-exam-2022.json").write_text(json.dumps(keys, indent=1), encoding="utf-8")
    score_exam(keys)


def score():
    """Scores the saved exam replays (keys-exam-2022.json); no replay is run again."""
    score_exam(json.loads((LOCAL / "keys-exam-2022.json").read_text(encoding="utf-8")))


def score_exam(keys):
    out_path = HERE / "results-sn366-exam-2022.json"
    assert not out_path.exists(), "the exam is scored once"
    trades = {n: load(k) for n, k in keys.items()}
    st = {n: stats(t) for n, t in trades.items()}
    n11, n08, cush, one, retry = st["panel|N11"], st["ctrl|N08"], st["CUSHION"], st["STRICT"], st["ctrl|N10"]
    nost, noadd, novol = st["panel|NO_STAND"], st["panel|NO_ADD"], st["panel|NO_VOL"]
    others = [n08, cush, one, retry]
    taken = {(t["entry_time"], t["tradingsymbol"]) for t in trades["panel|N11"]}
    fires = sum(1 for t in trades["panel|NO_STAND"] if (t["entry_time"], t["tradingsymbol"]) not in taken)
    rb = [st[n]["net"] for n in st if n.startswith("rand|") and n.endswith("|BASE")]
    n11_sheet = {
        "A_beats_the_others": n11["net"] >= max(o["net"] for o in others) and abs(n11["worst_day"]) <= min(abs(o["worst_day"]) for o in others) + 1000
                              and n11["fall_pct"] <= min(o["fall_pct"] for o in others) + 0.5,
        "B_stand_aside": ("not tested" if fires < 10 else (n11["net"] >= nost["net"] or (n11["fall_pct"] <= nost["fall_pct"] - 2.0 and n11["net"] >= nost["net"] - 10000))),
        "B_fires_proxy": fires,
        "C_honest_add": n11["net"] >= noadd["net"] and abs(n11["worst_day"]) <= abs(noadd["worst_day"]) + 1000,
        "D_size_by_volatility": abs(n11["worst_day"]) <= abs(novol["worst_day"]) and n11["net"] >= novol["net"] - 0.1 * abs(novol["net"]),
        "random_entry_median_net": round(statistics.median(rb)) if rb else None, "random_base_books": len(rb)}
    b_yes = retry["net"] > one["net"] and abs(retry["worst_day"]) <= abs(one["worst_day"]) + 1000
    n10x = retry if b_yes else one
    n10_sheet = {"A_earned_lot": one["net"] >= cush["net"] and abs(one["worst_day"]) <= abs(cush["worst_day"]) + 1000,
                 "B_retry": b_yes,
                 "C_beats_N08": n10x["net"] >= n08["net"] and abs(n10x["worst_day"]) <= abs(n08["worst_day"]) and n10x["fall_pct"] <= n08["fall_pct"],
                 "D_watch_one_account_2022_2026": "pending (a separate carry run)"}
    res = {"sessions_scored": "242 sessions, 190 with options (fewer than 200: scored as it exists, per N10's sheet)",
           "stats": st, "N11_sheet": n11_sheet, "N10_sheet": n10_sheet}
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
    show = ("panel|N11", "ctrl|N08", "CUSHION", "STRICT", "ctrl|N10", "panel|NO_STAND", "panel|NO_ADD", "panel|NO_VOL", "ctrl|VOL_CLOCK", "panel|DOUBLE")
    print(json.dumps({n: st[n] for n in show}, indent=1))
    print(json.dumps({"N11_sheet": n11_sheet, "N10_sheet": n10_sheet}, indent=1))


if __name__ == "__main__":
    {"w2": w2, "w2neg": w2neg, "diag": diag, "exam": exam, "score": score}[MODE]()
