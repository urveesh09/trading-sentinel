"""O30c case study - research only. No runtime module imports this file.

Owner (Oct 30, after O30): "investigate. Why did it fail ... we can make different cases for different situation to
counter them ... we don't have to change our strategy. We can add more to it ... and test it again ... Will this make
it over training or over tuning. Think about it and improve it accordingly."

Over-tuning guard (declared here, before the investigation runs):
  * Tier 1 - the case list below is fixed now from standard trading logic, one textbook setting each, no grid. A case
    counts only if it beats its base in BOTH years (2025, 2026) and is not worse in at least 3 of the 4 half-years,
    with at least 40 trades a year. A useless rule can still pass that by luck now and then, so a passing case is a
    candidate for the unseen checks (SENSEX Jan - Aug 2026 once downloaded, the forward panel), not a go-live.
  * Tier 2 - anything the investigation (diagnose_c.py) suggests afterwards was found by looking at both years. It is
    reported as such and never scored on them as proof.

Tier 1 cases, on the four strategies (SHIPPED, OR20, EFF, TPB) with no gate (UNION) and with the live gate (UNION_ADX):
  * trend direction - take a signal only in the direction of the daily trend known before the session:
      dmi   Wilder's DMI(14): calls when yesterday's +DI > -DI, puts otherwise;
      ema   calls when yesterday's close > its 20-day EMA, puts otherwise;
      both  only when the two agree, in that direction (no trade when they disagree);
  * tpb_first - TPB (the one strategy positive on every window so far) gets priority when signals coincide;
  * tpb_all_days (UNION_ADX only) - on days the gate is closed, TPB alone still trades (also TPB first);
  * other day types instead of ADX >= 25 (UNION): ADX >= 20, 20-day realised vol above usual, the O29g trend regime;
  * two declared stacks: UNION_ADX + tpb_all_days + dmi, and UNION + dmi + tpb_first;
  * the 20 random-entry books with and without dmi (does the direction case lift random entries too?).
The year is chosen by O30C_YEAR (2025: the sealed O30 dataset; 2026: the O29f dataset), so workers see the same setup.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
O30 = ROOT / "docs/research/fno/2026-10-30-nifty-2025-test"
SIDE = ROOT / "docs/research/fno/2026-10-29-sideways-study"
LOCAL = HERE / "_local"
YEAR = os.environ.get("O30C_YEAR", "2026")
assert YEAR in ("2025", "2026"), YEAR

if YEAR == "2025":
    sys.path[:0] = [str(O30), str(SIDE)]
    import lab_t as T  # noqa: E402  (repoints the O29f / O29g machinery at the sealed 2025 data)
    Y, G = T.Y, T.G
    WINDOW = T.WINDOW
else:
    sys.path[:0] = [str(SIDE)]
    import lab_i  # noqa: E402  (O29i -> O29g -> O29f, on the O29f 2026 dataset)
    Y, G = lab_i.Y, lab_i.G
    WINDOW = Y.FULL
import pandas as pd  # noqa: E402

from fno_models import FnoDirection  # noqa: E402

F, O27F, ROUTER, replay = G.F, Y.O27F, Y.ROUTER, Y.replay
Y.EVALS = LOCAL / "evals"
HALVES = {"2025": (("2025-01-01", "2025-06-30"), ("2025-07-01", "2025-12-31")),
          "2026": (("2026-01-01", "2026-05-31"), ("2026-06-01", "2026-10-28"))}
WINDOWS = {"2025": ("2025-01-01", "2025-12-31"), "2026": ("2026-01-01", "2026-10-28")}
ADX = "adx_abs25:HIGH"
CASES = ("dmi", "ema", "both")


# ---- the trend direction known before the session -------------------------------------------------------------------

def dmi(daily: pd.DataFrame, n: int = 14) -> tuple[pd.Series, pd.Series]:
    """Wilder's +DI / -DI (the same smoothing as features.adx)."""
    high, low, close = daily["high"], daily["low"], daily["close"]
    up, down = high.diff(), -low.diff()
    plus = ((up > down) & (up > 0)) * up
    minus = ((down > up) & (down > 0)) * down
    tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / n, adjust=False).mean()
    return (100 * plus.ewm(alpha=1 / n, adjust=False).mean() / atr,
            100 * minus.ewm(alpha=1 / n, adjust=False).mean() / atr)


def direction_sides(daily: pd.DataFrame, days: list[str]) -> dict:
    """day -> {"dmi_dir", "ema_dir"} from daily bars strictly before the day (60 bars at least, as features.py)."""
    pdi, mdi = dmi(daily)
    ema = daily["close"].ewm(span=20, adjust=False).mean()
    out = {}
    for s in days:
        prior = daily.index[daily.index < pd.Timestamp(s)]
        if len(prior) < 60:
            continue
        y = prior[-1]
        out[s] = {"dmi_dir": "UP" if float(pdi.loc[y]) > float(mdi.loc[y]) else "DOWN",
                  "ema_dir": "UP" if float(daily["close"].loc[y]) > float(ema.loc[y]) else "DOWN"}
    return out


_base_table = Y.table
_CASE_TABLE: dict = {}


def table(source: str) -> dict:
    """The year's regime table plus the two direction sides."""
    if source not in _CASE_TABLE:
        rows = _base_table(source)
        for day, sides in direction_sides(F.daily_bars(), sorted(rows)).items():
            rows[day].setdefault("side", {}).update(sides)
        _CASE_TABLE[source] = rows
    return _CASE_TABLE[source]


Y.table = table


def wanted(case: str, row: dict | None):
    """The direction a case allows today: FnoDirection, or None for no trade."""
    side = (row or {}).get("side") or {}
    dirs = {"dmi": side.get("dmi_dir"), "ema": side.get("ema_dir")}
    if case == "both":
        d = dirs["dmi"] if dirs["dmi"] == dirs["ema"] else None
    else:
        d = dirs[case]
    return None if d is None else (FnoDirection.LONG if d == "UP" else FnoDirection.SHORT)


_route = Y.BookReplay.route


def route(self, frame, regime, now):
    """The O29f book's routing; with a case, a member's signal against the allowed direction is passed over (the next
    member may still fire in the allowed direction)."""
    case = self.book.get("case")
    if not case or self.warm:
        return _route(self, frame, regime, now)
    bar_ts = replay._last_closed_bar(frame, now)
    row = self.table.get(now.date().isoformat())
    allow = wanted(case, row)
    for i, m in enumerate(self.members):
        if not ROUTER.allowed(m["gate"], row):
            continue
        sig = self._signal(i, frame, regime, now, bar_ts)
        if sig.direction is None:
            continue
        if sig.direction != allow:
            self.notes["case_no_direction" if allow is None else "case_against_trend"] += 1
            continue
        self._fired = i
        return sig
    return G.MomSignal(bar_ts=bar_ts or "", reject_reason="book:no_member")


Y.BookReplay.route = route


# ---- books ----------------------------------------------------------------------------------------------------------

def four(gate_for) -> list[dict]:
    return [Y.named(c, gate_for(c)) for c in Y.NAMED]


def tpb_first(members: list[dict]) -> list[dict]:
    return [m for m in members if m["name"] == "TPB"] + [m for m in members if m["name"] != "TPB"]


def book(members: list[dict], case: str | None = None) -> dict:
    b = Y.book_of(members)
    return {**b, "case": case} if case else b


def books() -> dict:
    union, live = four(lambda c: "ALWAYS"), four(lambda c: ADX)
    tpb_days = four(lambda c: "ALWAYS" if c == "TPB" else ADX)
    out = {"BASE|UNION": book(union), "BASE|UNION_ADX": book(live)}
    for base, members in (("UNION", union), ("UNION_ADX", live)):
        for case in CASES:
            out[f"{base}|dir_{case}"] = book(members, case)
        out[f"{base}|tpb_first"] = book(tpb_first(members))
    out["UNION_ADX|tpb_all_days"] = book(tpb_days)
    out["UNION_ADX|tpb_all_days_first"] = book(tpb_first(tpb_days))
    for g in ("adx_abs20:HIGH", "rv20:HIGH", "trend_regime:HIGH"):
        out[f"UNION|gate_{g}"] = book(four(lambda c: g))
    out["STACK|UNION_ADX|tpb_all_days|dir_dmi"] = book(tpb_days, "dmi")
    out["STACK|UNION|tpb_first|dir_dmi"] = book(tpb_first(union), "dmi")
    for i, b in enumerate(Y.null_fixed()):
        out[f"NULL{i:02d}|ALWAYS"] = b
        out[f"NULL{i:02d}|dir_dmi"] = {**b, "case": "dmi"}
    return out


def base_of(name: str) -> str:
    return "BASE|UNION_ADX" if "UNION_ADX" in name else "BASE|UNION"


RULE = {
    "tier1": "a case helps if, per lot, it beats its base (UNION or UNION_ADX, see base_of) in 2025 AND in 2026, is not "
             "worse in at least 3 of the 4 half-years (2025 Jan-Jun / Jul-Dec, 2026 Jan-May / Jun-Oct) and makes at "
             "least 40 trades in each year; the day-type gates are also shown against UNION_ADX",
    "luck": "the dmi case on the 20 random-entry books: median change per year; a direction case that lifts random "
            "entries as much is a market-direction effect, reported as such",
    "status": "both years are seen (2026 in-sample, 2025 since O30); a passing case is a candidate for the unseen "
              "checks (SENSEX Jan - Aug 2026 once downloaded, the forward panel), never a go-live on this replay",
    "tier2": "patterns the investigation finds afterwards are reported as found-by-looking, not scored as proof",
    "no_change": "nothing in the system changes on this result; the owner decides",
}


# ---- freeze and run -------------------------------------------------------------------------------------------------

def year_bindings() -> dict:
    files = {p.relative_to(ROOT).as_posix(): Y.grid._sha(p)
             for p in (HERE / "lab_c.py", HERE / "analyze_c.py", HERE / "diagnose_c.py", HERE / "test_lab_c.py")}
    if YEAR == "2025":
        b = T.bindings()
    else:
        b = lab_i.bindings()
        o29i =json.loads((SIDE / "freeze.json").read_text(encoding="utf-8"))["bindings"]["sources"]
        changed = sorted(k for k, v in o29i.items() if b["sources"].get(k) != v)
        if changed:
            raise SystemExit(f"files changed since the O29i freeze: {changed}")
    return {**b, "sources": {**b["sources"], **files}}


def freeze() -> None:
    parts = {}
    for year in ("2025", "2026"):
        out = subprocess.check_output([sys.executable, str(HERE / "lab_c.py"), "bindings"], cwd=ROOT,
                                      env={**os.environ, "O30C_YEAR": year})
        parts[year] = json.loads(out.decode("utf-8").strip().splitlines()[-1])
    b = books()
    Y.write_new(HERE / "freeze.json", {"schema": "o30c_case_study_v1", "bindings": parts, "windows": WINDOWS,
                                       "halves": HALVES, "cases": CASES, "books": b, "rule": RULE,
                                       "qualification": "NOT_ASSESSED", "can_place_orders": False})
    print("frozen", len(b), "books x 2 years")


def _init() -> None:
    Y._worker_init()


def run(jobs: int) -> None:
    frozen = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    now = json.loads(json.dumps(year_bindings(), default=str))
    assert frozen["bindings"][YEAR] == now, "bound inputs changed since the freeze"
    rel = (HERE / "freeze.json").relative_to(ROOT).as_posix()
    assert json.loads(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)) == frozen, "freeze not committed"
    assert 1 <= jobs <= 10
    O27F.deny_network()
    Y.EVALS.mkdir(parents=True, exist_ok=True)
    rows = table("year")
    target = LOCAL / f"table-{YEAR}.json"
    if not target.is_file():
        Y.write_new(target, {d: {"side": r.get("side"), "features": r.get("features")} for d, r in rows.items()})
    all_books = books()
    with ProcessPoolExecutor(max_workers=jobs, initializer=_init) as ex:
        runner = Y.Runner(ex, jobs)
        runner.run(list(all_books.values()), source="year", window=WINDOW)
    Y.write_new(LOCAL / f"results-raw-{YEAR}.json", {
        "freeze_sha256": Y.grid._sha(HERE / "freeze.json"), "year": YEAR,
        "books": {n: Y.task_key(b, "year", WINDOW) for n, b in all_books.items()}, "trades": runner.trades})
    print("DONE", YEAR, len(runner.trades), "replays", flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=["bindings", "freeze", "run"])
    cli.add_argument("--jobs", type=int, default=4)
    args = cli.parse_args()
    if args.action == "bindings":
        print(json.dumps(year_bindings(), default=str))
    else:
        {"freeze": freeze, "run": lambda: run(args.jobs)}[args.action]()
