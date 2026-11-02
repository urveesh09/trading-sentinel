"""Post-score independent trade-price and native signal/admission clock checks."""
import json
import os
from datetime import date, datetime
from pathlib import Path

import n091_lab as L

HERE = Path(__file__).resolve().parent


def main():
    L.verify()
    L.Z.B.L._init()
    data = L.Y.dataset("year")
    packets = {}
    checks = 0
    for phase in ("controls", "primary", "costs", "carry"):
        keys = json.loads((L.LOCAL / f"keys-{phase}-{L.YEAR}.json").read_text())
        for name, key in keys.items():
            obj = json.loads((L.Y.EVALS / f"{key}.json").read_text())
            for t in obj["trades"]:
                day = t["entry_time"][:10]
                if day not in packets:
                    packets[day] = {o.at.isoformat(): o for o in data.observations(day)[0]}
                for field, clock, side in (("entry_premium", "entry_time", "ask"), ("exit_premium", "exit_time", "bid")):
                    obs = packets[day][t[clock]]
                    quotes = [q for q in obs.options.values() if q.contract.tradingsymbol == t["tradingsymbol"]]
                    assert len(quotes) == 1
                    value = getattr(quotes[0], side)
                    if side == "bid" and value <= 0:
                        value = quotes[0].ltp
                    assert abs(value - t[field]) < .001, (L.YEAR, name, t[clock], side)
                    assert quotes[0].contract.lot_size == 65
                    checks += 1
                assert L.Y.ROUTER.allowed(t["entry_gate"], L.C.table("year")[day])
    out = {"year": L.YEAR, "prices_checked": checks, "trade_days": len(packets),
           "quote_basis": "archived candle-derived modeled bid/ask; not historical market depth"}
    L.write(HERE / f"price-audit-{L.YEAR}.json", out)
    print(out)


if __name__ == "__main__":
    main()
