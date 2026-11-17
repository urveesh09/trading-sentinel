"""SN477: record the held contract until it is closed (PLAN.md SN477, frozen at bf895633). Trace receipt for the Dev change.

The change (python-engine/research_pins.py; sn_gold.on_paper_signal and fno_n11.record_paper_signal call it; setting
RESEARCH_PIN_PAPER_LEGS, default on): each paper entry registers its exact contract in research_leg_subscriptions until 15:20 IST,
and the minute collector unions those legs with its rolling +-RESEARCH_QUOTE_STRIKE_WINDOW window (research_quote_collector.
_with_active_legs, unchanged). The tick recorder needs no change: its subscription set only grows during a day and is
resubscribed whole after a drop (test_tick_recorder covers both).
Trace check on SN464's two unpriced deep-ITM exits: the held strike, the archive window at the exit minutes (SN464's receipt), and
the engine's own union function applied to that window with the pinned contract (a store in a temporary folder).
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "python-engine"))
OUT = HERE / "results-sn477.json"
IST = timezone(timedelta(hours=5, minutes=30))


def main():
    if OUT.exists():
        raise SystemExit("SN477 is scored once")
    from config import settings
    import research_pins
    import research_quote_collector as rqc
    from fno_models import Contract
    from research_leg_subscriptions import ResearchLegSubscriptionStore
    rows = json.loads((HERE.parent / "2026-11-17-sn456" / "results-sn464.json").read_text(encoding="utf-8"))["rows"]
    res = {"traces": []}
    with tempfile.TemporaryDirectory() as tmp:
        settings.RESEARCH_ARCHIVE_PATH = tmp
        settings.RESEARCH_ARCHIVE_ENABLED = True
        settings.RESEARCH_PIN_PAPER_LEGS = True
        for r in rows:
            if r["day"] not in ("2026-10-08", "2026-10-21"):
                continue
            _und, expiry, strike, opt = r["contract"]          # SN464's receipt: [underlying, expiry, strike, type]
            strike = float(strike)
            sym = f"NIFTY{expiry}{int(strike)}{opt}"
            lo, hi, n = r["exit_minutes"][0]["window"]
            held = Contract(token=900000 + int(strike), tradingsymbol=sym, name="NIFTY", expiry=date.fromisoformat(expiry),
                            strike=strike, instrument_type=opt, lot_size=65, tick_size=0.05)
            entry_at = datetime.fromisoformat(r["day"]).replace(tzinfo=IST) + timedelta(minutes=555 + r["i"])
            pinned = asyncio.run(research_pins.pin([held], f"sn_gold:trace-{r['day']}", entry_at))
            window = [(Contract(token=800000 + k, tradingsymbol=f"W{k}", name="NIFTY", expiry=held.expiry, strike=lo + 50.0 * k,
                                instrument_type=opt, lot_size=65, tick_size=0.05), "atm_window") for k in range(int(n))]
            at_exit = datetime.fromisoformat(r["day"]).replace(tzinfo=IST) + timedelta(minutes=555 + r["j"])
            legs, short = ResearchLegSubscriptionStore(tmp).active(underlying="NIFTY", now=at_exit, capacity=50)
            merged = rqc._with_active_legs(window, legs)
            res["traces"].append({"day": r["day"], "contract": sym, "held_strike": strike, "entry_minute": r["i"], "exit_minute": r["j"],
                                  "archive_window_at_exit": [lo, hi, n], "held_inside_window": lo <= strike <= hi, "pin": pinned,
                                  "held_in_collector_request_with_pin": held.token in {c.token for c, _r in merged}, "capacity_shortfall": len(short),
                                  "replay_net": r.get("replay_net")})
    res["recorder"] = "no change: Universe grows only within a day and resubscribes the whole set after a drop (tests: widens_but_never_narrows, a_drop_reconnects_resubscribes_everything)"
    res["pass"] = all((not t["held_inside_window"]) and t["held_in_collector_request_with_pin"] for t in res["traces"]) and len(res["traces"]) == 2
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
