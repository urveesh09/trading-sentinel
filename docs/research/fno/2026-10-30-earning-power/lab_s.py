"""O30s earning power - research only. No runtime module imports this file.

Owner (Oct 30, after the O30q loss-day review): "so many people earn literally lakhs in single days and then despite
putting almost 2.5 lakhs in paper why can the system not even earn 2 lakhs in any single year? is it because of our
conservativeness? is there any way where we can ensure our current minimalistic loss strategy ... the 4 strategies
together had done really well in 2026 run though failed in 2025 ... search and make combinations and test it out ...
tell me how much tradeoff".

What is measured here and was never measured before: every F&O study so far compared strategies PER LOT. The question
now is the rupees on a Rs 2.5 lakh book, and what each extra rupee of profit costs in rupees of loss. Four layers:

  1. size: how many lots, by a fixed count or by a share of the money at risk, on the same trades;
  2. brakes: none, the shipped kill switches, or a throttle that cuts size in a drawdown without stopping;
  3. letting winners pay more: add a lot once the trade is working, with the stop moved so the total risk does not
     grow (ADD1: at +1R, stop to entry; ADD2: also at +2R, stop to +1R; HOUSE: the engine's own add at target), and
     holding longer (RUN, or HOLD: no time stop, 3-ATR trail, no lock);
  4. the three entries the O30q review named as the next research, one textbook setting each, no grid:
       RETEST    a close beyond the 09:15-09:45 range, a pull back to that level that holds, then a close beyond the
                 previous bar: continuation, stop just past the retest;
       FAILCONF  a close beyond the range, a close back inside, an attempt to regain the level that fails: reversal
                 toward the range's middle, stop just past the failed attempt;
       SQUEEZE   Bollinger inside Keltner (12 bars) for at least 6 bars, then a close beyond that quiet box: break
                 direction, stop at the far side of the box (0.5 to 1.5 ATR).

Every replay here is RAW: the shipped book (planner, contract choice, stops, costs, bid/ask fills) at ONE lot with the
kill switches off and a cap of 6 trades a day, so that one replay can be sized and braked many ways afterwards by
analyze_s.py. The simulator's shortcut (dropping a trade cannot release a later one the dropped trade had blocked) is
checked by exact replays of the shipped sizing and of the final pick (action "exact").

Declared before any of this is scored (freeze.json): the books, RAW, the sizing grid and RULE. NIFTY 2025 and Jan - Oct
2026 are both seen, so a pass is a candidate for the one-time 2024 check and forward data, never a go-live.

    O30C_YEAR=2025 python lab_s.py smoke
    python lab_s.py freeze                                      # commit and push freeze.json alone
    python ../run_slice.py --env O30C_YEAR=2025 -- <folder>/lab_s.py run --jobs 3      # repeat until DONE, then 2026
    python analyze_s.py
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
sys.path.insert(0, str(ROOT / "docs/research/fno/2026-10-30-case-study"))
import lab_c as C  # noqa: E402  (year setup via O30C_YEAR; regime table; case routing)

Y, G, O27F, replay = C.Y, C.G, C.O27F, C.replay
LOCAL = HERE / "_local"
Y.EVALS = LOCAL / "evals"

from config import settings  # noqa: E402

O27F.EXITS["HOLD"] = {"FNO_TIME_STOP_MIN": 400.0, "FNO_TRAIL_ATR_MULT": 3.0, "FNO_PROFIT_LOCK_ENABLED": False}
Y.KEEP = (*Y.KEEP, "stretch", "adds", "first_premium", "entry_underlying", "stop_underlying")

RAW = {"FNO_MAX_LOTS": 1, "FNO_MAX_LOTS_PROVEN": 1, "FNO_ADAPTIVE_RISK_ENABLED": False, "FNO_DAILY_KILL_PCT": 9.0,
       "FNO_WEEKLY_KILL_PCT": 9.0, "FNO_MONTHLY_KILL_PCT": 9.0, "FNO_MAX_DRAWDOWN_PCT": 0.999,
       "FNO_MAX_CONSECUTIVE_LOSSES": 1_000_000, "FNO_TWO_STRIKE_LOSSES": 1_000_000, "FNO_MAX_TRADES_PER_DAY": 6}
# (level in R at which a lot is added, where the stop moves to, in R from entry)
ADDS = {"ADD1": ((1.0, 0.0),), "ADD2": ((1.0, 0.0), (2.0, 1.0))}
ENTRY = {"last_entry_min": 870, "buffer_atr": 0.1, "max_wait": 12, "touch_atr": 0.25, "stop_pad_atr": 0.25,
         "min_stop_atr": 0.5}


def apply_raw() -> None:
    for k, v in RAW.items():
        setattr(settings, k, v)


# ---- 1. the three entries (causal: the answer for bar i reads only bars <= i) --------------------------------------

FAMILIES = ("RETEST", "FAILCONF", "SQUEEZE")
_TABLE: dict = {}


def _range30(t) -> tuple | None:
    first = t[t["minute"] < 585]
    if len(first) != 6 or int(first["minute"].iloc[0]) != 555:
        return None
    return float(first["high"].max()), float(first["low"].min())


def retest(m: dict, t, stamps) -> dict:
    box = _range30(t)
    if box is None:
        return {}
    c, h, l, atr, mins = (t["close"].values, t["high"].values, t["low"].values, t["atr"].values, t["minute"].values)
    out = {}
    for d, level in ((1, box[0]), (-1, box[1])):
        broke, held = None, None
        for i in range(6, len(t)):
            if not atr[i] > 0 or mins[i] + 5 > m["last_entry_min"]:
                continue
            if broke is None:
                if d * (c[i] - level) > m["buffer_atr"] * atr[i]:
                    broke = i
                continue
            if i - broke > m["max_wait"] or d * (c[i] - level) < 0:
                break                                   # expired, or closed back inside: no longer a retest
            if held is None:
                extreme = l[i] if d > 0 else h[i]
                if d * (extreme - level) <= m["touch_atr"] * atr[i]:
                    held = extreme
                continue
            held = min(held, l[i]) if d > 0 else max(held, h[i])
            if d * (c[i] - (h[i - 1] if d > 0 else l[i - 1])) > 0:
                dist = max(d * (c[i] - held) + m["stop_pad_atr"] * atr[i], m["min_stop_atr"] * atr[i])
                out[stamps[i]] = (d, float(c[i] - d * dist), None)
                break
    return out


def failconf(m: dict, t, stamps) -> dict:
    box = _range30(t)
    if box is None:
        return {}
    c, h, l, atr, mins = (t["close"].values, t["high"].values, t["low"].values, t["atr"].values, t["minute"].values)
    middle, out = (box[0] + box[1]) / 2, {}
    for d, level in ((1, box[0]), (-1, box[1])):
        broke, inside = None, None
        for i in range(6, len(t)):
            if not atr[i] > 0 or mins[i] + 5 > m["last_entry_min"]:
                continue
            if broke is None:
                if d * (c[i] - level) > m["buffer_atr"] * atr[i]:
                    broke = i
                continue
            if inside is None:
                if i - broke > m["max_wait"]:
                    break
                if d * (c[i] - level) < 0:
                    inside = i
                continue
            if i - inside > m["max_wait"] or d * (c[i] - level) > 0:
                break                                   # no attempt in time, or the level was regained: thesis gone
            extreme = h[i] if d > 0 else l[i]
            if d * (extreme - level) >= -m["touch_atr"] * atr[i]:
                dist = max(d * (extreme - c[i]) + m["stop_pad_atr"] * atr[i], m["min_stop_atr"] * atr[i])
                out[stamps[i]] = (-d, float(c[i] + d * dist), float(middle))
                break
    return out


def squeeze(m: dict, t, stamps) -> dict:
    c, h, l, atr, mins = (t["close"].values, t["high"].values, t["low"].values, t["atr"].values, t["minute"].values)
    n, out, run, done = 12, {}, 0, set()
    std = t["close"].rolling(n).std().values
    for i in range(n, len(t)):
        if not atr[i] > 0 or mins[i] + 5 > m["last_entry_min"]:
            continue
        if run >= 6:
            hi, lo = float(h[i - run:i].max()), float(l[i - run:i].min())
            for d, level in ((1, hi), (-1, lo)):
                if d not in done and d * (c[i] - level) > m["buffer_atr"] * atr[i]:
                    far = lo if d > 0 else hi
                    dist = min(max(d * (c[i] - far), m["min_stop_atr"] * atr[i]), 1.5 * atr[i])
                    out[stamps[i]] = (d, float(c[i] - d * dist), None)
                    done.add(d)
                    break
        run = run + 1 if 2.0 * std[i] < 1.5 * atr[i] else 0
    return out


RULES = {"RETEST": retest, "FAILCONF": failconf, "SQUEEZE": squeeze}


def entries(m: dict, f: dict) -> dict:
    """bar_ts -> (direction, stop_underlying, target_underlying or None) for one member on one session."""
    key = (m["family"], f["day"].isoformat(), f["stamps"][-1], len(f["stamps"]))
    if key not in _TABLE:
        _TABLE[key] = RULES[m["family"]](m, f["t"], f["stamps"])
        while len(_TABLE) > 6000:
            _TABLE.pop(next(iter(_TABLE)))
    return _TABLE[key]


def signal(m: dict, frame, regime: str, now):
    naive = now.replace(tzinfo=None)
    f = O27F.day_features(frame, naive.date())
    bar_ts = O27F.last_closed_bar(f, now) if f is not None else Y.replay._last_closed_bar(frame, now)
    if bar_ts is None or f is None or not f["complete_open"]:
        return G.MomSignal(bar_ts=bar_ts or "", reject_reason="o30s:no_features")
    hit = entries(m, f).get(bar_ts)
    if hit is None:
        return G.MomSignal(bar_ts=bar_ts, reject_reason="o30s:no_trigger")
    d, stop, target = hit
    sig = G._signal(frame, regime, now, m, d, bar_ts, f)
    if sig.direction is not None:
        risk = abs(sig.close - stop)
        sig.stop_underlying = stop
        sig.target_underlying = float(target if target is not None else sig.close + d * m["target_r"] * risk)
    return sig


_prev_signal = G.new_signal


def new_signal(m, frame, regime, now):
    return signal(m, frame, regime, now) if m["family"] in FAMILIES else _prev_signal(m, frame, regime, now)


G.new_signal = new_signal


def member(family: str, gate: str = "ALWAYS") -> dict:
    exit_ = "LIVE" if family == "FAILCONF" else "RUN"       # a reversal toward the middle is not held like a trend
    return G.new_member(family, gate, **{**ENTRY, "stop_atr": 1.0, "target_r": 2.0, "exit": exit_})


# ---- 2. the add-ons and the record of what happened at entry ---------------------------------------------------------

_prev_close = replay._close_record


def close_record(leg, at, price, reason, fut):
    record, final = _prev_close(leg, at, price, reason, fut)
    record["adds"] = getattr(leg, "o30s_adds", 0) + (1 if leg.pyramided else 0)
    record["first_premium"] = leg.fills[0]["entry_premium"] if leg.fills else leg.entry_premium
    record["stretch"] = getattr(leg, "o30s_stretch", None)
    return record, final


replay._close_record = close_record


def stretch_at(frame, now, direction: str):
    """The O30q entry-location clue: how far the last closed 5-minute close stands from VWAP, in the trade's direction,
    as a share of the first 30 minutes' range. Known at entry."""
    f = O27F.day_features(frame, now.replace(tzinfo=None).date())
    if f is None:
        return None
    bar_ts = O27F.last_closed_bar(f, now)
    box = _range30(f["t"])
    if bar_ts is None or box is None or box[0] <= box[1]:
        return None
    row = f["t"].loc[pd.Timestamp(bar_ts)]
    side = 1 if direction == "LONG" else -1
    return round(side * (float(row["close"]) - float(row["vwap"])) / (box[0] - box[1]), 4)


_prev_init, _prev_entry, _prev_manage, _prev_house = (Y.BookReplay.__init__, Y.BookReplay._entry, Y.BookReplay._manage,
                                                      Y.BookReplay._house_money_add)


def init(self, data, book, table, source, warm=False):
    _prev_init(self, data, book, table, source, warm)
    if book.get("pyr") == "HOUSE":
        self.policies = [dataclasses.replace(p, pyramid_house_money=True) for p in self.policies]


def entry(self, book, obs, frame, day, now):
    before = book.next_id
    _prev_entry(self, book, obs, frame, day, now)
    if book.next_id != before:
        leg = book.open[before]
        leg.o30s_r, leg.o30s_adds = abs(leg.entry_underlying - leg.stop_underlying), 0
        leg.o30s_stretch = stretch_at(frame, now, leg.direction)


def add_if_due(leg, fut: float, quote, plan: tuple, notes) -> bool:
    """Add one lot at the ask once the future has gone the planned R in the trade's favour, and move the stop."""
    k = getattr(leg, "o30s_adds", 0)
    risk = getattr(leg, "o30s_r", 0.0)
    if k >= len(plan) or not (fut and fut > 0) or not risk > 0 or quote is None or quote.ask <= 0 or quote.bid <= 0:
        return False
    side = 1 if leg.direction == "LONG" else -1
    level, stop_r = plan[k]
    if (fut - leg.entry_underlying) * side < level * risk:
        return False
    new_lots = leg.lots + 1
    leg.fills.append({"kind": "PYRAMID_ADD", "qty": leg.lot_size, "price": quote.ask, "entry_premium": leg.entry_premium,
                      "gross_pnl": 0.0, "net_pnl": 0.0})
    leg.entry_premium = (leg.entry_premium * leg.lots + quote.ask) / new_lots
    leg.lots, leg.o30s_adds = new_lots, k + 1
    leg.stop_underlying = leg.entry_underlying + side * stop_r * risk
    notes["o30s_added"] += 1
    return True


def manage(self, book, obs, now):
    _prev_manage(self, book, obs, now)
    plan = ADDS.get(self.book.get("pyr"))
    if plan:
        for leg in book.open.values():
            add_if_due(leg, obs.future.ltp, obs.options.get(leg.token), plan, self.notes)


def house(self, leg, quote, obs, now):
    before = settings.FNO_MAX_LOTS
    settings.FNO_MAX_LOTS = 2
    try:
        _prev_house(self, leg, quote, obs, now)
    finally:
        settings.FNO_MAX_LOTS = before


Y.BookReplay.__init__, Y.BookReplay._entry, Y.BookReplay._manage, Y.BookReplay._house_money_add = (init, entry, manage,
                                                                                                   house)


# ---- 3. the books ----------------------------------------------------------------------------------------------------

def _members(base: str, exit_: str = "OWN") -> list[dict]:
    if base == "TPB":
        return [Y.named("TPB", "ALWAYS", exit_)]
    gate = {"LIVE": lambda c: C.ADX, "BEST": lambda c: "ALWAYS" if c == "TPB" else C.ADX,
            "UNION": lambda c: "ALWAYS"}[base]
    return [Y.named(c, gate(c), exit_) for c in Y.NAMED]


def raw(members: list[dict], **extra) -> dict:
    return {"members": [Y.canonical_member(m) for m in members], "o30s": "raw1", **extra}


def books() -> dict:
    out = {}
    for base in ("LIVE", "BEST", "TPB", "UNION"):
        out[base] = raw(_members(base))
    out["DRIVE"] = raw(Y.FIXED["UNION_DRIVE"]["members"])
    for c in ("SHIPPED", "OR20", "EFF"):                     # with TPB: the four run side by side as separate sleeves
        out[c] = raw([Y.named(c)])
    for base, exits in (("LIVE", ("RUN", "HOLD")), ("BEST", ("RUN", "HOLD")), ("UNION", ("RUN", "HOLD")),
                        ("TPB", ("HOLD",))):
        for ex in exits:
            out[f"{base}|{ex}"] = raw(_members(base, ex))
    for base in ("LIVE", "BEST", "TPB", "UNION"):
        for pyr in ("ADD1", "ADD2", "HOUSE"):
            out[f"{base}|{pyr}"] = raw(_members(base), pyr=pyr)
    for base in ("BEST", "TPB"):
        out[f"{base}|HOLD|ADD2"] = raw(_members(base, "HOLD"), pyr="ADD2")
    for fam in FAMILIES:
        out[f"{fam}|alone"] = raw([member(fam)])
        out[f"BEST+{fam}"] = raw([*_members("BEST"), member(fam)])
    out["BEST+ALL3"] = raw([*_members("BEST"), *[member(f) for f in FAMILIES]])
    for i, b in enumerate(Y.null_fixed()):
        out[f"NULL{i:02d}"] = raw(b["members"])
    return out


RULE = {
    "question": "on Rs 2.5 lakh, how much more can the book earn, and what does each extra rupee cost in losses?",
    "sizing": "analyze_s.GRID on every non-random book, on the same RAW trades",
    "stress": "all verdicts after Rs 200 extra per lot per trade (the O30n stress; a pyramid pays it on every lot)",
    "pass": "at the stress: net > 0 in 2025 AND in 2026, no more than one of the four half-years negative, largest fall "
            "<= 25% of the running peak (the two years joined, from Rs 2.5 lakh), at least 40 trades a year, and net "
            "above the median of the 20 random-entry books under the same sizing and brakes, in both years",
    "pick": "among passes, the highest worse-year net; the pick is replayed exactly and frozen for the one-time 2024 "
            "check (the O30f list is not changed; this is a second, separate sheet)",
    "cross_year": "the combination chosen on one year alone (highest net with its fall <= 25%) is scored on the other, "
                  "both ways, against TPB and BEST held at the same lots; a method that fails this is reported as "
                  "selection luck whatever the pick's totals",
    "entries": "RETEST / FAILCONF / SQUEEZE count as an improvement only if, at one lot and the stress, they beat their "
               "reference (BEST for the added books, the random median for alone) in both years and in at least 3 of "
               "the 4 half-years",
    "status": "NIFTY 2025 and Jan - Oct 2026 are both seen. Nothing in the system changes on this result; the owner "
              "decides. The Nov 2 real-money test stays one lot.",
    "reference_outside_mandate": "reference_s.py prices option selling (forbidden by the owner's rule) as information "
                                 "only: it can never be a pick",
}


# ---- 4. freeze, run, exact, smoke ------------------------------------------------------------------------------------

def year_bindings() -> dict:
    out = C.year_bindings()
    for p in (HERE / "lab_s.py", HERE / "analyze_s.py", HERE / "reference_s.py", HERE / "test_lab_s.py"):
        out["sources"][p.relative_to(ROOT).as_posix()] = Y.grid._sha(p)
    return out


def freeze() -> None:
    parts = {}
    for year in ("2025", "2026"):
        out = subprocess.check_output([sys.executable, str(HERE / "lab_s.py"), "bindings"], cwd=ROOT,
                                      env={**os.environ, "O30C_YEAR": year})
        parts[year] = json.loads(out.decode("utf-8").strip().splitlines()[-1])
    import analyze_s
    Y.write_new(HERE / "freeze.json", {"schema": "o30s_earning_power_v1", "bindings": parts, "books": books(),
                                       "raw_settings": RAW, "adds": ADDS, "entry_settings": ENTRY,
                                       "hold_exit": O27F.EXITS["HOLD"], "grid": analyze_s.GRID, "rule": RULE,
                                       "qualification": "NOT_ASSESSED", "can_place_orders": False})
    print("frozen", len(books()), "books x 2 years")


def _init() -> None:
    apply_raw()
    C._init()


def run(jobs: int) -> None:
    frozen = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    assert frozen["bindings"][C.YEAR] == json.loads(json.dumps(year_bindings(), default=str)), "inputs changed"
    rel = (HERE / "freeze.json").relative_to(ROOT).as_posix()
    assert json.loads(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=ROOT)) == frozen, "not committed"
    assert 1 <= jobs <= 6
    O27F.deny_network()
    C.table("year")
    all_books = books()
    with ProcessPoolExecutor(max_workers=jobs, initializer=_init) as ex:
        runner = Y.Runner(ex, jobs)
        runner.run(list(all_books.values()), source="year", window=C.WINDOW)
    Y.write_new(LOCAL / f"results-raw-{C.YEAR}.json", {
        "freeze_sha256": Y.grid._sha(HERE / "freeze.json"), "year": C.YEAR,
        "books": {n: Y.task_key(b, "year", C.WINDOW) for n, b in all_books.items()}, "trades": runner.trades})
    print("DONE", C.YEAR, len(runner.trades), flush=True)


def _init_exact(values: dict) -> None:
    for k, v in values.items():
        setattr(settings, k, v)
    C._init()


def exact(name: str, values: dict, tag: str, jobs: int = 1) -> None:
    """One book replayed by the shipped code at real sizes (no simulator shortcut). `values` are the settings."""
    O27F.deny_network()
    C.table("year")
    Y.EVALS = LOCAL / "exact"
    b = {**books()[name], "o30s": tag}
    with ProcessPoolExecutor(max_workers=jobs, initializer=_init_exact, initargs=(values,)) as ex:
        key, trades = ex.submit(_evaluate_in, (b, str(Y.EVALS))).result()
    net = [float(t["net_pnl"]) for t in trades if t.get("net_pnl") is not None]
    print(f"EXACT {C.YEAR} {name} {tag}: {len(net)} trades, net {sum(net):.0f} ({key})", flush=True)


def _evaluate_in(task: tuple):
    book, evals = task
    Y.EVALS = Path(evals)
    return Y.evaluate((book, "year", C.WINDOW))


def smoke() -> None:
    """A book per mechanism over January of the chosen year: proves the plumbing, scores nothing."""
    O27F.deny_network()
    apply_raw()
    Y.speedups()
    Y.EVALS = LOCAL / "smoke"
    window = (f"{C.YEAR}-01-01", f"{C.YEAR}-01-31")
    all_books = books()
    C.table("year")
    Y._worker_init()
    for name in ("TPB", "TPB|ADD2", "TPB|HOUSE", "TPB|HOLD", "RETEST|alone", "FAILCONF|alone", "SQUEEZE|alone"):
        _key, trades = Y.evaluate((all_books[name], "year", window))
        lots = sorted({t.get("lots_at_exit") for t in trades})
        print(f"smoke {C.YEAR} {name}: {len(trades)} trades, lots at exit {lots} (plumbing only, not a result)", flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=["bindings", "freeze", "run", "smoke", "exact"])
    cli.add_argument("--jobs", type=int, default=3)
    cli.add_argument("--name")
    cli.add_argument("--settings", help="JSON settings for the exact replay")
    cli.add_argument("--tag")
    a = cli.parse_args()
    if a.action == "bindings":
        print(json.dumps(year_bindings(), default=str))
    elif a.action == "exact":
        exact(a.name, json.loads(a.settings), a.tag)
    else:
        {"freeze": freeze, "run": lambda: run(a.jobs), "smoke": smoke}[a.action]()
