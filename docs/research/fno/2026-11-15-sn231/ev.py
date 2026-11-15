"""SN235-SN245 shared scoring: a WK-type leg on the five WK samples (per option lot: net, months positive by settlement
month, worst month) and inside the Gold v6 account (Gold v5 + the leg's daily marks, DEV + TEST, Jan 2023 - Oct 2026)."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import led  # noqa: E402

BASE_WKH = {}


def wk_stats(by_sample, lots=2):
    out = {n: led.wk_month_stats(tr, lots) for n, tr in by_sample.items()}
    out["positive_samples"] = sum(out[n]["net"] > 0 for n in by_sample)
    out["months_positive_total"] = sum(out[n]["months_positive"] for n in by_sample)
    out["months_total"] = sum(out[n]["months"] for n in by_sample)
    return out


def account(legs_days, replace_wkh=True):
    """Gold v5 + the given legs' daily marks (+ WK-H unless replaced)."""
    days = led.sessions()
    g = led.gold()
    tot = dict(g)
    if not replace_wkh:
        for d, x in led.wkh_days().items():
            tot[d] = tot.get(d, 0.0) + x
    for leg in legs_days:
        for d, x in leg.items():
            tot[d] = tot.get(d, 0.0) + x
    return led.account_stats(tot, days)


def leg_days(trades):
    return led.leg_days(trades)


def q4(stats, base):
    return stats["positive_samples"] >= 4 and stats["months_positive_total"] >= base["months_positive_total"]


def line(tag, st, ac):
    per = " | ".join(f"{n} {st[n]['net']:>8} ({st[n]['months_positive']}/{st[n]['months']}, wm {st[n]['worst_month']})" for n in led.WK_SAMPLES if n in st)
    return (f"{tag:44s} {per} || account net {ac['net']:>9} months+ {ac['months_positive']}/{ac['months']} worst {ac['worst_month']:>8} "
            f"2nd {ac['second_worst_month']:>8}")
