"""SN05 - more trading days for the Rs 15,000 wallet from the house strategy library (research only).

N11 trades about one session in six. SN04 showed that filling the other sessions with new active entries loses like
random entries. The O30m library (`2026-10-30-day-router`) holds 136 strategies replayed always-on by the shipped
engine over NIFTY 2024, 2025 and 2026, including 20 random-entry books (NULL00..NULL19).

SN05 builds a priority list: N11 first, then library strategies added greedily while they raise the training years'
net (each added book trades only when the wallet is free). Choose on two years, score on the third (all three ways);
run the same procedure with only the random books as candidates (the NULL). Wallet: Rs 15,000 fixed, one lot, the strike
one step further out of the money when one lot costs more, one position at a time, Rs 3,000 day limit, current Zerodha
charges + Rs 205 per lot per trade. N11 entries are in-sample; the library is seen data.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent / "2026-11-12-sn03")]

import sn03 as Z  # noqa: E402

LIB = Z.M.ROOT / "docs/research/fno/2026-10-30-day-router/_local"
FILES = {"2024": "results-raw-2024test-2024-1793419338.json", "2025": "results-raw-library-2025.json",
         "2026": "results-raw-library-2026.json"}
YEARS = ("2024", "2025", "2026")
MAX_ADD = 6
MIN_GAIN = 2000.0


def parse(t: dict, book: str) -> dict:
    sym = t["tradingsymbol"]
    return {"day": t["entry_time"][:10], "i": Z.minute_of(t["entry_time"]), "j": Z.minute_of(t["exit_time"]),
            "strike": int(sym[11:-2]), "opt": sym[-2:], "expiry": f"20{sym[5:7]}-{sym[7:9]}-{sym[9:11]}",
            "reason": t["exit_reason"], "expert": book, "gate": "", "book": book,
            "sig_key": (t["entry_time"][:16], int(sym[11:-2]), sym[-2:] == "CE")}


class LibYear(Z.Year):
    def __init__(self, year: str):
        super().__init__(year)
        d = json.loads((LIB / FILES[year]).read_text(encoding="utf-8"))
        self.library = {}
        for name, k in d["books"].items():
            if k in d["trades"]:
                by = {}
                for t in d["trades"][k]:
                    if t.get("status", "CLOSED") == "CLOSED":
                        s = parse(t, name)
                        by.setdefault(s["day"], []).append(s)
                self.library[name] = by

    def sigs(self, book: str) -> dict:
        if book in getattr(self, "library", {}):
            return self.library[book]
        return super().sigs(book)


def run(Y, books) -> dict:
    return Z.year_result(Y, {}, books=tuple(books))


def greedy(years: dict, train: tuple, candidates: list, start=("N11",)) -> list:
    chosen = list(start)
    base = {y: run(years[y], chosen) for y in train}
    for _ in range(MAX_ADD):
        best, best_gain, best_res = None, MIN_GAIN, None
        for c in candidates:
            if c in chosen:
                continue
            res = {y: run(years[y], chosen + [c]) for y in train}
            gain = sum(res[y]["net"] - base[y]["net"] for y in train)
            if gain > best_gain and all(res[y]["net"] >= base[y]["net"] - MIN_GAIN for y in train):
                best, best_gain, best_res = c, gain, res
        if best is None:
            break
        chosen.append(best)
        base = best_res
        print("   add", best, "+", round(best_gain), flush=True)
    return chosen


if __name__ == "__main__":
    years = {y: LibYear(y) for y in YEARS}
    names = sorted(set.intersection(*(set(years[y].library) for y in YEARS)))
    real = [n for n in names if not n.startswith("NULL") and not n.startswith("REF")]
    null = [n for n in names if n.startswith("NULL")]
    out = {"singles": {}, "loyo": {}, "final": {}}
    for n in ["N11"] + names:
        out["singles"][n] = {y: run(years[y], [n]) for y in YEARS}
    for held in YEARS + ("ALL",):
        train = tuple(y for y in YEARS if y != held) if held != "ALL" else YEARS
        for kind, cands in (("real", real), ("null", null)):
            print(f"fold {held} {kind}", flush=True)
            chosen = greedy(years, train, cands)
            res = {y: run(years[y], chosen) for y in YEARS}
            out["loyo" if held != "ALL" else "final"][f"{held}|{kind}"] = {"books": chosen, "years": res}
    (HERE / "results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    bench = {y: out["singles"]["N11"][y] for y in YEARS}
    print("benchmark N11", {y: (bench[y]["net"], bench[y]["green"], bench[y]["red"], bench[y]["none"]) for y in YEARS})
    for kind in ("real", "null"):
        h = [out["loyo"][f"{y}|{kind}"]["years"][y] for y in YEARS]
        print(f"held-out {kind}: nets", [x["net"] for x in h], "sum", sum(x["net"] for x in h),
              "won/lost/none", sum(x["green"] for x in h), sum(x["red"] for x in h), sum(x["none"] for x in h),
              "vs benchmark", sum(bench[y]["net"] for y in YEARS))
    f = out["final"]["ALL|real"]
    print("final books", f["books"], {y: (f["years"][y]["net"], f["years"][y]["green"], f["years"][y]["red"], f["years"][y]["none"]) for y in YEARS})
    top = sorted(((sum(v[y]["net"] for y in YEARS), n, [v[y]["net"] for y in YEARS], sum(v[y]["green"] + v[y]["red"] for y in YEARS))
                  for n, v in out["singles"].items()), reverse=True)[:12]
    for t in top:
        print("single", t)
