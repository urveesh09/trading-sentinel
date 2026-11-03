"""E01.1 (the main paper C) on NIFTY 2024, the one recorded-chain year it was never run on.

Identical to the November 3 year study's 2025 minute C proxy (minutes.py): C's strike pick,
box, failed-break exit, one ticket a day, two completed minute confirmations (65 s), next-bar
fills, flat from 15:28, NIFTY lot 65 and today's fees. Only the source year differs. E01.1's
rules were frozen on November 2, before any 2024 price was opened, so this is a clean test
of those rules (the 2024 market itself has since been read by the E02 study).
"""
from __future__ import annotations
import json, sqlite3, sys
from collections import defaultdict
from datetime import datetime, timedelta, date
from pathlib import Path

HERE = Path(__file__).resolve().parent
YEAR = HERE.parent / "2026-11-03-expiry-year"
sys.path.insert(0, str(YEAR))
import study as S                 # noqa: E402
import minutes as MY              # noqa: E402

SOURCE = HERE.parent / "2026-11-03-expiry-e02/_local/2024.sqlite"


class Minute2024(MY.Minute):
    def __init__(self, day):
        self.day = day; self.underlying = "NIFTY"; self.date = date.fromisoformat(day)
        self.info = {"window": "nifty2024-minute-proxy"}
        self.exchange = "NFO"; self.schedule = S.EP.fee_schedule("NFO"); self.step = 50.; self.lot = 65
        self.p75 = json.loads((S.OLD / "spreads.json").read_text())["p75"]
        c = sqlite3.connect(SOURCE.resolve().as_uri() + "?mode=ro", uri=True)
        c.row_factory = sqlite3.Row
        rows = c.execute("SELECT * FROM candles WHERE datetime BETWEEN ? AND ? ORDER BY datetime",
                         (day + " 12:59:00", day + " 15:29:00")).fetchall()
        c.close()
        by_stamp = defaultdict(dict); index = {}; future = {}; contracts = {}; self.invalid_rows = 0
        for r in rows:
            stamp = r["datetime"]
            vals = [r[k] for k in ("open", "high", "low", "close")]
            valid = all(v is not None and v > 0 for v in vals) and r["low"] <= min(r["open"], r["close"]) <= max(r["open"], r["close"]) <= r["high"]
            if not valid or (r["kind"] == "option" and (r["volume"] is None or r["volume"] < 0)):
                self.invalid_rows += 1; continue
            if r["kind"] == "index": index[stamp] = r["close"]
            elif r["kind"] == "future": future[stamp] = r["close"]
            elif r["kind"] == "option":
                assert r["expiry"] == day
                name = f"NIFTY-{day}-{r['strike']:g}-{r['opt']}"
                if name not in contracts:
                    contracts[name] = S.L.Contract(300000000 + len(contracts), name, "NIFTY", self.date, r["strike"], r["opt"], 65)
                by_stamp[stamp][name] = dict(r)
        stamps = [(datetime.fromisoformat(day + " 12:59:00") + timedelta(minutes=i)).isoformat(sep=" ") for i in range(151)]
        self.now = [datetime.fromisoformat(t).replace(tzinfo=S.EP.IST) + timedelta(minutes=1) for t in stamps]
        self.clock = [t.time() for t in self.now]; self.n = len(stamps)
        self.spot = [index.get(t) for t in stamps]; self.fut = [future.get(t) for t in stamps]
        self.anchor = [self.spot[max(0, i - 1)] for i in range(self.n)]
        self._bars = [by_stamp[t] for t in stamps]; self.names = sorted(contracts)
        self._contract = contracts; self.kinds = {n: n for n in self.names}
        self._signals = {}


def main():
    S.no_network()
    c = sqlite3.connect(SOURCE.resolve().as_uri() + "?mode=ro", uri=True)
    days = [r[0] for r in c.execute("SELECT DISTINCT substr(datetime,1,10) FROM candles WHERE datetime>='2024-01-01' AND datetime<'2025-01-01' ORDER BY 1")]
    c.close()
    arms = {k: S.FIXED[k] for k in ("C", "E01", "E011", "E011R")}
    out = {n: {s: [] for s in ("ordinary", "adverse")} for n in arms}
    for day in days:
        x = Minute2024(day); state, fire = MY.signals(x)
        for name, ticket in arms.items():
            for scenario, adverse in (("ordinary", False), ("adverse", True)):
                for i, d in fire:
                    strike = S.L._pick(x, i, d, ticket)
                    if strike is None:
                        continue
                    contract, q = x.quoted_chain(i)[(strike, "CE" if d == "UP" else "PE")]
                    filled = S.simulate(x, (i, contract.tradingsymbol, "RECORDED_CHAIN_BREAK"), ticket, adverse, failed_back=True)
                    if filled:
                        S.audit_position(filled); out[name][scenario].append(filled); break
    summary = {n: {s: {k: v for k, v in S.stats(p).items() if k != "daily"} for s, p in sc.items()} for n, sc in out.items()}
    S.dump(HERE / "e011-2024.json", dict(model="RECORDED_CHAIN_MINUTE_C_PROXY_v1 (2024 source)", sessions=len(days), summaries=summary,
                                         daily={n: S.stats(out[n]["ordinary"]).get("daily") for n in arms}))
    for n in arms:
        print(n, {s: {k: summary[n][s][k] for k in ("tickets", "net", "without_best", "worst", "wins", "reached3x")} for s in summary[n]})


if __name__ == "__main__":
    main()
