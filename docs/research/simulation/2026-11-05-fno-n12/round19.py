"""Test two separate ways to use the frozen prior-only India VIX forecasts."""
import copy
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import subprocess

from anatomy import trades
import round1 as r
import round16 as straddle
from config import settings
from fno_chain import RISK_FREE_RATE, years_to_expiry
from options_math import black76_price, implied_vol

HERE = Path(__file__).resolve().parent
Y = r.Y
MANAGE = Y.BookReplay._manage
TRAIL = "VOL_TRAIL"
PAIR = "VOL_PRICE_PAIR"


@lru_cache(maxsize=1)
def forecasts():
    return json.loads((HERE / "round18-forecasts.json").read_bytes())


def trail_scale(row):
    return min(1.20, max(.80, math.exp((row[1] - row[0]) / 2))) if row else 1.


def manage(self, book, obs, now):
    if self.book.get("n12_vol") != TRAIL or not book.open:
        return MANAGE(self, book, obs, now)
    factor = trail_scale(forecasts().get(now.date().isoformat()))
    if factor == 1.:
        return MANAGE(self, book, obs, now)
    previous = r.exits.evaluate_single_leg_exit

    def adjusted(position, *, params, **kwargs):
        return previous(position, params={**params, "FNO_TRAIL_ATR_MULT": params["FNO_TRAIL_ATR_MULT"] * factor},
                        **kwargs)

    r.exits.evaluate_single_leg_exit = adjusted
    try:
        if getattr(self, "last_vol_trail_date", None) != now.date():
            self.last_vol_trail_date = now.date()
            self.notes["vol_trail_wider_day" if factor > 1. else "vol_trail_tighter_day"] += 1
        return MANAGE(self, book, obs, now)
    finally:
        r.exits.evaluate_single_leg_exit = previous


def price_test(quotes, asks, future, now, forecast):
    cutoff = now.replace(hour=14, minute=45, second=0, microsecond=0)
    fraction = (cutoff - now).total_seconds() / (310. * 60.)
    if not 0 < fraction <= 1. or future <= 0.:
        return None
    projected_move = future * math.sqrt(math.exp(forecast) / 252. * fraction)
    if not 0 < projected_move < future:
        return None
    call, put = quotes
    expiry, strike = call.contract.expiry, call.contract.strike
    at_entry, at_exit = years_to_expiry(expiry, now), years_to_expiry(expiry, cutoff)
    forward = strike + (call.mid - put.mid) * math.exp(RISK_FREE_RATE * at_entry)
    if forward <= projected_move:
        return None
    by_side = [{}, {}]
    for quote in quotes:
        c = quote.contract
        is_call = c.instrument_type == "CE"
        vol = implied_vol(quote.mid, forward, c.strike, at_entry, RISK_FREE_RATE, is_call)
        if vol is None:
            return None
        vol = max(.01, vol - .01)
        half_spread = (quote.ask - quote.bid) / 2.
        for target, direction in zip(by_side, (-1, 1)):
            mid = black76_price(forward + direction * projected_move, c.strike, at_exit, vol, RISK_FREE_RATE, is_call)
            target[c.token] = max(0., mid - half_spread)
    return projected_move, [straddle.amounts(asks, bids)[-1] for bids in by_side]


class VolPairReplay(straddle.StraddleReplay):
    def _entry(self, book, obs, frame, day, now):
        if self.ticket or self.incomplete:
            return
        Y.BookReplay._entry(self, book, obs, frame, day, now)
        if self.tried == day or not 600 <= now.hour * 60 + now.minute <= 603:
            return
        self.tried = day
        if book.open or book.entries_today[now.date()] or self._halts(book, now):
            return
        if self._stance(book, now).single_leg_halted_today:
            return
        expiry = next((e for e in self.data.option_expiries()[0] if e >= now.date()), None)
        if expiry is None or not 1 <= (expiry - now.date()).days <= 2:
            return
        bar = Y.replay._last_closed_bar(frame, now)
        if bar is None or self.data.regime(bar, day)[0] == "REGIME_3_CRISIS":
            return
        estimate = forecasts().get(day)
        if estimate is None:
            self.notes["vol_pair_missing_forecast"] += 1
            return
        self.notes["vol_pair_clock"] += 1
        future = obs.future.ltp
        atm = 50 * math.floor(future / 50 + .5)
        found = {q.contract.instrument_type: q for q in obs.options.values()
                 if q.contract.expiry == expiry and q.contract.strike == atm and q.contract.lot_size == straddle.LOT}
        if not {"CE", "PE"} <= found.keys():
            self.notes["vol_pair_missing_chain"] += 1
            return
        pair = (found["CE"], found["PE"])
        asks = {q.contract.token: self.mark(obs, q.contract.token, now, buying=True) for q in pair}
        if any(mark is None for mark in asks.values()):
            self.notes["vol_pair_missing_chain"] += 1
            return
        if straddle.reserve(asks.values()) > min(9000., settings.FNO_MAX_OPEN_PREMIUM_PCT * book.equity):
            self.notes["vol_pair_cash_refused"] += 1
            return
        economics = price_test(pair, asks, future, now, estimate[1])
        if economics is None or min(economics[1]) < 350.:
            self.notes["vol_pair_economics_refused"] += 1
            return
        move, scenarios = economics
        ordered = tuple(sorted(asks, key=lambda token: (asks[token], token)))
        self.ticket = straddle.Ticket(day, expiry.isoformat(), ordered, sum(asks.values()), now)
        self.pair_setup = {"at": now.isoformat(), "future": future, "move": move, "scenario_nets": scenarios,
                           "max_pair_ask": sum(asks.values())}
        self.notes["vol_pair_approved"] += 1

    def _buy(self, ticket, book, obs, now):
        setup = self.pair_setup
        if abs(obs.future.ltp - setup["future"]) <= .25 * setup["move"]:
            return super()._buy(ticket, book, obs, now)
        self.notes["vol_pair_moved"] += 1
        if ticket.buys:
            ticket.stage, ticket.reason = "CLOSE", "straddle_abandoned"
        else:
            self.ticket = None

    def _settle(self, ticket, book, now, bids):
        super()._settle(ticket, book, now, bids)
        book.trades[-1].update(tradingsymbol="NIFTY_VOL_PRICE_PAIR", vol_pair_setup=self.pair_setup)


def books():
    base = r.books()["N11T"]
    return {name: {**copy.deepcopy(base), "label": f"N12|{name}", "n12_vol": name} for name in (TRAIL, PAIR)}


Y.BookReplay._manage = manage


def verify():
    spec = HERE / "round19-freeze.json"
    cfg = json.loads(spec.read_bytes())
    assert cfg == json.loads(subprocess.check_output(
        ["git", "show", f"HEAD:{spec.relative_to(r.ROOT).as_posix()}"], cwd=r.ROOT))
    for name, sha in cfg["source"].items():
        assert hashlib.sha256((HERE / name).read_text(encoding="utf-8").encode()).hexdigest() == sha, name
    assert cfg["books"] == json.loads(json.dumps(books()))
    r.verify_freeze()
    dataset = r.DATASETS[r.YEAR]
    manifest = json.loads((dataset / "manifest.json").read_bytes())
    with (dataset / "breeze.sqlite").open("rb") as handle:
        assert hashlib.file_digest(handle, "sha256").hexdigest() == manifest["files_sha256"]["breeze.sqlite"]


def main():
    verify()
    controls = {name: r.raw_for(r.books()[name]) for name in ("N11", "N11T")}
    for name, raw in controls.items():
        assert r.money(raw) == r.money(trades(r.YEAR, name)[1]), name
    r.f.Z.N.B.O27F.deny_network()
    r.f.Z.N.B.L._init()
    models = books()
    results = {}
    for name, klass in ((TRAIL, Y.BookReplay), (PAIR, VolPairReplay)):
        with Y.ROUTER.dispatch():
            engine = klass(Y.dataset("year"), models[name], Y.table("year"), "year")
            results[name] = engine.run(*r.WINDOW)
        for row in results[name]["trades"]:
            row.setdefault("status", "CLOSED" if row.get("net_pnl") is not None else "UNRESOLVED")
    out = {name: r.metrics(value) for name, value in {**controls, **results}.items()}
    out["pairs"] = [t for t in results[PAIR]["trades"]
                    if t["tradingsymbol"] in ("NIFTY_VOL_PRICE_PAIR", "NIFTY_COMPRESSION_STRADDLE")]
    out["economic_tuples"] = {name: r.money(value) for name, value in results.items()}
    with (HERE / f"round19-{r.YEAR}.json").open("x", encoding="utf-8") as handle:
        json.dump(out, handle, indent=2, sort_keys=True, default=str)
        handle.write("\n")
    for name in (TRAIL, PAIR):
        row = out[name]
        print(r.YEAR, name, row["net"], row["worst_day"], row["unresolved"],
              {k: v for k, v in row["notes"].items() if k.startswith(("vol_", "straddle_"))}, flush=True)


if __name__ == "__main__":
    main()
