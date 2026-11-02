"""O30r risk spectrum - research only. No runtime module imports this file.

Owner (Oct 30): "do we have a system model that can perform average good in both years? ... are we being too
conservative? ... test multiple parameters of the system from the conservative we have right now which max looses
somewhere around 5 thousand in a day to more radical that can loose everything in one shot, the whole spectrum between
them you test for me and tell me which level of conservativeness felt the best in the 2 years. go on and ensure
correctness".

Every number comes from the shipped code replayed at that level, never from the sizing simulator: O30s showed the
simulator can be wrong once brakes decide which trades happen. All limits are settings, so a level is a set of settings
(the shipped planner sizes it: floor(money x risk share / (premium x lot x premium stop)), within own cash).

THE SPECTRUM (money lost at the premium stop, as a share of the money, per trade; the premium stop is 25% of what was
paid, so the money in one trade is 4 x the share):
  SHIPPED      today, exactly: 2%, capped at Rs 6,250, 2 lots (3 when proven), 15% of the money in premium, all brakes;
  R1 ... R25   no lot cap, no rupee cap, own cash only: 1, 2, 3, 4, 5, 6, 8, 10, 12.5, 15, 20, 25% (25% = all the money
               in one trade with the 25% stop), each with brakes OFF and with brakes SCALED to the level (day 1.5 x,
               week 3 x, month 5 x, total 7.5 x, size cuts at 2 x and 4 x: at R2 these are the shipped percentages);
  ALLIN_S50    all the money in one trade, stop at 50% of the premium;
  ALLIN_NOPREM all the money in one trade, no premium stop (the underlying stop stays);
  ALLIN_NOSTOP all the money in one trade, no stops at all, no time stop, held to 15:10: this one can lose everything.

THE BOOKS: LIVE (today), BEST (LIVE + TPB on closed days), TPB, each as it is and with the O30s rule "+rule" (pass over
a stretched entry).

THE COST: the replay's own prices and charges are flattering, so the main runs put an extra cost INSIDE the money path:
Rs 200 per lot per trade + Rs 5 per lot for each lot in the order (a bigger order pays more: at 50 lots, Rs 450 per lot).
That slope is an assumption; no depth data exists. "AS" runs have no extra cost, for LIVE, BEST+rule and TPB+rule.

THE ACCOUNT: each year alone from Rs 2.5 lakh, and one account carried from 2025 into 2026 ("carry": the 2025 trades are
the book's history, so a wipe-out stays wiped out and the shipped brakes keep their memory).

SENSITIVITY (never chosen): at R5, brakes off, with the extra cost, for BEST+rule and TPB+rule, one change at a time:
premium stop 15 / 40 / 60 / none; underlying stop x 0.75 / 1.5 / 2; trades a day 1 / 2 / 5; one position at a time.

Declared before any scoring (freeze.json): all of the above and RULE. Both years are seen; nothing changes on this.

    O30C_YEAR=2025 python lab_r.py smoke
    python lab_r.py freeze                                                        # commit and push freeze.json alone
    python ../run_slice.py --env O30C_YEAR=2025 -- <folder>/lab_r.py run --jobs 5  # repeat until DONE, then 2026
    python analyze_r.py
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
sys.path.insert(0, str(ROOT / "docs/research/fno/2026-10-30-earning-power"))
import lab_s2 as T  # noqa: E402  (the O30s machinery: year setup, the stretched-entry rule)

S, C, Y, G, O27F, replay = T.S, T.C, T.Y, T.G, T.O27F, T.S.replay
from config import settings  # noqa: E402

LOCAL = HERE / "_local"
Y.EVALS = LOCAL / "evals"
Y.KEEP = (*Y.KEEP, "extra_cost")
BASES = ("LIVE", "LIVE+rule", "BEST", "BEST+rule", "TPB", "TPB+rule")
AS_BASES = ("LIVE", "BEST+rule", "TPB+rule")
SHARES = (0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.125, 0.15, 0.20, 0.25)
COST = (200.0, 5.0)


def share_name(r: float) -> str:
    return f"R{r * 100:g}"


def unlimited(risk: float, stop: float = 0.25) -> dict:
    return {"FNO_MAX_RISK_PCT": risk, "FNO_STOP_PREMIUM_PCT": stop, "FNO_MAX_LOSS_PER_TRADE": 1e12,
            "FNO_MAX_STRUCTURAL_LOSS_PER_TRADE": 1e12, "FNO_MAX_LOTS": 100_000, "FNO_MAX_LOTS_PROVEN": 100_000,
            "FNO_MAX_OPEN_PREMIUM_PCT": 1.0}


BRAKES_OFF = {"FNO_ADAPTIVE_RISK_ENABLED": False, "FNO_DAILY_KILL_PCT": 9.0, "FNO_WEEKLY_KILL_PCT": 9.0,
              "FNO_MONTHLY_KILL_PCT": 9.0, "FNO_MAX_DRAWDOWN_PCT": 0.999, "FNO_MAX_CONSECUTIVE_LOSSES": 1_000_000,
              "FNO_TWO_STRIKE_LOSSES": 1_000_000}


def brakes_scaled(r: float) -> dict:
    return {"FNO_DAILY_KILL_PCT": min(0.95, 1.5 * r), "FNO_WEEKLY_KILL_PCT": min(0.95, 3 * r),
            "FNO_MONTHLY_KILL_PCT": min(0.95, 5 * r), "FNO_MAX_DRAWDOWN_PCT": min(0.95, 7.5 * r),
            "FNO_RISK_CUT1_DRAWDOWN_PCT": min(0.90, 2 * r), "FNO_RISK_CUT2_DRAWDOWN_PCT": min(0.90, 4 * r)}


def levels() -> dict:
    """level name -> {"cfg": settings, optional "nostop", "exit", "stop_k"}."""
    out = {"SHIPPED": {"cfg": {}}}
    for r in SHARES:
        out[f"{share_name(r)}|OFF"] = {"cfg": {**unlimited(r), **BRAKES_OFF}}
        out[f"{share_name(r)}|SCALED"] = {"cfg": {**unlimited(r), **brakes_scaled(r)}}
    out["ALLIN_S50"] = {"cfg": {**unlimited(0.5, 0.5), **BRAKES_OFF}}
    out["ALLIN_NOPREM"] = {"cfg": {**unlimited(1.0, 1.0), **BRAKES_OFF}}
    out["ALLIN_NOSTOP"] = {"cfg": {**unlimited(1.0, 1.0), **BRAKES_OFF}, "nostop": True, "exit": "HOLD"}
    return out


def sensitivities() -> dict:
    base = {**unlimited(0.05), **BRAKES_OFF}
    out = {}
    for s in (0.15, 0.40, 0.60, 1.0):
        out[f"S{int(s * 100)}"] = {"cfg": {**base, "FNO_STOP_PREMIUM_PCT": s}}
    for k in (0.75, 1.5, 2.0):
        out[f"K{k:g}"] = {"cfg": {**base, "FNO_TIME_STOP_MIN_R": 0.5 / k}, "stop_k": k}   # the time stop keeps its points
    for n in (1, 2, 5):
        out[f"T{n}"] = {"cfg": {**base, "FNO_MAX_TRADES_PER_DAY": n}}
    out["C1"] = {"cfg": {**base, "FNO_MAX_CONCURRENT": 1}}
    return out


def base_book(name: str, level: dict, cost: bool, label: str) -> dict:
    root, rule = (name[:-5], True) if name.endswith("+rule") else (name, False)
    members = S._members(root, level.get("exit", "OWN"))
    book = {"members": [Y.canonical_member(m) for m in members], "o30r": label, "cfg": level["cfg"]}
    if rule:
        book["skip"] = T.LIMIT
    if cost:
        book["cost"] = list(COST)
    for k in ("nostop", "stop_k"):
        if k in level:
            book[k] = level[k]
    return book


def year_books() -> dict:
    out = {}
    for name, level in levels().items():
        for base in BASES:
            out[f"{base}|{name}|COST"] = base_book(base, level, True, name)
        for base in AS_BASES:
            if not name.endswith("|SCALED"):
                out[f"{base}|{name}|AS"] = base_book(base, level, False, name)
    for name, level in sensitivities().items():
        for base in ("BEST+rule", "TPB+rule"):
            out[f"{base}|SENS|{name}|COST"] = base_book(base, level, True, f"SENS|{name}")
    return out


RULE = {
    "measure": "the money with the extra cost inside the path, from the shipped code at that level",
    "balanced": "THE ANSWER. Among all books and levels: both years > 0 (each alone from Rs 2.5 lakh), at most one of the "
                "four half-years negative, at least 40 trades a year, the carried account's largest fall <= 25% of its "
                "running peak, no wipe-out. Highest worse-year net wins",
    "most_money": "the highest carried two-year end, whatever the fall (shown with its fall)",
    "lowest_risk": "the smallest carried fall with both years > 0",
    "peak_check": "for each book, the level with the most money on 2025 alone and on 2026 alone, brakes off. A level is "
                  "'inside the margin' if it is at most half the smaller of those two (estimates err, and betting past "
                  "the peak earns less: Kelly). The balanced pick is reported with this check",
    "cross_year": "the same balanced rule chosen on 2025 alone (fall on 2025 only) and scored on 2026, and the reverse",
    "wipe_out": "a carried account ending under Rs 10,000",
    "correctness": "analyze_r.check_book on every replay: all closed, charges recomputed, entries per day, own cash, lots "
                   "recomputed from the planner's formula (brakes off); SHIPPED|AS reproduces the stored rupees exactly; "
                   "brakes-off levels compared with the O30s simulator; a sample replayed twice",
    "status": "NIFTY 2025 and Jan - Oct 2026 are both seen, and the +rule books were found by looking at them. A pick is a "
              "candidate for the 2024 exam and forward data. Nothing in the system changes on this; the owner decides. "
              "The Nov 2 real-money test stays one lot.",
}


# ---- the patches: settings per book, the cost in the path, the carried history, the stops ----------------------------

_COST = [0.0, 0.0]
_prev_close = replay._close_record


def close_record(leg, at, price, reason, fut):
    record, final = _prev_close(leg, at, price, reason, fut)
    if _COST[0] or _COST[1]:
        extra = (_COST[0] + _COST[1] * leg.lots) * leg.lots
        final -= extra
        record["net_pnl"] = round(record["net_pnl"] - extra, 4)
        record["extra_cost"] = round(extra, 2)
    return record, final


replay._close_record = close_record
_prev_run = replay.SingleLegReplay.run


def history(key: str) -> list:
    """A carried book's earlier trades, as the replay's prior closes."""
    data = json.loads((Y.EVALS / f"{key}.json").read_text(encoding="utf-8"))
    return [(datetime.fromisoformat(t["exit_time"]), float(t["net_pnl"]), "SINGLE_LEG")
            for t in data["trades"] if t.get("net_pnl") is not None]


def run_book(self, start, end):
    cfg = self.book.get("cfg") or {}
    before = {k: getattr(settings, k) for k in cfg}
    carry = self.book.get("carry")
    try:
        for k, v in cfg.items():
            setattr(settings, k, v)
        _COST[:] = self.book.get("cost") or [0.0, 0.0]
        if carry:
            closes = history(carry)
            self.data.paper_closes = lambda: closes
        result = _prev_run(self, start, end)
        result["notes"]["start_equity"] = result["start_equity"]
        return result
    finally:
        for k, v in before.items():
            setattr(settings, k, v)
        _COST[:] = [0.0, 0.0]
        if carry:
            del self.data.paper_closes


Y.BookReplay.run = run_book
_prev_entry = Y.BookReplay._entry


def entry(self, book, obs, frame, day, now):
    before = book.next_id
    _prev_entry(self, book, obs, frame, day, now)
    if book.next_id == before:
        return
    leg = book.open[before]
    if self.book.get("nostop"):
        side = 1 if leg.direction == "LONG" else -1
        leg.stop_underlying = leg.entry_underlying - side * 1e7
    elif self.book.get("stop_k"):
        leg.stop_underlying = leg.entry_underlying + (leg.stop_underlying - leg.entry_underlying) * self.book["stop_k"]


Y.BookReplay._entry = entry


# ---- freeze, run, smoke, verify ---------------------------------------------------------------------------------------

def year_bindings() -> dict:
    out = C.year_bindings()
    for folder, names in ((HERE, ("lab_r.py", "analyze_r.py", "test_lab_r.py")),
                          (ROOT / "docs/research/fno/2026-10-30-earning-power", ("lab_s.py", "lab_s2.py", "analyze_s.py"))):
        for n in names:
            out["sources"][(folder / n).relative_to(ROOT).as_posix()] = Y.grid._sha(folder / n)
    return out


def freeze() -> None:
    parts = {}
    for year in ("2025", "2026"):
        out = subprocess.check_output([sys.executable, str(HERE / "lab_r.py"), "bindings"], cwd=ROOT,
                                      env={**os.environ, "O30C_YEAR": year})
        parts[year] = json.loads(out.decode("utf-8").strip().splitlines()[-1])
    Y.write_new(HERE / "freeze.json", {"schema": "o30r_risk_spectrum_v1", "bindings": parts, "levels": levels(),
                                       "sensitivities": sensitivities(), "bases": BASES, "as_bases": AS_BASES, "cost": COST,
                                       "books": year_books(), "rule": RULE, "qualification": "NOT_ASSESSED",
                                       "can_place_orders": False})
    print("frozen", len(year_books()), "books per year, plus the carried 2026 runs")


def _init() -> None:
    C._init()


def _atomic(path: Path, value) -> None:
    tmp = path.with_name(path.name + f".{os.getpid()}.part")
    tmp.write_text(json.dumps(value), encoding="utf-8")
    os.replace(tmp, path)


def carried_books() -> dict:
    keys = json.loads((LOCAL / "keys-2025.json").read_text(encoding="utf-8"))
    return {f"{n}|carry": {**b, "carry": keys[n]} for n, b in year_books().items() if "|SENS|" not in n}


def run(jobs: int) -> None:
    frozen = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    assert frozen["bindings"][C.YEAR] == json.loads(json.dumps(year_bindings(), default=str)), "inputs changed"
    rel = (HERE / "freeze.json").relative_to(ROOT).as_posix()
    assert json.loads(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)) == frozen, "not committed"
    assert 1 <= jobs <= 7
    O27F.deny_network()
    C.table("year")
    all_books = dict(year_books())
    if C.YEAR == "2026":
        all_books.update(carried_books())
    LOCAL.mkdir(exist_ok=True)
    with ProcessPoolExecutor(max_workers=jobs, initializer=_init) as ex:
        runner = Y.Runner(ex, jobs)
        runner.run(list(all_books.values()), source="year", window=C.WINDOW)
    _atomic(LOCAL / f"keys-{C.YEAR}.json", {n: Y.task_key(b, "year", C.WINDOW) for n, b in all_books.items()})
    print("DONE", C.YEAR, len(all_books), flush=True)


def smoke() -> None:
    """A book at several levels over January of the chosen year: proves the plumbing, scores nothing."""
    O27F.deny_network()
    Y.speedups()
    Y.EVALS = LOCAL / "smoke"
    window = (f"{C.YEAR}-01-01", f"{C.YEAR}-01-31")
    C.table("year")
    Y._worker_init()
    books = year_books()
    for name in ("TPB|SHIPPED|COST", "TPB|R10|OFF|COST", "TPB|R25|OFF|COST", "TPB|ALLIN_NOSTOP|COST", "TPB+rule|R5|SCALED|COST"):
        _key, trades = Y.evaluate((books[name], "year", window))
        lots = sorted({t.get("lots_at_exit") for t in trades})
        print(f"smoke {C.YEAR} {name}: {len(trades)} trades, lots {lots[:6]}{'...' if len(lots) > 6 else ''}, exits "
              f"{sorted({t.get('exit_reason') for t in trades})} (plumbing only)", flush=True)


def verify() -> None:
    """A sample replayed again into another folder: the same book must give the same trades."""
    O27F.deny_network()
    Y.speedups()
    C.table("year")
    Y._worker_init()
    keys = json.loads((LOCAL / f"keys-{C.YEAR}.json").read_text(encoding="utf-8"))
    books = year_books()
    same = {}
    for name in ("TPB+rule|R5|OFF|COST", "BEST+rule|R10|SCALED|COST", "LIVE|SHIPPED|COST"):
        first = json.loads((LOCAL / "evals" / f"{keys[name]}.json").read_text(encoding="utf-8"))["trades"]
        Y.EVALS = LOCAL / "verify"
        _key, again = Y.evaluate((books[name], "year", C.WINDOW))
        Y.EVALS = LOCAL / "evals"
        same[name] = json.loads(json.dumps(again)) == first
    print("REPLAYED TWICE", C.YEAR, same, flush=True)
    _atomic(LOCAL / f"verify-{C.YEAR}.json", same)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=["bindings", "freeze", "run", "smoke", "verify"])
    cli.add_argument("--jobs", type=int, default=5)
    a = cli.parse_args()
    if a.action == "bindings":
        print(json.dumps(year_bindings(), default=str))
    else:
        {"freeze": freeze, "run": lambda: run(a.jobs), "smoke": smoke, "verify": verify}[a.action]()
