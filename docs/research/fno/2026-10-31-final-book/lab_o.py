"""O31b - the final book at today's lot limits - research only. No runtime module imports this file.

Owner (Oct 31, after the 2024 exam): "how do we improve it? ... We should have a lot limit as original as we have now go
ahead test that and in general, give me a overall output of what do you think? Should we have as a final features and
option strategy and one that will be consistent and ensure that losses are less also just like how we are having."

All three years (NIFTY 2024, 2025, Jan - Oct 2026) are now SEEN. Nothing here can be proof, so the method is built to catch
luck rather than to find the best-looking row:

BASE: the four strategies with the stretched-entry rule at today's limits (the only book positive in all three years after
the assumed cost). Every variant changes ONE thing from BASE, with one textbook setting and no grids:
  the lot limit; the risk share; the day filter; which strategies; the exits and stops; how often it trades; the brakes; the
  contract's delta; the rule's own limit; an extra strategy on closed days.

Each variant is replayed exactly through the shipped code on each year alone from Rs 2.5 lakh, with the O30r extra cost
inside the money path. Passing needs help in EVERY year and a paired weekly t of at least 2 (RULE). If changes were coin
flips, about 1 in 8 would still help in all three years, so about 6 of 46 would pass on that test alone.

The continuous account: BASE and the live book carried from Jan 2024 to Oct 2026 with no restart, as the shipped permanent
stop would actually behave.

    O30F_YEAR=2024 python lab_o.py smoke
    python lab_o.py freeze                                                 # commit and push freeze.json alone
    python ../run_slice.py --env O30F_YEAR=2024 -- <folder>/lab_o.py run --jobs 5     # repeat until DONE
    python ../run_slice.py --env O30C_YEAR=2025 -- <folder>/lab_o.py run --jobs 5     # needs 2024's keys (the carried runs)
    python ../run_slice.py --env O30C_YEAR=2026 -- <folder>/lab_o.py run --jobs 5     # needs 2024's and 2025's
    python analyze_o.py
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
FNO = ROOT / "docs/research/fno"
sys.path[:0] = [str(HERE), str(FNO / "2026-10-30-risk-spectrum"), str(FNO / "2026-10-30-day-router")]
if os.environ.get("O30F_YEAR") == "2024":
    import lab_f  # noqa: E402,F401  (must come first: points the machinery below at the sealed 2024 data)
import lab_m  # noqa: E402,F401  (the compound gates)
import lab_r as L  # noqa: E402

import pandas as pd  # noqa: E402

T, S, C, Y, G, O27F = L.T, L.S, L.C, L.Y, L.G, L.O27F
F = C.F
import lab_i  # noqa: E402

YEAR = "2024" if os.environ.get("O30F_YEAR") == "2024" else C.YEAR
YEARS = ("2024", "2025", "2026")
LOCAL = HERE / "_local"
Y.EVALS = LOCAL / "evals"
ADX = "adx_abs25:HIGH"
FADE = {"level": "OR20", "stop": "STRUCT", "target_r": 2.4, "exit": "LIVE"}     # the O29i pick shown to the owner


# ---- two more day sides, known before the session ----------------------------------------------------------------------

_prev_table = C.table
_sides_done: set = set()


def extra_sides(rows: dict, sessions: list, expiries: list, adx: pd.Series) -> None:
    """adx_abs30: yesterday's ADX(14) >= 30. dte2: HIGH when at least 2 sessions remain to the weekly expiry, LOW on the
    session before it (and on the expiry itself, where the book makes no entry anyway)."""
    order = {d: i for i, d in enumerate(sessions)}
    for day, row in rows.items():
        side = row.setdefault("side", {})
        prior = adx.index[adx.index < pd.Timestamp(day)]
        side["adx_abs30"] = None if len(prior) < 60 else ("HIGH" if float(adx.loc[prior[-1]]) >= 30 else "LOW")
        expiry = next((e for e in expiries if e >= day), None)
        if day in order and expiry in order:
            side["dte2"] = "HIGH" if order[expiry] - order[day] >= 2 else "LOW"
        else:      # an expiry outside the data: the calendar says it is not the next session only if it is a week away
            side["dte2"] = "HIGH" if expiry is None or (pd.Timestamp(expiry) - pd.Timestamp(day)).days >= 3 else "LOW"


def table(source: str) -> dict:
    rows = _prev_table(source)
    if source not in _sides_done:
        manifest = json.loads((Y.YEAR / "manifest.json").read_text(encoding="utf-8"))
        extra_sides(rows, manifest["sessions"], manifest["option_expiries"], F.adx(F.daily_bars()))
        _sides_done.add(source)
    return rows


C.table = table
Y.table = table


# ---- the carried account: more than one earlier year ----------------------------------------------------------------

def history(key) -> list:
    out = []
    for k in key if isinstance(key, list) else [key]:
        data = json.loads((Y.EVALS / f"{k}.json").read_text(encoding="utf-8"))
        out += [(datetime.fromisoformat(t["exit_time"]), float(t["net_pnl"]), "SINGLE_LEG")
                for t in data["trades"] if t.get("net_pnl") is not None]
    return sorted(out, key=lambda r: r[0])


L.history = history


# ---- the books -----------------------------------------------------------------------------------------------------

def book(name: str, members: list | None = None, cfg: dict | None = None, skip: float | None = T.LIMIT, cost: bool = True,
         **extra) -> dict:
    out = {"members": [Y.canonical_member(m) for m in (members or S._members("LIVE"))], "o31": name, "cfg": cfg or {}}
    if skip is not None:
        out["skip"] = skip
    if cost:
        out["cost"] = list(L.COST)
    return {**out, **extra}


def gated(gate: str) -> list:
    return [Y.named(c, gate) for c in Y.NAMED]


def day(side: str) -> dict:
    return {"members": gated(f"{ADX}&{side}"), "router": "o30m"}


def dropped(name: str) -> list:
    return [m for m in S._members("LIVE") if m["name"] != name]


def lots(n: int) -> dict:
    return {"FNO_MAX_LOTS": n, "FNO_MAX_LOTS_PROVEN": n}


VARIANTS = {
    # the lot limit (today: 2, or 3 when proven)
    "LOTS|1": {"cfg": lots(1)}, "LOTS|2": {"cfg": lots(2)}, "LOTS|3": {"cfg": lots(3)}, "LOTS|5": {"cfg": lots(5)},
    # the risk share (today: 2%)
    "RISK|1": {"cfg": {"FNO_MAX_RISK_PCT": 0.01}}, "RISK|1.5": {"cfg": {"FNO_MAX_RISK_PCT": 0.015}},
    "RISK|2.5": {"cfg": {"FNO_MAX_RISK_PCT": 0.025}},
    # the day filter (today: yesterday's ADX >= 25)
    "ADX|20": {"members": gated("adx_abs20:HIGH")}, "ADX|30": {"members": gated("adx_abs30:HIGH")},
    "DAY|drive": day("open_drive:HIGH"), "DAY|wide_open": day("or_width:HIGH"), "DAY|vol_high": day("rv20:HIGH"),
    "DAY|not_expiry_eve": day("dte2:HIGH"), "DAY|with_dmi": {"case": "dmi"}, "DAY|with_ema": {"case": "ema"},
    # which strategies, and their order
    "DROP|SHIPPED": {"members": dropped("SHIPPED")}, "DROP|OR20": {"members": dropped("OR20")},
    "DROP|EFF": {"members": dropped("EFF")}, "DROP|TPB": {"members": dropped("TPB")},
    "ORDER|tpb_first": {"members": C.tpb_first(S._members("LIVE"))},
    # exits and stops
    "EXIT|LIVE": {"members": S._members("LIVE", "LIVE")}, "EXIT|LATE": {"members": S._members("LIVE", "LATE")},
    "EXIT|LOOSE": {"members": S._members("LIVE", "LOOSE")}, "EXIT|RUN": {"members": S._members("LIVE", "RUN")},
    "LOCK|off": {"cfg": {"FNO_PROFIT_LOCK_ENABLED": False}},
    "PSTOP|20": {"cfg": {"FNO_STOP_PREMIUM_PCT": 0.20}}, "PSTOP|35": {"cfg": {"FNO_STOP_PREMIUM_PCT": 0.35}},
    "USTOP|0.75": {"cfg": {"FNO_TIME_STOP_MIN_R": 0.5 / 0.75}, "stop_k": 0.75},
    "USTOP|1.25": {"cfg": {"FNO_TIME_STOP_MIN_R": 0.5 / 1.25}, "stop_k": 1.25},
    # how often
    "TRADES|1": {"cfg": {"FNO_MAX_TRADES_PER_DAY": 1}}, "TRADES|2": {"cfg": {"FNO_MAX_TRADES_PER_DAY": 2}},
    "ONE_AT_A_TIME": {"cfg": {"FNO_MAX_CONCURRENT": 1}},
    "LATEST|12:30": {"cfg": {"FNO_ENTRY_END_MIN": 750}}, "LATEST|13:30": {"cfg": {"FNO_ENTRY_END_MIN": 810}},
    # the brakes
    "BRAKES|all_off": {"cfg": L.BRAKES_OFF}, "BRAKES|no_two_strike": {"cfg": {"FNO_TWO_STRIKE_LOSSES": 1_000_000}},
    "BRAKES|no_size_cuts": {"cfg": {"FNO_ADAPTIVE_RISK_ENABLED": False}},
    "BRAKES|no_total_stop": {"cfg": {"FNO_MAX_DRAWDOWN_PCT": 0.999}},
    # the contract
    "DELTA|45": {"cfg": {"FNO_TARGET_DELTA": 0.45}}, "DELTA|65": {"cfg": {"FNO_TARGET_DELTA": 0.65}},
    # the rule's own limit, and no rule at all (= today's live book)
    "SKIP|25": {"skip": 0.25}, "SKIP|75": {"skip": 0.75}, "SKIP|100": {"skip": 1.0}, "SKIP|none": {"skip": None},
    # an extra strategy on the days the gate is closed
    "ADD|tpb_closed": {"members": S._members("BEST")},
    "ADD|fade_closed": {"members": [*S._members("LIVE"), lab_i.side_member("FADE", gate="adx_abs25:LOW", **FADE)]},
}
CARRIED = ("BASE", "BASE|AS", "SKIP|none")


def books() -> dict:
    out = {"BASE": book("BASE"), "BASE|AS": book("BASE|AS", cost=False)}
    for name, v in VARIANTS.items():
        out[name] = book(name, **v)
    return out


RULE = {
    "measure": "rupees from Rs 2.5 lakh, each year alone, exact replays, with the O30r extra cost in the money path",
    "parity": "BASE must reproduce -219 / +4,805 / +47,333, SKIP|none -33,726 / -38,681 / +61,674, BASE|AS +17,358 / "
              "+26,230 / +79,247, or the setup differs and nothing here counts",
    "improves": "a change improves BASE only if it nets more in EVERY year, its fall is at most 1 point above BASE's in every "
                "year, it makes at least 40 trades in every year, and the paired weekly difference from BASE has t >= 2",
    "safer": "a change is safer if its fall in BASE's worst year is at least 2 points lower, its worst year's net is not below "
             "BASE's worst year, and its three-year net is at least 90% of BASE's. Reported separately; it trades money for "
             "safety, and the owner chooses",
    "selection_luck": "for each year held out: among BASE and all variants with falls <= 25% and 40+ trades in the other two, "
                      "take the highest worse-of-two net, and score it on the held-out year against BASE. If this does not "
                      "beat BASE in all three, choosing among these variants is not shown to help",
    "lots": "the lot-limit answer: the highest three-year net among LOTS|1,2,3,5 and BASE with every year's fall <= 15%",
    "final": "FINAL = BASE plus every change that improves. If two or more improve, their combination is replayed and must "
             "itself improve on BASE; each improving change is also applied to the 20 random-entry books and reported. If none "
             "improves, FINAL = BASE",
    "correctness": "analyze_r.check_book on every replay; a variant with trades identical to BASE is reported as no effect",
    "status": "NIFTY 2024, 2025 and Jan - Oct 2026 are all seen. A pass is a candidate for real fills and the forward panels, "
              "never proof. Nothing in the system changes on this; the owner decides.",
}


# ---- freeze, run, smoke -------------------------------------------------------------------------------------------------

def sources() -> dict:
    return {p.relative_to(ROOT).as_posix(): Y.grid._sha(p) for p in
            [*sorted((ROOT / "python-engine").glob("*.py")), HERE / "lab_o.py", HERE / "analyze_o.py", HERE / "test_lab_o.py",
             FNO / "2026-10-30-risk-spectrum/lab_r.py", FNO / "2026-10-30-earning-power/lab_s2.py"]}


def freeze() -> None:
    Y.write_new(HERE / "freeze.json", {"schema": "o31b_final_book_v1", "books": json.loads(json.dumps(books())), "rule": RULE,
                                       "carried": CARRIED, "cost": L.COST, "sources": sources(), "qualification": "NOT_ASSESSED",
                                       "can_place_orders": False})
    print("frozen", len(books()), "books per year")


def carried_books(all_books: dict) -> dict:
    if YEAR == "2024":
        return {}
    out = {}
    earlier = json.loads((LOCAL / "keys-2024.json").read_text(encoding="utf-8"))
    middle = json.loads((LOCAL / "keys-2025.json").read_text(encoding="utf-8")) if YEAR == "2026" else None
    for n in CARRIED:
        out[f"{n}|carry"] = {**all_books[n], "carry": [earlier[n]] + ([middle[f"{n}|carry"]] if middle else [])}
    return out


def run(jobs: int) -> None:
    frozen = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    rel = (HERE / "freeze.json").relative_to(ROOT).as_posix()
    assert json.loads(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)) == frozen, "not committed"
    changed = [k for k, v in frozen["sources"].items() if Y.grid._sha(ROOT / k) != v]
    assert not changed, f"files changed since the freeze: {changed}"
    all_books = books()
    assert {n: Y.digest(b) for n, b in frozen["books"].items()} == {n: Y.digest(b) for n, b in all_books.items()}
    assert 1 <= jobs <= 7
    O27F.deny_network()
    C.table("year")
    all_books.update(carried_books(all_books))
    LOCAL.mkdir(exist_ok=True)
    with ProcessPoolExecutor(max_workers=jobs, initializer=L._init) as ex:
        runner = Y.Runner(ex, jobs)
        runner.run(list(all_books.values()), source="year", window=C.WINDOW)
    L._atomic(LOCAL / f"keys-{YEAR}.json", {n: Y.task_key(b, "year", C.WINDOW) for n, b in all_books.items()})
    print("DONE", YEAR, len(all_books), flush=True)


def smoke() -> None:
    """Variants of each kind over January of the chosen year: proves the plumbing, scores nothing."""
    O27F.deny_network()
    Y.speedups()
    Y.EVALS = LOCAL / "smoke"
    window = (f"{YEAR}-01-01", f"{YEAR}-01-31")
    C.table("year")
    Y._worker_init()
    all_books = books()
    for name in ("BASE", "LOTS|1", "ADX|30", "DAY|drive", "DAY|not_expiry_eve", "DAY|with_dmi", "DROP|TPB", "EXIT|RUN", "USTOP|0.75",
                 "LATEST|12:30", "DELTA|45", "ADD|fade_closed"):
        _key, trades = Y.evaluate((all_books[name], "year", window))
        print(f"smoke {YEAR} {name}: {len(trades)} trades, lots {sorted({t.get('lots_at_exit') for t in trades if t.get('lots_at_exit')})} "
              f"members {sorted({str(t.get('member')) for t in trades})[:5]} (plumbing only)", flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=["freeze", "run", "smoke"])
    cli.add_argument("--jobs", type=int, default=5)
    a = cli.parse_args()
    {"freeze": freeze, "run": lambda: run(a.jobs), "smoke": smoke}[a.action]()
