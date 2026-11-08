"""N012 round five. Early structure invalidation and protected continuation."""
from __future__ import annotations

import copy
from dataclasses import replace
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess

import pandas as pd

import round1 as r
from config import settings
from fno_costs import calc_fno_costs
from fno_n11 import extra_cost

HERE = Path(__file__).resolve().parent
MANAGE = r.Y.BookReplay._manage
NATIVE = r.EXIT_NATIVE


def books():
    base = r.books()["N11T"]
    return {
        mode: {**copy.deepcopy(base), "label": f"N12|{mode}", "n12": mode}
        for mode in ("INVALIDATED", "RUNNER")
    }


def fresh_bid(position, observation, now):
    quote = observation.options.get(position.token)
    if quote is None or quote.bid <= 0 or quote.last_trade_time is None:
        return 0.0
    if not 0 <= (now - quote.last_trade_time).total_seconds() <= settings.FNO_MAX_QUOTE_AGE_SEC:
        return 0.0
    if quote.bid_quantity < position.qty:
        return 0.0
    return quote.bid


def manage(self, book, obs, now):
    mode = self.book.get("n12")
    frame = getattr(self, "_frame", None)
    if mode not in ("INVALIDATED", "RUNNER") or not book.open or frame is None:
        return MANAGE(self, book, obs, now)
    bar = r.Y.replay._last_closed_bar(frame, now)
    if not bar:
        return MANAGE(self, book, obs, now)
    stamp = pd.Timestamp(bar)
    recent = frame.loc[stamp - pd.Timedelta(minutes=10):stamp]
    if len(recent) != 3:
        return MANAGE(self, book, obs, now)

    def decide(position, *, fut_price, exit_px_basis, **kwargs):
        native = NATIVE(position, fut_price=fut_price, exit_px_basis=exit_px_basis, **kwargs)
        if fut_price is None or fut_price <= 0:
            return native
        bid = fresh_bid(position, obs, now)
        risk = abs(position.entry_underlying - position.stop_underlying)
        if bid <= 0 or risk <= 0:
            return native
        side = 1 if position.direction == "LONG" else -1
        if mode == "INVALIDATED":
            if native.exit_reason or native.trail_active or bid >= position.entry_premium:
                return native
            entry = datetime.fromisoformat(position.entry_time)
            age = (now - entry).total_seconds() / 60
            if not 10 <= age <= 35 or native.best_underlying is None:
                return native
            if side * (native.best_underlying - position.entry_underlying) >= .5 * risk:
                return native
            signal = pd.Timestamp(position.bar_ts)
            if signal not in frame.index or signal >= recent.index[-2]:
                return native
            trigger = frame.loc[signal]
            edge = float(trigger.low if side == 1 else trigger.high) - side * .10 * risk
            if not 0 < side * (edge - position.stop_underlying) < risk:
                return native
            if all(side * (px - edge) < 0 for px in (*recent.close.iloc[-2:], fut_price)):
                self.notes["n12_structure_invalidation"] += 1
                return replace(native, exit_reason="n12_structure_invalidation", persist_trail=False)
        elif native.exit_reason == "trail_stop" and now.hour * 60 + now.minute < 885:
            # Native trail takes priority over premium reasons. Check those explicitly.
            if bid <= position.premium_stop or (
                native.profit_lock_floor is not None and bid <= native.profit_lock_floor
            ):
                return native
            gain = (bid - position.entry_premium) * position.qty
            cost = calc_fno_costs(position.entry_premium, bid, position.qty) + extra_cost(position.lots)
            progress = side * (fut_price - position.entry_underlying)
            if gain < 2 * cost or progress <= .75 * risk:
                return native
            prior, first, second = recent.close.to_list()
            advancing = side * (first - prior) > 0 and side * (second - first) > 0
            first_bar, second_bar = recent.iloc[-2], recent.iloc[-1]
            overlap = min(first_bar.high, second_bar.high) >= max(first_bar.low, second_bar.low)
            edge = min(first_bar.low, second_bar.low) if side == 1 else max(first_bar.high, second_bar.high)
            floor = float(edge) - side * .15 * (position.atr_at_entry or 0.0)
            if advancing and overlap and side * (fut_price - floor) > 0:
                self.notes["n12_protected_runner_tick"] += 1
                return replace(native, exit_reason="", persist_trail=True)
        return native

    r.exits.evaluate_single_leg_exit = decide
    try:
        return MANAGE(self, book, obs, now)
    finally:
        r.exits.evaluate_single_leg_exit = NATIVE


r.Y.BookReplay._manage = manage


def main():
    spec = HERE / "round5-freeze.json"
    rel = spec.relative_to(r.ROOT).as_posix()
    cfg = json.loads(spec.read_bytes())
    assert cfg == json.loads(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=r.ROOT))
    assert all(hashlib.sha256((HERE / name).read_bytes()).hexdigest() == sha for name, sha in cfg["files"].items())
    r.verify_freeze()
    variants = books()
    r.f.Z.N.run_books(variants, 2)
    out = {k: r.metrics(r.raw_for(b)) for k, b in variants.items()}
    for k, v in out.items():
        print(r.YEAR, k, v["net"], v["closed"], v["worst_day"], v["drawdown_pct"],
              {key: n for key, n in v["notes"].items() if key.startswith("n12")}, flush=True)
    with (HERE / f"round5-{r.YEAR}.json").open("x", encoding="utf-8") as file:
        json.dump(out, file, indent=2, sort_keys=True)
        file.write("\n")


if __name__ == "__main__":
    main()
