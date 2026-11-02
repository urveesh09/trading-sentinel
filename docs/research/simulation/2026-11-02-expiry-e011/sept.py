"""The four September expiries as a session the lab can run. PARTIAL, and labelled so everywhere.

What the files hold: one opening-ATM strike, call and put, ten-second OHLC built from real one-second candles,
09:15:00 to 15:29:50. No bid, ask or depth, no index, no other strike. So:

  * The index is the put-call forward K + C - P on the last three bars' median, a causal proxy. The engine's box and
    confirmation run on it, with future = spot because there is no independent future at this resolution.
  * The engine samples one price every ten seconds, so a tick here is one bar's CLOSE, known at the bar's end. No
    tick sees inside a bar.
  * Bid and ask are the close less and plus half the 75th-percentile spread that the eight archived sessions show at
    that price, rounded away to the 0.05 tick. Adverse execution fills at the NEXT bar's low (sell) or high (buy), less
    or plus the same half spread: decided on this bar, filled at the worst price of the next ten seconds.
  * Depth is 20% of the bar's traded quantity, so a thin bar can refuse a fill.
  * A and B usually can't run: they need strikes the file doesn't hold. C can run only when the fixed strike happens to
    be out of the money and in the band at a break. Other breaks are UNAVAILABLE, never zero.
  * A leg still open at the last bar sells at that bar's bid, or is worthless if there is none. The files end before
    the engine's 15:38 flat, so this is a data limit and every arm shares it.
"""
from __future__ import annotations

import csv
import json
import math
import statistics
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np

import e011_lab as L
from e011_lab import EP

SOURCE = Path(r"C:\Users\Urveesh\sentinel-operations\breeze-history-20261029\data\nifty-expiry-10second-20261102")
SNAPSHOT = L.LOCAL / "sept"
SPREADS = L.HERE / "spreads.json"
DAYS = ("2026-09-08", "2026-09-15", "2026-09-22", "2026-09-29")
BUCKETS = (2.0, 5.0, 10.0, 25.0, 50.0, 100.0, float("inf"))
DEPTH_SHARE = 0.20
TICK = 0.05
START = "12:58:50"


def _bucket(price: float) -> int:
    return next(k for k, top in enumerate(BUCKETS) if price < top)


def build_spreads() -> dict:
    """75th-percentile spread by price, NIFTY options, continuous session, from the archived sessions' real quotes."""
    samples: list[list[float]] = [[] for _ in BUCKETS]
    for day, u in L.recorded_keys():
        if u != "NIFTY":
            continue
        S = L.Recorded(day, u)
        for i in range(S.n):
            if not EP.BOX_END <= S.clock[i] < EP.A_ENTRY_END or i % 6:
                continue
            for symbol in S.names:
                q = S.quote(i, symbol)
                if q is not None and q.bid is not None and q.ask is not None and q.ask >= q.bid:
                    samples[_bucket((q.bid + q.ask) / 2)].append(round(q.ask - q.bid, 4))
    table = {"buckets": [str(b) for b in BUCKETS], "p75": [], "n": []}
    for rows in samples:
        rows.sort()
        table["p75"].append(rows[int(len(rows) * .75)] if rows else None)
        table["n"].append(len(rows))
    SPREADS.write_text(json.dumps(table, indent=1) + "\n")
    return table


def _down(x: float) -> float:
    return round(math.floor(round(x / TICK, 6)) * TICK, 2)


def _up(x: float) -> float:
    return round(math.ceil(round(x / TICK, 6)) * TICK, 2)


class Sept:
    partial = True

    def __init__(self, day: str, adverse: bool = False, folder: Path = SNAPSHOT):
        self.day, self.underlying, self.adverse = day, "NIFTY", adverse
        self.date = date.fromisoformat(day)
        self.exchange = "NFO"
        self.schedule = EP.fee_schedule("NFO")
        self.step = 50.0
        self.lot = 65
        self.p75 = json.loads(SPREADS.read_text())["p75"]
        bars: dict[str, dict] = {}
        with open(folder / f"NIFTY-{day}-ATM-CE-PE-10second.csv", newline="") as f:
            rows = list(csv.DictReader(f))
        self.strike = float(rows[0]["strike"])
        for r in rows:
            bars.setdefault(r["datetime_ist"][11:], {})[r["option"]] = r
        stamps = [t for t in sorted(bars) if t >= START and len(bars[t]) == 2]
        self.names = [f"NIFTY{day}{self.strike:g}{k}" for k in ("CE", "PE")]
        self.index = {n: j for j, n in enumerate(self.names)}
        self.kinds = {n: k for n, k in zip(self.names, ("CE", "PE"))}
        self._contract = {n: L.Contract(200000000 + j, n, "NIFTY", self.date, self.strike, k, self.lot)
                          for j, (n, k) in enumerate(self.kinds.items())}
        self.n = len(stamps)
        tz = EP.IST
        self.now = [datetime.fromisoformat(f"{day}T{t}").replace(tzinfo=tz) + timedelta(seconds=10) for t in stamps]
        self.clock = [t.time() for t in self.now]
        self._bars = [bars[t] for t in stamps]
        raw = [self.strike + float(b["CE"]["close"]) - float(b["PE"]["close"]) for b in self._bars]
        self.raw_forward = raw
        self.spot = [statistics.median(raw[max(0, i - 2): i + 1]) for i in range(self.n)]
        self.fut = list(self.spot)
        self.anchor = [self.spot[max(0, i - 1)] for i in range(self.n)]
        self._signals: dict = {}

    def _half(self, price: float) -> float:
        return (self.p75[_bucket(price)] or TICK) / 2.0

    def quote(self, i: int, symbol: str) -> Optional[EP.Quote]:
        kind = self.kinds.get(symbol)
        if kind is None:
            return None
        bar = self._bars[i][kind]
        close = float(bar["close"])
        if self.adverse:
            next_bar = self._bars[i + 1][kind] if i + 1 < self.n else bar
            sell_at, buy_at = float(next_bar["low"]), float(next_bar["high"])
            volume = float(next_bar["volume"])
        else:
            sell_at, buy_at = close, close
            volume = float(bar["volume"])
        half = self._half(close)
        bid, ask = _down(sell_at - half), _up(buy_at + half)
        depth = int(volume * DEPTH_SHARE)
        if depth < self.lot:
            return EP.Quote(bids=(), asks=(), ltp=close, ts=self.now[i] - timedelta(seconds=5))
        return EP.Quote(bids=((bid, depth),) if bid > 0 else (), asks=((ask, depth),), ltp=close,
                        ts=self.now[i] - timedelta(seconds=5))

    def contracts_near(self, i: int) -> dict:
        return {(self.strike, self.kinds[n]): self._contract[n] for n in self.names}

    def quoted_chain(self, i: int) -> dict:
        return {(self.strike, self.kinds[n]): (self._contract[n], self.quote(i, n)) for n in self.names}

    def atm(self, spot: float) -> float:
        return float(round(spot / self.step) * self.step)

    def contract(self, symbol: str):
        return self._contract.get(symbol)

    def settlement_spot(self):
        return None


def settle_partial(S: Sept, positions: list[dict]) -> None:
    """A leg still open when the file ends sells at the last bar's bid, or is worthless with none."""
    for pos in positions:
        if pos["status"] != "OPEN":
            continue
        q = S.quote(S.n - 1, pos["symbol"])
        if q is not None and q.bid is not None:
            filled, price = EP.walk(q.bids, pos["lots_open"], pos["lot_size"])
            if filled:
                EP._sell(pos, filled, price, "DATA_END", S.now[-1])
        if pos["status"] == "OPEN":
            qty = pos["lots_open"] * pos["lot_size"]
            pos["status"] = "WORTHLESS_AT_DATA_END"
            pos["assumed_pnl"] = round(-pos["entry_price"] * qty, 2)


def validate(folder: Path = SNAPSHOT) -> dict:
    """Independent checks on the snapshot: grid, OHLC, missing seconds. No strategy, no outcome."""
    out = {}
    for day in DAYS:
        with open(folder / f"NIFTY-{day}-ATM-CE-PE-10second.csv", newline="") as f:
            rows = list(csv.DictReader(f))
        legs = {"CE": [], "PE": []}
        bad = 0
        for r in rows:
            o, h, l, c = (float(r[k]) for k in ("open", "high", "low", "close"))
            if not (0 < l <= min(o, c) and h >= max(o, c)):
                bad += 1
            legs[r["option"]].append(r["datetime_ist"])
        out[day] = dict(rows=len(rows), ce=len(legs["CE"]), pe=len(legs["PE"]), unique_ce=len(set(legs["CE"])), unique_pe=len(set(legs["PE"])),
                        first=min(legs["CE"]), last=max(legs["CE"]), strikes=sorted({r["strike"] for r in rows}), bad_ohlc=bad,
                        missing_seconds=sum(int(r["missing_source_seconds"]) for r in rows),
                        invalid_volume=sum(int(r["invalid_volume_source_seconds"]) for r in rows))
    return out
