"""SN455 (own): what a development number is worth - the SN program's own record of development results against later
unseen / held-out results for the same frozen rule (PLAN.md section 2, frozen at f56f5807; the table below was extracted
before any summary was computed, each row with its source).

Rate = the result divided by the sample's length in the unit the source states (years, or trades); a row whose length is not
stated is used for the sign only. Unit per row as the source gives it (per lot, or the wallet's rupees).
Reported: rows, the share whose unseen sign matched a positive development sign, the median and the spread of
unseen-rate / development-rate, and the rows that passed. Its use: the minimum development effect SN449 should ask for.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE / "results-sn455.json"
H = "docs/SN_STRATEGY_HISTORY.md"
# (name, unit, dev value, dev length, length unit, [(unseen sample, value, length)], source)
ROWS = [
    ("WK-S weekly seller", "per lot", 314000, 4.4, "years", [("NIFTY Dec 2021-Mar 2022", -56743, 17 / 52), ("SENSEX Oct 2024-Apr 2026", -42022, 83 / 52)], f"{H}:39, :654"),
    ("WK-H hedged straddle", "per lot", 211957, 229 / 52, "years", [("NIFTY Oct 2020-Nov 2021 exam", 61511, 60 / 52), ("NIFTY Jan-Sep 2020 crash exam", 42570, 39 / 52)], f"{H}:742, :750, :996"),
    ("SN95-L cheap straddle", "rupees", 23518, 35, "trades", [("NIFTY 2022 exam", -4490, 10), ("EXAM-N", -17654, 19), ("EXAM-S", -8541, 21)], f"{H}:453, :616, :857"),
    ("SN171 HAR strangle", "rupees", 23087, 4, "years", [("NIFTY Apr-Dec 2022 exam", -1740, 0.75)], f"{H}:584, :616"),
    ("SN126-L hot-day burst", "rupees", 4414, 35, "trades", [("EXAM-N", 132, 12)], f"{H}:532, :912"),
    ("SN279 vote of seven signals", "rupees", 13988, None, None, [("EXAM-N", -11040, None), ("EXAM-S", -28680, None)], f"{H}:909"),
    ("SN272 pre-holiday calls (post hoc)", "rupees", 13331, None, None, [("EXAM-N", 25327, None), ("EXAM-S", 8884, None)], f"{H}:864"),
    ("Gold v5 (Rs 30k wallet)", "wallet", 850883, 4, "years", [("NIFTY 2022", -15281, 1)], f"{H}:1078"),
    ("N11 book", "wallet", 255365, 4, "years", [("NIFTY 2022", -14079, 1)], f"{H}:1078; memory fno-development-direction"),
    ("N10 retry", "wallet", 233275, 4, "years", [("NIFTY 2022", -3803, 1)], f"{H}:1078; memory fno-development-direction"),
    ("N08", "wallet", 202284, 4, "years", [("NIFTY 2022", -6874, 1)], f"{H}:1078; memory fno-development-direction"),
    ("SN78 1-second pick (TWAP)", "rupees", 15000, None, None, [("archive B Jul-Nov 2026", -28579, None)], f"{H}:261, :378"),
    ("E01.1 expiry book", "per lot", 12918, None, None, [("NIFTY 2024 expiries", -9012, None)], "memory expiry-day-paper-book; docs/research/simulation/2026-11-03-expiry-year"),
]


def main():
    if OUT.exists():
        raise SystemExit("SN455 is run once")
    out, ratios, kept, n = [], [], 0, 0
    for name, unit, dv, dl, lu, unseen, src in ROWS:
        dev_rate = dv / dl if dl else None
        for sample, uv, ul in unseen:
            n += 1
            k = (uv > 0) == (dv > 0)
            kept += k
            r = None
            if dev_rate and ul:
                r = (uv / ul) / dev_rate
                ratios.append(r)
            out.append({"rule": name, "unit": unit, "dev": dv, "dev_rate": None if dev_rate is None else round(dev_rate, 1), "rate_unit": lu,
                        "unseen_sample": sample, "unseen": uv, "unseen_rate": None if not ul else round(uv / ul, 1), "sign_kept": k,
                        "ratio": None if r is None else round(r, 3), "source": src})
    res = {"pairs": n, "rules": len(ROWS), "sign_kept": kept, "sign_kept_share": round(kept / n, 3),
           "ratio_n": len(ratios), "ratio_median": round(float(np.median(ratios)), 3), "ratio_mean": round(float(np.mean(ratios)), 3),
           "ratio_p25_p75": [round(float(np.percentile(ratios, 25)), 3), round(float(np.percentile(ratios, 75)), 3)],
           "share_ratio_above_0_5": round(float(np.mean([x > 0.5 for x in ratios])), 3),
           "rules_all_unseen_positive": [nm for nm, _u, _d, _l, _lu, us, _s in ROWS if all(v > 0 for _x, v, _y in us)],
           "rows": out}
    OUT.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1))
    for r in out:
        print(r["rule"], "|", r["unseen_sample"], r["dev_rate"], r["unseen_rate"], r["ratio"], r["sign_kept"])


if __name__ == "__main__":
    main()
