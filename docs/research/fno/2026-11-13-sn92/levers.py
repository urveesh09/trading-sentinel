"""SN100b (description, written after SN92-SN100 were scored; it chooses nothing): the owner's money levers for Gold
v5 itself - day loss limit (15 / 20 / 25 / 30% of the wallet), growth trigger (after 100% or 50% net profit) and cap
(stop after 0 / 2 / 3 / 5 steps), at starts Rs 15k / 20k / 30k / 50k. In-sample; the per-lot rules are v5's in every
row. Plus a post-hoc description of SN95's one positive lead (the 10:00 cheap straddle): concentration, +Rs 400 per
leg, the entry 1 minute late, and overlap with Gold's days."""
from __future__ import annotations

import itertools
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common as C  # noqa: E402
import sn95  # noqa: E402

STARTS = (15000.0, 20000.0, 30000.0, 50000.0)
CAPS = (0, 2, 3, 5)


def levers():
    wallets = tuple((f"{int(s / 1000)}k cap {k}", s, "grow", k) for s, k in itertools.product(STARTS, CAPS))
    out = {}
    for loss, trig in itertools.product((0.15, 0.20, 0.25, 0.30), (1.0, 0.5)):
        p = C.panel(C.run({**C.V5, "loss_share": loss, "g_trig": trig}, wallets))
        out[f"day limit {int(loss * 100)}% | step after {int(trig * 100)}%"] = p
        print(f"--- day limit {int(loss * 100)}% | step after {int(trig * 100)}% profit")
        for w, r in p.items():
            print(f"   {w:12s} net {r['net']:>9} by year {r['by_year']} refilled {r['refilled']:>9} worst {r['worst']:>8} losing years {r['losing_years']}", flush=True)
    return out


def straddle_lead():
    Ys = C.years()
    rows, adm = sn95.features()
    labels = {r["day"]: r for r in json.loads((C.FNO / "2026-11-13-sn76" / "_local" / "days.json").read_text(encoding="utf-8"))}
    out = {}
    for name, day_ok in (("gold-free", C.gold_free), ("all days", lambda d: C.adx(d) is not None)):
        for label, ls, late in (("house 100/leg", 100.0, 0), ("strict 205/leg", 205.0, 0), ("stress 400/leg", 400.0, 0),
                                ("1 minute late, 100/leg", 100.0, 1)):
            trades = []
            for y in C.YEARS:
                for S in Ys[y].ordered():
                    if day_ok(S.day) and adm.get((S.day, "10:00", "R_today", 0.2, "top"), False):
                        got = sn95.play(S, 45 + late, "buy", None, 1, 3000.0, ls, 15000.0)
                        if got is not None:
                            trades.append((S.day, round(got[0]), bool(labels.get(S.day, {}).get("trades"))))
            nets = sorted((t[1] for t in trades), reverse=True)
            out[f"{name} | {label}"] = {"trades": len(trades), "net": sum(nets), "without_best_5": sum(nets[5:]),
                                        "won": sum(n > 0 for n in nets), "lost": sum(n < 0 for n in nets),
                                        "on_gold_trade_days": sum(t[2] for t in trades),
                                        "by_year": {y: sum(t[1] for t in trades if t[0][:4] == y) for y in C.YEARS},
                                        "best5": nets[:5]}
            print(f"SN95 lead {name:9s} {label:24s}", out[f"{name} | {label}"], flush=True)
    return out


if __name__ == "__main__":
    res = {"levers": levers(), "sn95_lead": straddle_lead()}
    (HERE / "results-levers.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
