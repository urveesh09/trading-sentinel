"""SN419: the cheap opener and Gold in one chronological ledger (PLAN.md section 1, frozen at e5cc95b7; details fixed here
before any number). Development only (the opener's rows are seen history).

ow.run_wallet with a leg (SN252's contract: the leg trades only while no Gold position is open, its loss reduces Gold's day
room `loss + realized`, a Gold signal while it is open sells it that minute and Gold then enters). 2023-26 path, Gold v5
unchanged at Rs 30k with growth, Rs 205 / 400.
OPENER (fw9's rule on the HONEST clock): only on CHEAP auction sessions (sn353b auctions with g != 0, fixed-cutoff HONEST
jump label), only at the session's start (i_from == 0): the auction side, 2-ITM then 1-ITM whose label ask x 65 + entry
charges <= min(Rs 15,000, the spendable wallet - Rs 15,000 reserve); filled at the 09:15 close; stop = min(the leg room ow
passes, Rs 3,000); exit at 60 minutes, or at Gold's first signal minute if earlier (forced).
NEVER: the same ledger with a leg that never enters must give Gold alone (Rs 8,50,882 / 883 at Rs 205).
Reported: Gold-alone and shared-ledger nets (total, 2025-26, the opener window), the opener's own net, trades, forced exits,
stop overshoots (loss beyond the intended stop), days whose total loss passes 20% of the wallet, the worst opener loss
against its no-bid bound (the paid debit + fees), and Gold's net change on the opener's days.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "2026-11-17-sn396"))
import gold  # noqa: E402
import op  # noqa: E402

gl, wk = op.gl, op.wk
OUT = HERE / "results-sn419.json"


class Never:
    def intraday(self, smp, d, i_from, spendable, room, stop_at):
        return None


class Opener:
    def __init__(self, cheap, au, stress):
        self.cheap, self.au, self.stress, self.log = cheap, au, stress, []

    def intraday(self, smp, d, i_from, spendable, room, stop_at):
        if i_from != 0 or d not in self.cheap or d not in smp.s:
            return None
        s, a = smp.s[d], self.au[d]
        side = "CE" if a["g"] > 0 else "PE"
        cap = min(op.ROOM, spendable)
        atm = gl.atm(smp, s, 0)
        sgn = -1 if side == "CE" else 1
        pos = None
        for dep in (2, 1):
            k = atm + sgn * dep * 50
            p = gl.opx(s, k, side, 0)
            if p is None or op.entry_cost(wk.ask(smp.mk, p)) > cap:
                continue
            pos = gl.Pos(smp, s, [(k, side, +1)], 0, lots=1, stress=self.stress)
            if pos.ok:
                break
            pos = None
        if pos is None:
            return None
        stop = min(room, 3000.0)
        end = 60 if stop_at is None else min(60, stop_at)
        net, j, why = gl.walk(pos, s, 0, end, room=stop)
        if net is None:
            return None
        if why == "time" and stop_at is not None and end == stop_at:
            why = "forced"
            j = stop_at
        debit = op.entry_cost(pos.fills[0])
        self.log.append({"day": d, "net": round(net, 2), "why": why, "j": j, "stop": stop, "debit": round(debit, 2),
                         "no_bid_bound": round(-(debit + 0.0), 2), "overshoot": round(max(0.0, -net - stop), 2)})
        return net, j, why


def main():
    if OUT.exists():
        raise SystemExit("SN419 is run once")
    smp, _days, au = op.setup()
    jm = op.jumps(smp, "HONEST")
    lab = op.labels(jm, True)
    cheap = {d for d, a in au.items() if a["g"] != 0 and lab.get(d) == "CHEAP"}
    res = {"cheap_sessions": len(cheap)}
    for st in (205.0, 400.0):
        alone_days, alone_log, _ = gold.run(gold.Y2326, gold.DEPLOYED, st)
        never_days, never_log, _ = gold.run(gold.Y2326, gold.DEPLOYED, st, leg=Never())
        if st == 205.0:
            assert gold.summary(never_days, never_log)["net"] in (850882, 850883), gold.summary(never_days, never_log)["net"]
        leg = Opener(cheap, au, st)
        days, log, legs = gold.run(gold.Y2326, gold.DEPLOYED, st, leg=leg)
        a, b = gold.summary(alone_days, alone_log), gold.summary(days, log)
        gold_net_alone = {d: n for d, _w, n, _t, _l in alone_days}
        gold_part = {d: n - ln for d, _w, n, _t, ln in days}
        wal = {d: w for d, w, *_ in days}
        ld = {x["day"] for x in leg.log}
        win = [d for d, *_ in days if "2025-12-08" <= d < "2026-10-29"]
        res[f"@{int(st)}"] = {
            "gold_alone": {k: a[k] for k in ("net", "by_year", "months_positive", "worst_month", "refilled")},
            "never_leg_parity": gold.summary(never_days, never_log)["net"],
            "shared_ledger": {k: b[k] for k in ("net", "by_year", "months_positive", "worst_month", "refilled")},
            "increment_total": b["net"] - a["net"],
            "opener_window_sessions": len(win), "opener_trades": len(leg.log), "opener_net": round(sum(x["net"] for x in leg.log)),
            "opener_winners": sum(x["net"] > 0 for x in leg.log), "forced_by_gold": sum(x["why"] == "forced" for x in leg.log),
            "stops": sum(x["why"] == "stop" for x in leg.log), "stop_overshoots": sum(x["overshoot"] > 0 for x in leg.log),
            "worst_overshoot": max([x["overshoot"] for x in leg.log], default=0.0), "worst_opener_loss": min([x["net"] for x in leg.log], default=0.0),
            "worst_no_bid_bound": min([x["no_bid_bound"] for x in leg.log], default=0.0),
            "gold_net_change_on_opener_days": round(sum(gold_part.get(d, 0.0) - gold_net_alone.get(d, 0.0) for d in ld)),
            "gold_net_change_elsewhere": round(sum(gold_part.get(d, 0.0) - gold_net_alone.get(d, 0.0) for d in gold_part if d not in ld)),
            "days_total_loss_over_20pct": sum(1 for d, w, n, *_ in days if n <= -0.2 * w),
            "days_total_loss_over_20pct_gold_alone": sum(1 for d, w, n, *_ in alone_days if n <= -0.2 * w),
            "per_market_session_increment_window": round((b["net"] - a["net"]) / max(1, len(win)), 1),
            "opener_log": leg.log}
        r = res[f"@{int(st)}"]
        print(int(st), json.dumps({k: v for k, v in r.items() if k not in ("opener_log",)}), flush=True)
    OUT.write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    main()
