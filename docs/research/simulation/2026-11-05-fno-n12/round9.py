"""One account, with the existing yearly NIFTY control and a dated BFO sleeve."""
from contextlib import contextmanager
import copy
from dataclasses import replace
from datetime import date
from functools import lru_cache
import json
import math
import os
import subprocess
import sys

import round1 as r
from round9_tape import HERE, LOCAL, DEST, digest
from anatomy import trades
from config import settings
import fno_book
from fno_costs import calc_fno_costs
from fno_engine_mom import MomSignal, evaluate_fno_mom

Y = r.Y
FEES = calc_fno_costs
SEGMENT = "NFO"
MEMBERS = {"N11_SHIPPED": 0, "N11_OR20": 1, "N11_EFF": 2, "N11_TPB": 3, "N11_TPB_LOW": 4}


def fee(entry, exit_, quantity, exchange=None):
    return FEES(entry, exit_, quantity, exchange=exchange or SEGMENT)


@contextmanager
def exchange_scope():
    """Route fees in this isolated replay process, including research wrappers."""
    modules = [module for module in tuple(sys.modules.values())
               if getattr(module, "calc_fno_costs", None) is FEES]
    for module in modules:
        module.calc_fno_costs = fee
    try:
        yield
    finally:
        for module in modules:
            module.calc_fno_costs = FEES


class SensexData(Y.yeardata.YearData):
    def __init__(self, stress):
        super().__init__(LOCAL, LOCAL / f"observations-{stress}")
        self.day = None
        self.spread_quantile = "p90" if stress else "p75"

    @lru_cache(maxsize=4096)
    def bid_ask(self, close):
        upper, row = next((upper, row) for upper, row in
                          sorted(self.manifest["spread"].items(), key=lambda pair: float(pair[0]))
                          if close < float(upper))
        spread = float(row[self.spread_quantile])
        if upper == "inf":
            spread = max(spread, .003 * close)
        tick = .05
        bid = max(tick, math.floor((close - spread / 2) / tick + 1e-9) * tick)
        ask = max(bid + tick, math.ceil((close + spread / 2) / tick - 1e-9) * tick)
        return round(bid, 2), round(ask, 2)

    def front_expiry(self, day):
        return date.fromisoformat(self.manifest["day_contracts"][day.isoformat()]["future"])

    def observations(self, day):
        self.day = day
        self._weekly = (date.fromisoformat(self.manifest["day_contracts"][day]["option"]),)
        return super().observations(day)

    def _observations(self, day):
        old = Y.yeardata.bid_ask
        Y.yeardata.bid_ask = self.bid_ask
        try:
            observations, excluded = super()._observations(day)
        finally:
            Y.yeardata.bid_ask = old
        fresh = []
        for obs in observations:
            available = {k: v for k, v in obs.options.items() if v.last_trade_time
                         and 0 <= (obs.at - v.last_trade_time).total_seconds() <= settings.FNO_MAX_QUOTE_AGE_SEC}
            fresh.append(replace(obs, options=available))
        return fresh, excluded


class SharedDays:
    def __init__(self, nifty, sensex, allow):
        self.nifty, self.sensex, self.allow = nifty, sensex, allow
        self.active = nifty
        self.volume_frame = None
        self.selected = []
        self.days = nifty.days

    def __getattr__(self, name):
        return getattr(self.nifty, name)

    def observations(self, day):
        self.active = self.sensex if day in self.allow else self.nifty
        if self.active is self.sensex:
            self.selected.append(day)
        return self.active.observations(day)

    def option_expiries(self):
        return self.active.option_expiries()

    def futures_frame(self, token, day):
        raw = self.active.futures_frame(token, day)
        if self.active is self.sensex:
            front = self.nifty.future_contract(self.nifty.front_expiry(day))
            self.volume_frame = self.nifty.futures_frame(front.token, day)
            return fno_book.with_participation(raw, self.volume_frame)
        return raw


class Replay(Y.BookReplay):
    def route(self, frame, regime, now):
        if not isinstance(self.data, SharedDays) or self.data.active is self.data.nifty:
            return super().route(frame, regime, now)
        day = now.date().isoformat()
        row = self.table.get(day) or {}
        adx = (row.get("side") or {}).get("adx_abs30")
        shipped = evaluate_fno_mom(frame, regime, now, rvol_bars=self.data.volume_frame)
        signal = fno_book.n11_signal(frame, regime, now, shipped=shipped, adx_side=adx, underlying="SENSEX")
        if signal.direction is None:
            return signal
        self.notes["bfo_signal_ticks"] += 1
        rules = r.f.L
        if rules.R.stand_aside(rules.vol_at(now, .9), rules.paper_before(now), 20):
            self.notes["bfo_stand_aside_ticks"] += 1
            return MomSignal(bar_ts=signal.bar_ts, reject_reason="n11:stand_aside")
        self._fired = MEMBERS[signal.strategy]
        self._n02_decision = {
            "selected_profile": self.book["n02_profile"], "selector_policy": "STATIC",
            "selection_asof": None, "signal_bar": signal.bar_ts, "selection_latest_label_exit": None,
            "origin": "N12_CALENDAR", "entry_expert": self.members[self._fired]["name"],
            "entry_gate": f"adx_abs30:{adx}",
        }
        settings.FNO_MAX_LOTS = min(settings.FNO_MAX_LOTS, 1)
        settings.FNO_MAX_LOTS_PROVEN = min(settings.FNO_MAX_LOTS_PROVEN, 1)
        return signal

    def _entry(self, book, obs, frame, day, now):
        global SEGMENT
        old = SEGMENT
        SEGMENT = "BFO" if obs.future.contract.name == "SENSEX" else "NFO"
        try:
            return super()._entry(book, obs, frame, day, now)
        finally:
            SEGMENT = old

    def _manage(self, book, obs, now):
        global SEGMENT
        old = SEGMENT
        SEGMENT = "BFO" if obs.future.contract.name == "SENSEX" else "NFO"
        try:
            return super()._manage(book, obs, now)
        finally:
            SEGMENT = old


def verify():
    path = HERE / "round9-freeze.json"
    frozen = json.loads(path.read_bytes())
    assert frozen == json.loads(subprocess.check_output(
        ["git", "show", f"HEAD:{path.relative_to(r.ROOT).as_posix()}"], cwd=r.ROOT))
    for file, sha in frozen["files"].items():
        assert digest(HERE / file) == sha, file
    data = json.loads((LOCAL / "manifest.json").read_bytes())
    assert digest(DEST) == data["data_sha256"]
    assert digest(LOCAL / "catalogue.json") == data["catalogue_sha256"]
    for day, item in json.loads((LOCAL / "catalogue.json").read_bytes()).items():
        for exchange, source in item["sources"].items():
            assert digest(LOCAL / f"exchange/{exchange}-{item['previous']}.raw") == source["sha256"], day
    r.verify_freeze()


def evaluate(book, data):
    fno_book._RETEST.clear()
    with Y.ROUTER.dispatch(), exchange_scope():
        engine = Replay(data, book, Y.table("year"), "year")
        result = engine.run(*r.WINDOW)
    for row in result["trades"]:
        row.setdefault("status", "CLOSED" if row.get("net_pnl") is not None else "UNRESOLVED")
    return result


def main():
    assert r.YEAR in ("2025", "2026")
    verify()
    stress = os.environ.get("N12_STRESS") == "1"
    tag = "stress" if stress else "base"
    r.f.Z.N.B.L._init()
    nifty = Y.dataset("year")
    sensex = SensexData(stress)
    source = sensex.manifest["coverage"]
    allow = {d for d, v in source.items() if d.startswith(r.YEAR)
             and v["status"] == "OBSERVED" and v["opening_complete"] and v["hard_flat_minute_present"]}
    calendar, _ = nifty.option_expiries()
    assert all(date.fromisoformat(d) in calendar for d in allow)
    controls = r.books()
    output = {}
    for name in ("N11", "N11T"):
        control = copy.deepcopy(controls[name])
        control["label"] += f"|R9|{tag}"
        if stress:
            control["cost"] = [400.0, 10.0]
        result = evaluate(control, nifty)
        if not stress:
            _, reference = trades(r.YEAR, name)
            assert r.money(result) == r.money(reference), name
        output[name] = result
        print(r.YEAR, tag, name, result["summary"], flush=True)
    candidate = copy.deepcopy(controls["N11T"])
    candidate["label"] = f"N12|CALENDAR|{tag}"
    if stress:
        candidate["cost"] = [400.0, 10.0]
    dual = SharedDays(nifty, sensex, allow)
    output["CALENDAR"] = evaluate(candidate, dual)
    for name, result in output.items():
        for row in result["trades"]:
            if not row["tradingsymbol"].startswith("SENSEX") or row["status"] != "CLOSED":
                continue
            assert row["entry_time"][:10] in allow
            assert row["entry_qty"] == 20 and not row.get("n10_children")
            assert abs(row["net_pnl"] - ((row["exit_premium"] - row["entry_premium"]) * 20
                                         - FEES(row["entry_premium"], row["exit_premium"], 20, "BFO")
                                         - row["extra_cost"])) < .02, row
    with (LOCAL / f"results-{r.YEAR}-{tag}.json").open("x", encoding="utf-8") as handle:
        json.dump(output, handle, default=str)
    summary = {name: r.metrics(result) for name, result in output.items()}
    summary["selected_days"] = sorted(dual.selected)
    summary["sensex_trades"] = [row for row in output["CALENDAR"]["trades"] if row["tradingsymbol"].startswith("SENSEX")]
    with (HERE / f"round9-{r.YEAR}-{tag}.json").open("x", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    print(r.YEAR, tag, "selected", len(dual.selected), "BFO", len(summary["sensex_trades"]),
          "shared net", summary["CALENDAR"]["net"], flush=True)


if __name__ == "__main__":
    main()
