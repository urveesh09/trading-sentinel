"""Offline synthetic tape exercise of the production-callable Penny paper functions.

Run with the engine Python from the repository root. No provider, order,
scheduler or notification is started. These numbers are engineering fixtures.
"""
import hashlib
import asyncio
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from datetime import datetime

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "python-engine"))
import penny_auction_forward as f
from config import settings


def at(clock, day="2026-11-09"):
    return datetime.fromisoformat(day + "T" + clock).replace(tzinfo=f.IST)


def packet(clock, *, price=19., bid=20., volume=10000, trade=None):
    return {"timestamp": at(clock), "last_trade_time": at(trade or clock),
            "last_price": price, "ohlc": {"close": 20., "open": 19.}, "volume": volume,
            "depth": {"buy": [{"price": bid, "quantity": 10000}],
                      "sell": [{"price": bid + .05, "quantity": 10000}]}}


def exercise():
    results = {"synthetic": True, "financial_qualification": "NOT_EVALUATED", "scenarios": {}}
    with TemporaryDirectory() as scratch:
        for name, missing in (("complete_observed_tape", False), ("missing_matching_quote", True)):
            cache = str(Path(scratch) / name)
            f.capture_smart(cache, {"AAA": packet("09:07:00")}, {"AAA": (2e6, 1e5)},
                            {"AAA": 10000}, at("09:07:00"))
            with f.store(cache) as c:
                for phase, clock, quotes in (
                    ("MATCH", "09:12:00", {} if missing else {"AAA": packet("09:12:00", trade="09:11:00")}),
                    ("MORNING", "09:30:00", {"AAA": packet("09:30:00")}),
                    ("POST_BASE", "15:51:00", {"AAA": packet("15:51:00", price=20.5, volume=20000)}),
                    ("POST_END", "16:03:00", {"AAA": packet("16:03:00", trade="15:59:00", price=20.5, volume=40000)}),
                ):
                    f.apply_phase(c, phase, quotes, at(clock))
                records = f.rows(c)
                for row in records:
                    assert row["reserve"] <= row["initial_capital"]
                    if row["status"] == "CLOSED":
                        gross = (row["exit_price"] - row["entry_price"]) * row["modeled_quantity"]
                        assert abs(gross - row["costs"] - row["net"]) < 1e-8
                        assert row["modeled_quantity"] <= row["order_quantity"]
                if missing:
                    assert all(row["status"] == "UNRESOLVED" for row in records)
            results["scenarios"][name] = f.comparison(cache)
    results["source_sha256"] = hashlib.sha256((ROOT / "python-engine/penny_auction_forward.py").read_bytes()).hexdigest()
    return results


async def concurrent_receipts():
    """Race two actual collector invocations through a deterministic fake broker."""
    class QuotesOnly:
        instrument_cache = {"AAA": 1}
        def __init__(self):
            self.calls = 0
            self.both = asyncio.Event()
        async def get_quote(self, tokens):
            self.calls += 1
            if self.calls == 2:
                self.both.set()
            await self.both.wait()
            return {1: packet("09:12:00", trade="09:11:00")}
    with TemporaryDirectory() as scratch:
        cache = str(Path(scratch) / "concurrent")
        f.capture_smart(cache, {"AAA": packet("09:07:00")}, {"AAA": (2e6, 1e5)},
                        {"AAA": 10000}, at("09:07:00"))
        kite = QuotesOnly()
        result = await asyncio.gather(*(f.collect(kite, "MATCH", cache, now=at("09:12:00")) for _ in range(2)))
        assert sorted(x["status"] for x in result) == ["observed", "repeat"]
        with f.store(cache) as c:
            records = f.rows(c)
            assert len(records) == 2 and all(r["status"] == "OPEN" for r in records)
            assert c.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
        return {"statuses": sorted(x["status"] for x in result), "rows": len(records),
                "actual_fill": "UNKNOWN", "quote_calls": kite.calls}


if __name__ == "__main__":
    # Only this disposable research process is configured. No .env file changes.
    settings.PENNY_AUCTION_FORWARD_ENABLED = True
    settings.PENNY_SMART_V3_ENABLED = True
    settings.PENNY_SMART_V3_BANKROLL = 2000.
    out = exercise()
    out["concurrent_collector"] = asyncio.run(asyncio.wait_for(concurrent_receipts(), timeout=5.))
    path = Path(__file__).with_name("synthetic-results.json")
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    for name, result in out["scenarios"].items():
        print(name, {k: {x: v[x] for x in ("closed", "unresolved", "complete_modeled_net")}
                     for k, v in result["variants"].items() if k in f.SMART})
