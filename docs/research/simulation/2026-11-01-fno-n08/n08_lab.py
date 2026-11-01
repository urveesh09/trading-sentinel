"""N08: the study of N03-N07's weaknesses, on the unchanged replay stack. Research only; no application module imports this file.

N08_YEAR chooses the year. 2024-26 are development years, already seen. 2023 stays closed until N08 is frozen: repoint_2023 is only
reached through the sealed exam in exam_2023.py. Patches sit at module level because Windows workers re-import the main script.

    <venv python> n08_lab.py parity --jobs 5     with N08_YEAR=2024, 2025, 2026
    <venv python> n08_lab.py screen --jobs 5     with N08_YEAR=2024, 2025, 2026
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from datetime import datetime
from functools import lru_cache
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine").is_dir())
PARENT = HERE.parent / "2026-11-01-fno-failure-anatomy"
sys.path[:0] = [str(HERE), str(PARENT)]

YEAR = os.environ.get("N08_YEAR", "2026")
assert YEAR in ("2023", "2024", "2025", "2026", "TEST2025"), YEAR
for name in ("O30F_YEAR", "O30C_YEAR"):
    os.environ.pop(name, None)
if YEAR in ("2023", "2024", "TEST2025"):
    os.environ["O30F_YEAR"] = "2024"     # the 2024 route is the one built to repoint the stack at another sealed dataset
else:
    os.environ["O30C_YEAR"] = YEAR
import anatomy_lab as A  # noqa: E402
import n08_rules as R  # noqa: E402
from config import settings  # noqa: E402

Y, B, C, X, P = A.Y, A.B, A.C, A.X, A.P
F = C.F
LOCAL = HERE / "_local"
A.LOCAL = LOCAL
X.LOCAL = LOCAL
P.LOCAL = LOCAL
P.P.LOCAL = LOCAL
P.P.E.LOCAL = LOCAL
Y.EVALS = LOCAL / "evals"
TIME_STOP_DEFAULT = float(settings.FNO_TIME_STOP_MIN)
NATIVE_CLOCK = {"SHIPPED": TIME_STOP_DEFAULT, "OR20": 75.0, "EFF": 60.0, "TPB": 120.0}
FNO_STUDIES = ROOT / "docs/research/fno"
POINTS = {
    "2023": {"year": "2023", "dataset": LOCAL / "dataset-nifty-2023", "mirror": LOCAL / "mirror-2023.sqlite", "window": ("2023-01-01", "2023-12-31"),
             "cache": LOCAL / "observations-2023", "local": LOCAL / "y2023"},
    # The wiring test: the same repointing, aimed at sealed 2025 data whose results are already known.
    "TEST2025": {"year": "2025", "dataset": FNO_STUDIES / "2026-10-30-nifty-2025-test/_local/dataset-nifty-2025",
                 "mirror": FNO_STUDIES / "2026-10-30-nifty-2025-test/_local/mirror.sqlite", "window": ("2025-01-01", "2025-12-31"),
                 "cache": LOCAL / "repoint-test/observations", "local": LOCAL / "repoint-test"},
}

if YEAR in POINTS:
    point = POINTS[YEAR]
    Y.YEAR = point["dataset"]
    Y.CACHES["year"] = point["cache"]
    Y.LOCAL = point["local"]
    Y.EVALS = LOCAL / "evals"
    F.DOWNLOAD = point["mirror"]
    F.DATASET = point["dataset"]
    C.WINDOW = point["window"]
    B.YEAR = point["year"]

    def _base_table(source: str) -> dict:
        assert source == "year", source
        if source not in X.G._TABLE:
            manifest = json.loads((point["dataset"] / "manifest.json").read_text(encoding="utf-8"))
            X.G._TABLE[source] = X.G.regime_rows(manifest["sessions"], Y.condition_table("year"), manifest["weekly_expiry_calendar"])
        return X.G._TABLE[source]

    C._base_table = _base_table
    C._CASE_TABLE.clear()
    X.G._TABLE.clear()


@lru_cache(None)
def di_sides() -> dict:
    """day -> True when yesterday's daily +DI was above -DI, from daily bars strictly before the day."""
    import sides_w as W
    daily = F.daily_bars()
    daily = daily[~daily.index.duplicated(keep="last")].sort_index()
    pdi, mdi, _adx, _atr = W._dmi(daily)
    out = {}
    for stamp in daily.index:
        prior = daily.index[daily.index < stamp]
        if len(prior) >= 60:
            y = prior[-1]
            out[stamp.date().isoformat()] = bool(float(pdi.loc[y]) > float(mdi.loc[y]))
    return out


# ---- exits ----------------------------------------------------------------------------------------------------------

_review = A.review
_ACTIVE: dict = {}


def review(leg, obs, now, frame, mode):
    minute, ctx = _review(leg, obs, now, frame, mode)
    if _ACTIVE.get("eff_cut") == "NO_PROGRESS" and minute != 30.0:
        if R.no_progress_cut(ctx.get("parent_stall_eligible"), ctx.get("bid"), leg.entry_premium, ctx.get("progress_r")):
            return 30.0, {**ctx, "action": "NO_PROGRESS_STALL"}
    return minute, ctx


A.review = review


def _member_params(policy, overrides: dict):
    return replace(policy, exit_overrides=tuple(sorted({**dict(policy.exit_overrides), **overrides}.items())))


_manage = Y.BookReplay._manage


def manage(self, book, obs, now):
    cfg = self.book.get("n08")
    if not cfg:
        return _manage(self, book, obs, now)
    full, policies = book.open, self.policies
    _ACTIVE["eff_cut"] = cfg.get("eff_cut")
    try:
        for ident in sorted(full):
            leg = full[ident]
            i = self.leg_member[ident]
            name = self.members[i]["name"]
            params = dict(cfg.get("exits", {}).get(name, {}))
            quote = obs.options.get(leg.token)
            bid = quote.bid if quote and quote.bid > 0 else None
            if name in cfg.get("stall_half", ()) and bid is not None:
                native = float(params.get("FNO_TIME_STOP_MIN", NATIVE_CLOCK[name]))
                age = (now - datetime.fromisoformat(leg.entry_time)).total_seconds() / 60
                risk = abs(leg.entry_underlying - leg.stop_underlying)
                progress = (1 if leg.direction == "LONG" else -1) * (obs.future.ltp - leg.entry_underlying) / risk if risk > 0 else 0.0
                minute = R.half_clock_stall(age, native, bool(leg.trail_active), bid, leg.entry_premium, progress)
                if minute != native:
                    params["FNO_TIME_STOP_MIN"] = minute
            book.open = {ident: leg}
            self.policies = list(policies)
            if params:
                self.policies[i] = _member_params(policies[i], params)
            if name in cfg.get("pyramid", ()):
                self.policies[i] = replace(self.policies[i], pyramid_house_money=True)
            _manage(self, book, obs, now)
            if ident not in book.open:
                del full[ident]
    finally:
        book.open, self.policies = full, policies
        _ACTIVE.clear()


Y.BookReplay._manage = manage

_house_money = Y.replay.SingleLegReplay._house_money_add


def house_money(self, leg, quote, obs, now):
    """The shipped add, with the premium cap every other entry obeys."""
    cap = float(settings.FNO_MAX_OPEN_PREMIUM_PCT) * self._n08_equity
    if leg.entry_premium * leg.qty + quote.ask * leg.lot_size > cap:
        self.notes["pyramid_skipped_premium_cap"] += 1
        return
    _house_money(self, leg, quote, obs, now)


Y.replay.SingleLegReplay._house_money_add = house_money

_on_target = Y.replay.SingleLegReplay._on_target


def on_target(self, book, leg, obs, now):
    self._n08_equity = book.equity
    return _on_target(self, book, leg, obs, now)


Y.replay.SingleLegReplay._on_target = on_target


# ---- entries --------------------------------------------------------------------------------------------------------

_route = Y.BookReplay.route


def route(self, frame, regime, now):
    """N02's static route with N08's options for the extra low-day TPB. Same first-firing rule, same stretch rule."""
    cfg = self.book.get("n08") or {}
    mode = cfg.get("low_direction", "PUTS")
    if mode == "PUTS" and not any(k in cfg for k in ("low_last_minute", "low_two_lots_before", "order")):
        return _route(self, frame, regime, now)
    bar = Y.replay._last_closed_bar(frame, now)
    day = now.date().isoformat()
    minute = now.hour * 60 + now.minute
    profile = self.book["n02_profile"]
    row = self.table.get(day)
    for i in cfg.get("order", X.INDEX[profile]):
        m = self.members[i]
        if not Y.ROUTER.allowed(m["gate"], row):
            continue
        sig = self._signal(i, frame, regime, now, bar)
        if sig.direction is None:
            continue
        stretch = X.S.stretch_at(frame, now, sig.direction.value)
        if stretch is not None and stretch >= 0.5:
            return X.G.MomSignal(bar_ts=sig.bar_ts, reject_reason="n02:stretched")
        if i == 4 and not R.low_day_direction_allowed(mode, sig.direction.value, di_sides().get(day)):
            return X.G.MomSignal(bar_ts=sig.bar_ts, reject_reason="n08:low_direction")
        if i == 4 and not R.low_day_time_allowed(minute, cfg.get("low_last_minute")):
            return X.G.MomSignal(bar_ts=sig.bar_ts, reject_reason="n08:low_too_late")
        self._fired = i
        self._n02_decision = {"selected_profile": profile, "selector_policy": "STATIC", "selection_asof": None, "signal_bar": sig.bar_ts,
                              "selection_latest_label_exit": None, "origin": "TPB_LOW" if i == 4 else "MAIN", "entry_expert": m["name"], "entry_gate": m["gate"]}
        if i == 4 and profile == "TPB_ONE":
            lots = R.low_day_lots(minute, cfg.get("low_two_lots_before"))
            settings.FNO_MAX_LOTS = min(settings.FNO_MAX_LOTS, lots)
            settings.FNO_MAX_LOTS_PROVEN = min(settings.FNO_MAX_LOTS_PROVEN, lots)
        return sig
    return X.G.MomSignal(bar_ts=bar or "", reject_reason="n02:no_member")


Y.BookReplay.route = route

_entry = Y.BookReplay._entry


def entry(self, book, obs, frame, day, now):
    """N08's later or earlier trail arming: the same stop, the target scaled from the 1.8R every strategy uses."""
    before = book.next_id
    _entry(self, book, obs, frame, day, now)
    arm = (self.book.get("n08") or {}).get("trail_arm_r")
    if arm and book.next_id != before:
        leg = book.open[before]
        leg.target_underlying = leg.entry_underlying + (leg.target_underlying - leg.entry_underlying) * arm / 1.8


Y.BookReplay._entry = entry


# ---- books ----------------------------------------------------------------------------------------------------------

def references() -> dict:
    return {name: book for name, book in A.books().items() if name.startswith("NORMAL|") and name.split("|")[1] in ("BASE", "STALL30", "STRUCT30", "PREMIUM_STALL")}


def variant(label: str, **cfg) -> dict:
    book = copy.deepcopy(references()["NORMAL|PREMIUM_STALL"])
    book["n08"] = {"contract": "v1", **cfg}
    book["label"] = "N08|" + label
    return book


def lock(arm: float, keep: float, floor: float = 0.10) -> dict:
    return {"FNO_PROFIT_LOCK_ENABLED": True, "FNO_PROFIT_LOCK_ARM_R": arm, "FNO_PROFIT_LOCK_FLOOR_R": floor, "FNO_PROFIT_LOCK_KEEP_FRACTION": keep}


def screen_books() -> dict:
    """One change at a time against N07. Every number is a round value, and each family has a stated reason."""
    out = {}
    for arm in (0.8, 1.2, 1.6, 2.4):
        for keep in (0.0, 0.5):
            out[f"LOCK_TPB|{arm}|{keep}"] = variant(f"LOCK_TPB|{arm}|{keep}", exits={"TPB": lock(arm, keep)})
            out[f"LOCK_EFF|{arm}|{keep}"] = variant(f"LOCK_EFF|{arm}|{keep}", exits={"EFF": lock(arm, keep)})
    for arm in (0.8, 1.2, 1.6):
        out[f"LOCK_BOTH|{arm}|0.0"] = variant(f"LOCK_BOTH|{arm}|0.0", exits={"TPB": lock(arm, 0.0), "EFF": lock(arm, 0.0)})
    for names in (("TPB",), ("OR20",), ("SHIPPED",), ("TPB", "OR20", "SHIPPED")):
        tag = "+".join(names)
        out[f"STALL_HALF|{tag}"] = variant(f"STALL_HALF|{tag}", stall_half=list(names))
    out["EFF_CUT|NO_PROGRESS"] = variant("EFF_CUT|NO_PROGRESS", eff_cut="NO_PROGRESS")
    for mult in (1.0, 1.5, 3.0):
        out[f"TRAIL_TPB|{mult}"] = variant(f"TRAIL_TPB|{mult}", exits={"TPB": {"FNO_TRAIL_ATR_MULT": mult}})
    for mult in (1.0, 2.0):
        out[f"TRAIL_EFF_OR20|{mult}"] = variant(f"TRAIL_EFF_OR20|{mult}", exits={"EFF": {"FNO_TRAIL_ATR_MULT": mult}, "OR20": {"FNO_TRAIL_ATR_MULT": mult}})
    for names in (("TPB",), ("TPB", "EFF", "OR20", "SHIPPED")):
        tag = "+".join(names)
        out[f"PYRAMID|{tag}"] = variant(f"PYRAMID|{tag}", pyramid=list(names))
    for mode in ("PUTS_UNLESS_UP", "WITH_TREND"):
        out[f"LOW_DIRECTION|{mode}"] = variant(f"LOW_DIRECTION|{mode}", low_direction=mode)
    return out


WIDE = {"EFF": {"FNO_TRAIL_ATR_MULT": 2.0}, "OR20": {"FNO_TRAIL_ATR_MULT": 2.0}}
EVERY_TRAIL_2 = {**WIDE, "SHIPPED": {"FNO_TRAIL_ATR_MULT": 2.0}}
MINUTE = {"12:00": 720, "13:00": 780, "13:30": 810, "14:00": 840}


def screen2_books() -> dict:
    """Second round, from what the first found: where profit really comes from, and the hour pattern in the low-day trades."""
    out = {"TRAIL_ALL|2.0": variant("TRAIL_ALL|2.0", exits=EVERY_TRAIL_2)}
    for name, value in (("14:00", 840), ("13:30", 810), ("13:00", 780)):
        out[f"LOW_LAST|{name}"] = variant(f"LOW_LAST|{name}", low_last_minute=value)
    for name, value in (("12:00", 720), ("13:00", 780)):
        out[f"LOW_TWO_BEFORE|{name}"] = variant(f"LOW_TWO_BEFORE|{name}", low_two_lots_before=value)
    for arm in (1.2, 2.4, 3.0):
        out[f"TRAIL_ARM|{arm}"] = variant(f"TRAIL_ARM|{arm}", trail_arm_r=arm)
    for flat, label in ((900, "15:00"), (915, "15:15"), (920, "15:20"), (925, "15:25")):
        book = variant(f"FLAT|{label}", flat=flat)
        book["cfg"] = {**book.get("cfg", {}), "FNO_HARD_FLAT_MIN": flat}
        out[f"FLAT|{label}"] = book
    out["TPB_FIRST"] = variant("TPB_FIRST", order=[3, 0, 1, 2, 4])
    out["NO_LOW_TPB"] = variant("NO_LOW_TPB", order=[0, 1, 2, 3])
    return out


def combo(label: str, wide: bool = False, early_two: bool = False, late_stop: bool = False, cap2: bool = False, **extra) -> dict:
    cfg = dict(extra)
    if wide:
        cfg["exits"] = WIDE
    if early_two:
        cfg["low_two_lots_before"] = MINUTE["12:00"]
    if late_stop:
        cfg["low_last_minute"] = MINUTE["14:00"]
    book = variant(label, **cfg)
    if cap2:
        book["cfg"] = {**book.get("cfg", {}), "FNO_MAX_LOTS": 2, "FNO_MAX_LOTS_PROVEN": 2}
    return book


def screen3_books() -> dict:
    """Third round: is the wider trail on a plateau or a spike, what does each part add, and do they work together?"""
    out = {}
    for mult in (2.5, 3.0):
        out[f"TRAIL_EFF_OR20|{mult}"] = variant(f"TRAIL_EFF_OR20|{mult}", exits={"EFF": {"FNO_TRAIL_ATR_MULT": mult}, "OR20": {"FNO_TRAIL_ATR_MULT": mult}})
    out["TRAIL_EFF|2.0"] = variant("TRAIL_EFF|2.0", exits={"EFF": {"FNO_TRAIL_ATR_MULT": 2.0}})
    out["TRAIL_OR20|2.0"] = variant("TRAIL_OR20|2.0", exits={"OR20": {"FNO_TRAIL_ATR_MULT": 2.0}})
    parts = {"W": "wide", "E": "early_two", "L": "late_stop", "C": "cap2"}
    for tag in ("C", "WE", "WL", "WC", "EL", "EC", "LC", "WEL", "WEC", "WLC", "ELC", "WELC"):
        out[f"COMBO|{tag}"] = combo(f"COMBO|{tag}", **{parts[c]: True for c in tag})
    return out


def n08_cfg(trail: float = 2.0, two_before: int = 720, last: int = 840) -> dict:
    return {"exits": {"EFF": {"FNO_TRAIL_ATR_MULT": trail}, "OR20": {"FNO_TRAIL_ATR_MULT": trail}}, "low_two_lots_before": two_before, "low_last_minute": last}


def welc(label: str, base: str = "NORMAL|PREMIUM_STALL", cost=None, cap2: bool = True, **cfg_args) -> dict:
    parents = A.books()
    book = copy.deepcopy(parents[base])
    book["n08"] = {"contract": "v1", **n08_cfg(**cfg_args)}
    book["label"] = "N08|" + label
    if cap2:
        book["cfg"] = {**book.get("cfg", {}), "FNO_MAX_LOTS": 2, "FNO_MAX_LOTS_PROVEN": 2}
    if cost is not None:
        book["cost"] = cost
    return book


def screen4_books() -> dict:
    """Fourth round: stress the candidate. Nearby settings, other bases, one lot and other costs. It chooses nothing by itself."""
    out = {"WELC": welc("WELC")}
    for value, name in ((705, "11:45"), (735, "12:15"), (750, "12:30")):
        out[f"NEAR|two_before={name}"] = welc(f"NEAR|two_before={name}", two_before=value)
    for value, name in ((810, "13:30"), (870, "14:30")):
        out[f"NEAR|last={name}"] = welc(f"NEAR|last={name}", last=value)
    for mult in (1.75, 2.5):
        out[f"NEAR|trail={mult}"] = welc(f"NEAR|trail={mult}", trail=mult)
    out["BASE|N04"] = welc("BASE|N04", base="NORMAL|STALL30")
    out["BASE|N05"] = welc("BASE|N05", base="NORMAL|STRUCT30")
    out["BASE|N03"] = welc("BASE|N03", base="NORMAL|BASE")
    out["COST|none"] = welc("COST|none", cost=[0.0, 0.0])
    out["COST|double"] = welc("COST|double", cost=[400.0, 10.0])
    n07 = copy.deepcopy(references()["NORMAL|PREMIUM_STALL"])
    for name, cost in (("none", [0.0, 0.0]), ("double", [400.0, 10.0])):
        b = copy.deepcopy(n07)
        b.update(cost=cost, label=f"N08|N07_COST|{name}")
        out[f"N07_COST|{name}"] = b
    one = {"exits": WIDE, "low_last_minute": MINUTE["14:00"]}
    b = copy.deepcopy(A.books()["ONE|PREMIUM_STALL"])
    b["label"] = "N08|ONE|N07"
    out["ONE|N07"] = b
    b = copy.deepcopy(A.books()["ONE|PREMIUM_STALL"])
    b["n08"] = {"contract": "v1", **one}
    b["label"] = "N08|ONE|WL"
    out["ONE|WL"] = b
    return out


def n08_book() -> dict:
    """N08: N07 + EFF and OR20 trail at 2 ATR + low-day TPB at up to two lots before 12:00 and none from 14:00 + nothing above two lots."""
    return welc("N08")


def noop_book() -> dict:
    """Every N08 code path active, with nothing changed: it must equal N07 trade for trade."""
    return variant("NOOP", order=list(X.INDEX["TPB_ONE"]))


def exam_books() -> dict:
    """Everything that sees 2023. The six O31e exam books are unchanged from freeze-2023.json. The parts are only there to explain the result."""
    exam = json.loads((FNO_STUDIES / "2026-10-31-weak-spots/freeze-2023.json").read_text(encoding="utf-8"))["books"]
    refs = references()
    out = {"N03": refs["NORMAL|BASE"], "N04": refs["NORMAL|STALL30"], "N05": refs["NORMAL|STRUCT30"], "N07": refs["NORMAL|PREMIUM_STALL"], "N08": n08_book()}
    screen = {**screen_books(), **screen2_books(), **screen3_books()}
    four = screen4_books()
    out.update({"PART|WIDE_TRAIL": screen["TRAIL_EFF_OR20|2.0"], "PART|EARLY_TWO": screen["LOW_TWO_BEFORE|12:00"], "PART|LATE_STOP": screen["LOW_LAST|14:00"],
                "PART|CAP2": screen["COMBO|C"], "PART|NO_LOW_TPB": screen["NO_LOW_TPB"], "ONE|N07": four["ONE|N07"], "ONE|WL": four["ONE|WL"]})
    out.update({f"EXAM|{k}": v for k, v in exam.items()})
    return out


def run_books(books: dict, jobs: int) -> None:
    assert 1 <= jobs <= 6
    B.O27F.deny_network()
    C.table("year")
    with ProcessPoolExecutor(max_workers=jobs, initializer=B.L._init) as pool:
        Y.Runner(pool, jobs).run(list(books.values()), source="year", window=C.WINDOW)


def parity() -> dict:
    """N03, N04, N05 and N07 must come back trade for trade from this stack before anything here means anything."""
    year = B.YEAR
    stored = {**json.loads((A.HERE / "_local" / f"keys-reference-{year}.json").read_text()), **json.loads((A.HERE / "_local" / f"keys-candidate-{year}.json").read_text())}
    out = {}
    for name, book in references().items():
        key = Y.task_key(book, "year", C.WINDOW)
        assert stored[name] == key, (name, stored[name], key)
        old = json.loads((A.HERE / "_local" / "evals" / f"{key}.json").read_text())["trades"]
        new = json.loads((LOCAL / "evals" / f"{key}.json").read_text())["trades"]
        assert old == new, (name, "trades differ")
        out[name] = {"trades": len(new), "net": round(sum(t["net_pnl"] for t in new), 2), "identical": True}
    n07 = json.loads((LOCAL / "evals" / f"{Y.task_key(references()['NORMAL|PREMIUM_STALL'], 'year', C.WINDOW)}.json").read_text())["trades"]
    noop = json.loads((LOCAL / "evals" / f"{Y.task_key(noop_book(), 'year', C.WINDOW)}.json").read_text())["trades"]
    strip = lambda t: {k: v for k, v in t.items() if k != "admission_id"}
    assert [strip(t) for t in n07] == [strip(t) for t in noop], "the N08 code paths changed N07 with nothing switched on"
    out["NOOP"] = {"trades": len(noop), "identical_to_n07": True}
    return out


def main() -> None:
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=("parity", "screen", "screen2", "screen3", "screen4"))
    cli.add_argument("--jobs", type=int, default=5)
    a = cli.parse_args()
    assert YEAR != "2023", "2023 is reached only through the sealed exam"
    if a.action == "parity":
        run_books({**references(), "NOOP": noop_book()}, a.jobs)
        result = parity()
        X.write(HERE / f"parity-{YEAR}.json", result)
        print("DONE parity", YEAR, result, flush=True)
    else:
        books = {"screen": screen_books, "screen2": screen2_books, "screen3": screen3_books, "screen4": screen4_books}[a.action]()
        run_books(books, a.jobs)
        X.write(LOCAL / f"keys-{a.action}-{YEAR}.json", {n: Y.task_key(b, "year", C.WINDOW) for n, b in books.items()})
        print("DONE", a.action, YEAR, len(books), flush=True)


if __name__ == "__main__":
    main()
