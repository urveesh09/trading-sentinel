"""O29d SENSEX check - research only. No runtime module imports this file.

The owner (Oct 28 evening, after O29c): "why are you just sticking on nifty? ... You can apply it anywhere you want
okay so you just have to ensure that the strategy is flexible and smart that the losses are less and the profits are
consistent."

O29c made the paper book's NIFTY strategy the engine's UNION_DRIVE book (python-engine/fno_book.py). Every study
that chose its four strategies and its 09:45 opening-drive filter replayed NIFTY only, so SENSEX kept the shipped
break. This check runs the ENGINE's book, unchanged, on SENSEX: every archived SENSEX session Sep 10 - Oct 28 was
never used to choose anything in it, so this is the first test of the book on data it was not fitted to.

How (all through the shipped single-leg book, fno_policy_replay unchanged, as in O28/O29b):
  - SENSEX quote batches (front future + the archived SENSEX calls and puts) and SENSEX's own option-expiry calendar;
  - SENSEX front-future 5-minute bars for every price rule. SENSEX futures volume is too thin to measure
    participation (the shipped SENSEX signal reads NIFTY's: ``evaluate_fno_mom(rvol_bars=...)``), so wherever a
    strategy reads volume (RVOL, VWAP weights) it reads the NIFTY front future's volume of the same 5-minute bar;
  - the opening drive from SENSEX's own bars, its HIGH/LOW threshold from SENSEX's own previous 20 sessions;
  - each leg managed with its strategy's exits (fno_book.EXIT_OVERRIDES), BSE (BFO) charges.
Not replayed: the live pool shared with NIFTY, and the rule that refuses a SENSEX entry in the direction NIFTY
already holds. Each arm is its own SENSEX-only book.

The rule, declared before scoring (freeze.json): see RULE.
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import importlib.util
import json
import os
import pickle
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine/fno_policy_replay.py").is_file())
sys.path[:0] = [str(ROOT / "python-engine"), str(ROOT / "scripts")]


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


study = _load(ROOT / "docs/research/fno/2026-10-28-chop-study/study.py", "o29b_study")
router, replay, grid = study.router, study.replay, study.grid
import fno_book  # noqa: E402
import fno_costs  # noqa: E402
from fno_engine_mom import MomSignal, evaluate_fno_mom  # noqa: E402

DATA = study.DATA                       # the O29b copy of panel C's read-only export (sha-checked by its manifest)
LOCAL = HERE / "_local"
CACHE = LOCAL / "observations"
RESULTS = LOCAL / "results.json"
FULL = study.FULL
SENSEX_FUTURES = {216221445: "2026-09-24", 221330181: "2026-10-29"}  # token -> expiry, from the archived quotes
EXTREME_DAY = -5000.0
ARMS = {
    "SHIPPED": ("SHIPPED",),                       # today's SENSEX strategy
    "UNION_DRIVE": fno_book.STRATEGIES,            # the O29c book (breakouts only on a HIGH drive)
    "UNION": fno_book.STRATEGIES,                  # the four always on (context)
}
RULE = {
    "candidate": "UNION_DRIVE, the engine's fno_book exactly as committed in 01fa551 (no SENSEX-specific value)",
    "replace_shipped_on_sensex_only_if": [
        "its net over the SENSEX sessions Sep 10 - Oct 28 is above the shipped break's net on the same sessions",
        "its net without its best day is above 0",
        "its worst day is no worse than -Rs 5,000 (the panel C extreme-loss bound)",
    ],
    "otherwise": "SENSEX keeps the shipped break; nothing is tuned on these sessions in either case",
    "metrics": "trades by entry day; net after BFO charges; drawdown over closed trades in exit order (O29b metrics)",
}


def deny_network() -> None:
    study.deny_network()


def sensex_front(day: date) -> int | None:
    live = [t for t, expiry in SENSEX_FUTURES.items() if expiry >= day.isoformat()]
    return min(live, key=lambda t: SENSEX_FUTURES[t]) if live else None


class SensexData(grid.CachedReplayData):
    """The export read as SENSEX: its quote batches, its option calendar, its futures bars carrying NIFTY's volume."""

    def option_expiries(self):
        if self._expiries is None:
            self._expiries = tuple(sorted(date.fromisoformat(e) for e in self.manifest["option_expiries"]["SENSEX"])), \
                "export_manifest"
        return self._expiries

    def observations(self, day: str):
        path = self.cache / f"{day}.pkl"
        if path.is_file():
            return pickle.loads(path.read_bytes())
        parsed = self._parse(day)
        part = path.with_name(f"{day}.{os.getpid()}.part")
        part.write_bytes(pickle.dumps(parsed, protocol=pickle.HIGHEST_PROTOCOL))
        os.replace(part, path)
        return parsed

    def _parse(self, day: str):
        """ReplayData.observations with SENSEX in place of NIFTY (same verification, same exclusions)."""
        from fno_chain import _parse_quote_entry
        from fno_exit_experiment import verify_archive_event
        from fno_models import Contract
        from intraday_spread_archive_adapter import read_archived_quote_events
        batches: dict = defaultdict(list)
        for event in read_archived_quote_events(self.root, days=[day]):
            if (event.get("contract") or {}).get("underlying") == "SENSEX":
                batches[event["received_at_utc"]].append(event)
        excluded: Counter = Counter()
        out = []
        for received in sorted(batches):
            future, options = None, {}
            for event in batches[received]:
                spec = event["contract"]
                token = int(spec["instrument_token"])
                verified, reason = verify_archive_event(event, token=token, symbol=spec["tradingsymbol"],
                                                        max_age_seconds=replay.MAX_QUOTE_AGE_SECONDS)
                if verified is None:
                    excluded[reason] += 1
                    continue
                contract = Contract(token=token, tradingsymbol=spec["tradingsymbol"], name="SENSEX",
                                    expiry=date.fromisoformat(spec["expiry"]), strike=float(spec["strike"]),
                                    instrument_type=spec["instrument_type"], lot_size=int(spec["lot_size"]),
                                    tick_size=float(spec["tick_size"]))
                quote = _parse_quote_entry(contract, event["raw_packet"])
                if spec["instrument_type"] == "FUT":
                    future = quote
                else:
                    options[token] = quote
            if future is None or future.ltp <= 0:
                excluded["batch_without_future"] += 1
                continue
            at = datetime.fromisoformat(received.replace("Z", "+00:00")).astimezone(replay.IST)
            out.append(replay.Observation(at, future, options))
        return out, excluded

    def futures_frame(self, token: int, day: date):
        """The SENSEX contract's 21-day 5-minute window; its volume column is the NIFTY front future's volume of the
        same bar (0 where NIFTY has no bar), as the shipped SENSEX signal reads participation."""
        frame = super().futures_frame(token, day)
        nifty = super().futures_frame(router.front_token(day), day)
        nifty = nifty[~nifty.index.duplicated(keep="last")]
        frame["volume"] = nifty["volume"].reindex(frame.index).fillna(0.0).values
        return frame


def drive_table(data: SensexData) -> dict:
    """date -> SENSEX opening drive (front contract, read at 09:46), for every session in the SENSEX bars."""
    import sqlite3
    con = sqlite3.connect(f"file:{(DATA / 'fno-replay.sqlite').resolve().as_posix()}?mode=ro", uri=True)
    try:
        stamps = [r[0] for r in con.execute(
            "SELECT DISTINCT substr(datetime,1,10) FROM fut_candles WHERE interval='5minute' AND instrument_token IN "
            f"({','.join(str(t) for t in SENSEX_FUTURES)}) ORDER BY 1")]
    finally:
        con.close()
    out = {}
    for stamp in stamps:
        day = date.fromisoformat(stamp)
        token = sensex_front(day)
        if token is None:
            continue
        frame = replay.ReplayData.futures_frame(data, token, day)
        value = fno_book.opening_drive(frame, day, datetime.combine(day, datetime.min.time()).replace(hour=9, minute=46))
        if value is not None:
            out[stamp] = value
    return out


class SensexBook(router.RouterReplay):
    """The engine's book (fno_book.book_signal over the given strategies) on SENSEX, through the shipped book."""

    def __init__(self, data, arm: str, drives: dict):
        super().__init__(data, {"sensex": arm}, {}, {})
        self.arm, self.drives = arm, drives
        self.strategies = ARMS[arm]

    def route(self, frame, regime, now) -> MomSignal:
        day = now.date()
        shipped = evaluate_fno_mom(frame, regime, now)
        if self.arm == "SHIPPED":
            self._fired = "SHIPPED" if shipped.direction is not None else None
            return shipped
        if self.arm == "UNION":
            side = "HIGH"
        else:
            value = fno_book.opening_drive(frame, day, now)
            history = [v for d, v in sorted(self.drives.items()) if d < day.isoformat()]
            side = fno_book.drive_side(value, history)
        sig = fno_book.book_signal(frame, regime, now, shipped=shipped, side=side)
        self._fired = sig.strategy or None
        return sig

    def _manage(self, book, obs, now):
        base, full = self.policy, book.open
        try:
            for leg_id in sorted(full):
                leg, comp = full[leg_id], self.leg_component[leg_id]
                before = len(book.trades)
                book.open = {leg_id: leg}
                self.policy = replay.ReplayPolicy(name=f"BOOK_{comp}", manage_every_observation=True,
                                                  exit_overrides=tuple(sorted(fno_book.EXIT_OVERRIDES[comp].items())))
                replay.SingleLegReplay._manage(self, book, obs, now)
                for trade in book.trades[before:]:
                    trade["component"], trade["entry_qty"] = comp, leg.initial_qty
                if leg_id not in book.open:
                    del full[leg_id]
        finally:
            book.open, self.policy = full, base


def _bfo_costs() -> None:
    """Charge every replayed SENSEX fill at the BSE rate (the replay's cost calls name no exchange)."""
    if not getattr(fno_costs.calc_fno_costs, "o29d_bfo", False):
        bfo = functools.partial(fno_costs.calc_fno_costs, exchange=fno_costs.options_exchange_for("SENSEX"))
        bfo.o29d_bfo = True
        fno_costs.calc_fno_costs = bfo


def _warm(day: str) -> str:
    deny_network()
    SensexData(DATA, CACHE).observations(day)
    return day


def _arm(arm: str) -> tuple[str, dict]:
    deny_network()
    _bfo_costs()
    data = SensexData(DATA, CACHE)
    drives = json.loads((LOCAL / "drives.json").read_text(encoding="utf-8"))
    with router.dispatch():
        result = SensexBook(data, arm, drives).run(*FULL)
    keep = {k: result[k] for k in ("trades", "funnel", "notes", "archive_exclusions")}
    return arm, keep


def freeze_record() -> dict:
    files = (Path(__file__), ROOT / "python-engine/fno_book.py", ROOT / "python-engine/fno_policy_replay.py",
             ROOT / "python-engine/fno_engine_mom.py", ROOT / "python-engine/fno_shadow.py",
             ROOT / "python-engine/fno_entry_plan.py", ROOT / "python-engine/fno_exit_rules.py")
    return {"study": "O29d SENSEX check", "rule": RULE, "arms": {k: list(v) for k, v in ARMS.items()},
            "window": FULL, "sensex_futures": SENSEX_FUTURES, "extreme_day": EXTREME_DAY,
            "sources_sha256": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in files},
            "seen": "no SENSEX session was used to choose the book's strategies, exits or filter"}


def verdict(metrics: dict) -> dict:
    u, s = metrics["UNION_DRIVE"], metrics["SHIPPED"]
    checks = {"beats_shipped": u["net"] > s["net"], "positive_without_best_day": u["net_ex_best"] > 0,
              "worst_day_within_bound": u["worst_day"] >= EXTREME_DAY}
    return {"checks": checks, "replace_shipped_on_sensex": all(checks.values())}


def run(jobs: int) -> dict:
    frozen = json.loads((HERE / "freeze.json").read_text(encoding="utf-8"))
    assert frozen["sources_sha256"] == freeze_record()["sources_sha256"], "code changed since the freeze"
    deny_network()
    CACHE.mkdir(parents=True, exist_ok=True)
    days = study.sessions()
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        list(ex.map(_warm, [d for d in days if not (CACHE / f"{d}.pkl").exists()]))
    drives = drive_table(SensexData(DATA, CACHE))
    (LOCAL / "drives.json").write_text(json.dumps(drives, indent=1), encoding="utf-8")
    with ProcessPoolExecutor(max_workers=jobs) as ex:
        results = dict(ex.map(_arm, list(ARMS)))
    metrics = {}
    for arm, result in results.items():
        trades = [{k: t.get(k) for k in (*study.KEEP, "entry_qty")} for t in result["trades"]]
        for t in trades:
            t["status"] = "CLOSED" if t.get("net_pnl") is not None else "UNRESOLVED"
        result["trades"] = trades
        metrics[arm] = study.metrics(trades, days)
    sides = {}
    ordered = sorted(drives)
    for i, d in enumerate(ordered):
        sides[d] = fno_book.drive_side(drives[d], [drives[x] for x in ordered[:i]])
    out = {"freeze_sha256": hashlib.sha256((HERE / "freeze.json").read_bytes()).hexdigest(), "sessions": days,
           "metrics": metrics, "verdict": verdict(metrics), "drives": drives, "sides": sides, "results": results}
    RESULTS.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=("freeze", "run"))
    p.add_argument("--jobs", type=int, default=6)
    a = p.parse_args()
    if a.command == "freeze":
        target = HERE / "freeze.json"
        if target.exists():
            raise SystemExit("freeze.json exists")
        target.write_text(json.dumps(freeze_record(), indent=1), encoding="utf-8", newline="\n")
    else:
        out = run(a.jobs)
        print(json.dumps({"metrics": {k: {m: v for m, v in x.items() if m != "by_day"}
                                      for k, x in out["metrics"].items()}, "verdict": out["verdict"]}, indent=1))


if __name__ == "__main__":
    main()
