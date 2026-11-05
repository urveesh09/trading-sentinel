"""Staged long straddle in a single N11T research account."""
import copy
from contextlib import closing
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import subprocess

import pandas as pd

from anatomy import trades
import round1 as r
from round12 import usable
from config import settings
from fno_adaptive_risk import Close
from fno_costs import calc_fno_costs

HERE = Path(__file__).resolve().parent
Y = r.Y
NAME = "COMPRESSION_STRADDLE"
LOT = 65


@dataclass
class Ticket:
    day: str
    expiry: str
    tokens: tuple[int, int]
    max_pair_ask: float
    last_action: datetime
    stage: str = "FIRST"
    buys: dict = field(default_factory=dict)
    bought_at: dict = field(default_factory=dict)
    reason: str = ""


def width_after_compression(frame, day, now):
    first = pd.Timestamp(f"{day} 09:15")
    expected = pd.date_range(first, periods=21, freq="5min")
    if expected[-1] + pd.Timedelta(minutes=5) > pd.Timestamp(now.replace(tzinfo=None)):
        return None
    if not expected.isin(frame.index).all():
        return None
    opening, later = frame.loc[expected[:12]], frame.loc[expected[12:]]
    low, high = float(opening.low.min()), float(opening.high.max())
    width = high - low
    if not math.isfinite(width) or width <= 0:
        return None
    if float(later.high.max() - later.low.min()) > .5 * width:
        return None
    if not low + .25 * width <= float(later.close.iloc[-1]) <= high - .25 * width:
        return None
    return width


def reserve(asks):
    return sum(ask * LOT + calc_fno_costs(ask, ask, LOT) for ask in asks) + 400.


def amounts(asks, bids):
    gross = sum((bids[token] - ask) * LOT for token, ask in asks.items())
    fees = sum(calc_fno_costs(ask, bids[token], LOT) for token, ask in asks.items())
    stress = 200. * len(asks)
    return gross, fees, stress, gross - fees - stress


class StraddleReplay(Y.BookReplay):
    ticket = None
    tried = None
    incomplete = False

    def mark(self, obs, token, now, *, buying=False):
        quote = obs.options.get(token)
        if quote is None or quote.last_trade_time != now or quote.bid_quantity < LOT or quote.bid <= 0:
            return None
        if buying and not usable(quote, now):
            return None
        contract = quote.contract
        row = self.raw.execute(
            "SELECT close, volume FROM candles WHERE kind='option' AND expiry=? AND strike=? AND opt=? AND datetime=?",
            (contract.expiry.isoformat(), contract.strike, contract.instrument_type, now.strftime("%Y-%m-%d %H:%M:00")),
        ).fetchone()
        if row is None or (row[1] or 0) <= 0 or float(row[0]) != quote.ltp:
            return None
        return quote.ask if buying else quote.bid

    def _entry(self, book, obs, frame, day, now):
        if self.ticket or self.incomplete:
            return
        super()._entry(book, obs, frame, day, now)
        if self.tried == day or not 660 <= now.hour * 60 + now.minute <= 663:
            return
        self.tried = day
        if book.open or book.entries_today[now.date()] or self._halts(book, now):
            return
        if self._stance(book, now).single_leg_halted_today:
            return
        expiry = next((e for e in self.data.option_expiries()[0] if e >= now.date()), None)
        if expiry is None or not 1 <= (expiry - now.date()).days <= 2:
            return
        width = width_after_compression(frame, day, now)
        if width is None:
            return
        regime, _ = self.data.regime(Y.replay._last_closed_bar(frame, now), day)
        if regime == "REGIME_3_CRISIS":
            return
        self.notes["straddle_compression"] += 1
        atm = 50 * math.floor(obs.future.ltp / 50 + .5)
        pair = {q.contract.instrument_type: q.contract.token for q in obs.options.values()
                if q.contract.expiry == expiry and q.contract.strike == atm and q.contract.lot_size == LOT}
        if not {"CE", "PE"} <= pair.keys():
            self.notes["straddle_chain_missing"] += 1
            return
        tokens = (pair["CE"], pair["PE"])
        asks = {token: self.mark(obs, token, now, buying=True) for token in tokens}
        if any(ask is None for ask in asks.values()):
            self.notes["straddle_chain_missing"] += 1
            return
        if sum(asks.values()) > width or reserve(asks.values()) > min(9000., settings.FNO_MAX_OPEN_PREMIUM_PCT * book.equity):
            self.notes["straddle_price_refused"] += 1
            return
        ordered = tuple(sorted(tokens, key=lambda token: (asks[token], token)))
        self.ticket = Ticket(day, expiry.isoformat(), ordered, width, now)

    def _buy(self, ticket, book, obs, now):
        exactly_next = (now - ticket.last_action).total_seconds() == 60.
        token = ticket.tokens[0] if ticket.stage == "FIRST" else ticket.tokens[1]
        cost = self.mark(obs, token, now, buying=True) if exactly_next else None
        if ticket.stage == "FIRST" and cost is not None:
            other = self.mark(obs, ticket.tokens[1], now, buying=True)
        else:
            other = next(iter(ticket.buys.values()), None)
        fit = cost is not None and other is not None and cost + other <= ticket.max_pair_ask and (
            reserve((cost, other)) <= min(9000., settings.FNO_MAX_OPEN_PREMIUM_PCT * book.equity))
        if not fit:
            if ticket.buys:
                ticket.stage, ticket.reason = "CLOSE", "straddle_abandoned"
            else:
                self.ticket = None
                self.notes["straddle_first_cancelled"] += 1
            return
        ticket.buys[token], ticket.bought_at[token], ticket.last_action = cost, now.isoformat(), now
        if ticket.stage == "FIRST":
            ticket.stage = "SECOND"
            book.entries_today[now.date()] += 1
        else:
            ticket.stage = "HOLD"
            self.notes["straddle_pair_opened"] += 1

    def _settle(self, ticket, book, now, bids):
        gross, fees, stress, net = amounts(ticket.buys, bids)
        book.equity += net
        book.closes.append((now, net, "DEFINED_RISK"))
        book.completed.append(Close(now, net, False))
        book.trades.append({
            "tradingsymbol": "NIFTY_COMPRESSION_STRADDLE", "entry_time": min(ticket.bought_at.values()),
            "exit_time": now.isoformat(), "exit_reason": ticket.reason, "status": "CLOSED",
            "gross_pnl": gross, "fees": fees, "extra_cost": stress, "net_pnl": net,
            "expiry": ticket.expiry, "buys": ticket.buys, "buy_clocks": ticket.bought_at, "bids": bids,
        })
        self.notes["straddle_settled"] += 1
        self.ticket = None

    def _manage(self, book, obs, now):
        super()._manage(book, obs, now)
        ticket = self.ticket
        if ticket is None:
            return
        minute = now.hour * 60 + now.minute
        if ticket.day != now.date().isoformat() or minute > settings.FNO_HARD_FLAT_MIN:
            self.incomplete = bool(ticket.buys)
            self.ticket = None
            return
        if ticket.stage in ("FIRST", "SECOND"):
            self._buy(ticket, book, obs, now)
            return
        bids = {token: self.mark(obs, token, now) for token in ticket.buys}
        complete = all(bid is not None for bid in bids.values())
        if ticket.stage == "CLOSE":
            if complete:
                self._settle(ticket, book, now, bids)
            return
        net = amounts(ticket.buys, bids)[-1] if complete else None
        if minute >= 885:
            ticket.reason = "straddle_clock"
        elif net is not None and net <= -1800.:
            ticket.reason = "straddle_loss"
        elif net is not None and net >= 3000.:
            ticket.reason = "straddle_gain"
        if ticket.reason:
            ticket.stage = "CLOSE"

    def run(self, start, end):
        with closing(self.data._connect()) as self.raw:
            out = super().run(start, end)
        if self.incomplete or (self.ticket and self.ticket.buys):
            out["trades"].append({"tradingsymbol": "NIFTY_COMPRESSION_STRADDLE", "status": "UNRESOLVED"})
        return out


def book_for_run():
    book = copy.deepcopy(r.books()["N11T"])
    book["label"] = "N12|COMPRESSION_STRADDLE"
    return book


def main():
    spec = HERE / "round16-freeze.json"
    cfg = json.loads(spec.read_bytes())
    assert cfg == json.loads(subprocess.check_output(
        ["git", "show", f"HEAD:{spec.relative_to(r.ROOT).as_posix()}"], cwd=r.ROOT))
    for name, sha in cfg["files"].items():
        assert hashlib.sha256((HERE / name).read_text(encoding="utf-8").encode()).hexdigest() == sha, name
    assert cfg["book"] == json.loads(json.dumps(book_for_run()))
    r.verify_freeze()
    dataset = r.DATASETS[r.YEAR]
    manifest = json.loads((dataset / "manifest.json").read_bytes())
    with (dataset / "breeze.sqlite").open("rb") as handle:
        assert hashlib.file_digest(handle, "sha256").hexdigest() == manifest["files_sha256"]["breeze.sqlite"]
    controls = {name: r.raw_for(r.books()[name]) for name in ("N11", "N11T")}
    for name, raw in controls.items():
        assert r.money(raw) == r.money(trades(r.YEAR, name)[1]), name
    r.f.Z.N.B.O27F.deny_network()
    r.f.Z.N.B.L._init()
    with Y.ROUTER.dispatch():
        engine = StraddleReplay(Y.dataset("year"), book_for_run(), Y.table("year"), "year")
        data = engine.run(*r.WINDOW)
    for row in data["trades"]:
        row.setdefault("status", "CLOSED" if row.get("net_pnl") is not None else "UNRESOLVED")
    out = {name: r.metrics(value) for name, value in {**controls, NAME: data}.items()}
    out["straddles"] = [t for t in data["trades"] if t["tradingsymbol"] == "NIFTY_COMPRESSION_STRADDLE"]
    with (HERE / f"round16-{r.YEAR}.json").open("x", encoding="utf-8") as file:
        json.dump(out, file, indent=2, sort_keys=True, default=str)
        file.write("\n")
    row = out[NAME]
    print(r.YEAR, row["net"], row["unresolved"], {k: v for k, v in row["notes"].items() if k.startswith("straddle")}, flush=True)


if __name__ == "__main__":
    main()
