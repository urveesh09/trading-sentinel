"""SN457: what changed in the filing - the deterministic parser first, the model arm bounded (PLAN.md section 1, frozen at
83e1b444; details fixed here before any number; acquisition was a separate step: _local/filings, hashes below).

Documents (fetched once, Nov 17, generic clients):
  NSE   nsearchives .../corporate/ixbrl/INTEGRATED_FILING_BANKING_203710_23102026201332_iXBRL_WEB.html (the handoff's example).
        It is NSE's RENDERED web view of the integrated filing (label / value tables), not inline-XBRL tags, so the parser reads
        the rendered rows deterministically (tag-stripped, whitespace-normalised text, fixed row labels)
  SEC   sec.gov .../000119312526015872/d53025dex99.htm (HDFC Bank's filed exhibit, the handoff's December 2025 fixture)
Parser output: issuer, scope, rounding, reporting periods, board-meeting clock, the dissemination clock in the file name,
the four interest-earned components and their total, interest expenses, NII = total interest earned - interest expenses (lakhs
and crore), for the quarter and the year to date, and whether a year-ago column exists.
Fixture: the SEC exhibit's sentence "Net interest income ... grew by X% to Rs A billion from Rs B billion" against Rs 32,615.00
/ 30,653.25 crore (+6.40%) rounded to its precision; the consolidated Rs 41,245.52 crore is checked only if the exhibit states it.
Model arm: the session's model read the bounded text (the interest passages printed by the acquisition check) and wrote one
caveat with verbatim quotes (MODEL_ARM below, written before this script ran). Scored mechanically: each quote must occur in
the normalised document text. Latency is not meaningful for an in-session reader.
Forecast comparison: INSUFFICIENT (SN447's 8 reaction sessions are fixtures; no new session has accrued).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIL = HERE / "_local" / "filings"
OUT = HERE / "results-sn457.json"
NSE_FILE = "INTEGRATED_FILING_BANKING_203710_23102026201332_iXBRL_WEB.html"

MODEL_ARM = {
    "caveat": ("This filing is not comparable year over year on its own: it reports only the quarter 01-07-2026 to 30-09-2026 and "
               "the year to date from 01-04-2026, standalone, in lakhs, with no year-ago column, and one interest component is an "
               "unspecified 'Others'. A reported NII change needs the prior-year filing or a stated comparative."),
    "quotes": ["Date of start of reporting period 01-07-2026 01-04-2026",
               "Nature of report standalone or consolidated Standalone Standalone",
               "Others 17,265.00 55,251.00 Total interest earned 21,22,887.00 41,17,820.00"],
}


def norm(fn):
    s = (FIL / fn).read_text(encoding="utf-8", errors="replace")
    s = re.sub(r"<style.*?</style>|<script.*?</script>", " ", s, flags=re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s)))


def num(x):
    x = x.replace(",", "")
    return -float(x.strip("()")) if x.startswith("(") else float(x)


def two(t, label):
    m = re.search(re.escape(label) + r" (\(?[\d,]+\.\d+\)?) (\(?[\d,]+\.\d+\)?)", t)
    return (num(m.group(1)), num(m.group(2))) if m else (None, None)


def field(t, label, pat=r"([A-Za-z0-9 &\-]+?)"):
    m = re.search(re.escape(label) + r" " + pat + r"(?= [A-Z][a-z]| \d| \(|$)", t)
    return m.group(1).strip() if m else None


def main():
    if OUT.exists():
        raise SystemExit("SN457 is scored once")
    hashes = {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(FIL.iterdir()) if f.is_file()}
    t = norm("nse_banking_ixbrl.html")
    comp = {k: two(t, k) for k in ("Interest or discount on advances or bills", "Income on investments",
                                    "Interest on balances with reserve bank of India and other inter bank funds", "Others",
                                    "Total interest earned", "Interest expenses")}
    q_tot, y_tot = comp["Total interest earned"]
    q_exp, y_exp = comp["Interest expenses"]
    parts_q = sum(v[0] for k, v in comp.items() if k not in ("Total interest earned", "Interest expenses") and v[0] is not None)
    stamp = re.search(r"_(\d{14})_iXBRL", NSE_FILE).group(1)
    res = {"hashes": hashes,
           "nse": {"issuer": field(t, "Name of bank", r"([A-Z][A-Z &]+?)"), "nse_symbol": field(t, "NSE Symbol", r"([A-Z]+)"),
                   "scope": field(t, "Nature of report standalone or consolidated", r"(Standalone|Consolidated)"),
                   "rounding": field(t, "Level of rounding used in financial results", r"(Lakhs|Crores|Millions|Thousands)"),
                   "reporting_quarter": field(t, "Reporting Quarter", r"([A-Za-z]+ quarter)"),
                   "periods": re.findall(r"Date of (?:start|end) of reporting period (\d{2}-\d{2}-\d{4}) (\d{2}-\d{2}-\d{4})", t),
                   "board_meeting_end": field(t, "End date and time of board meeting", r"(\d{2}-\d{2}-\d{4} \d{2}:\d{2}:\d{2})"),
                   "dissemination_clock_from_file_name": dt.datetime.strptime(stamp, "%d%m%Y%H%M%S").isoformat(sep=" "),
                   "interest_components_lakhs": comp,
                   "components_sum_quarter_matches_total": None if q_tot is None else abs(parts_q - q_tot) < 0.5,
                   "nii_quarter_lakhs": None if q_tot is None or q_exp is None else q_tot - q_exp,
                   "nii_ytd_lakhs": None if y_tot is None or y_exp is None else y_tot - y_exp,
                   "year_ago_column": bool(re.search(r"Date of start of reporting period \d{2}-\d{2}-\d{4} \d{2}-\d{2}-\d{4} \d{2}-\d{2}-\d{4}", t))}}
    for k in ("nii_quarter_lakhs", "nii_ytd_lakhs"):
        if res["nse"][k] is not None:
            res["nse"][k.replace("lakhs", "crore")] = round(res["nse"][k] / 100, 2)
    h = norm("hdfc_sec_ex99.htm")
    m = re.search(r"Net interest income \(interest earned less interest expended\) for the quarter ended December 31, 2025 grew by "
                  r"([\d.]+)% to ₹ ([\d,.]+) billion from ₹ ([\d,.]+) billion", h)
    fx = {"sentence_found": bool(m)}
    if m:
        g, a, b = float(m.group(1)), num(m.group(2)), num(m.group(3))
        fx.update(growth_pct=g, now_bn=a, ago_bn=b, matches_32615=round(32615.00 / 100, 1) == round(a, 1),
                  matches_30653=round(30653.25 / 100, 1) == round(b, 1), matches_growth=round((32615.00 / 30653.25 - 1) * 100, 1) == g)
    fx["consolidated_41245_stated"] = ("41,245" in h) or ("412.5 billion" in h)
    res["hdfc_fixture"] = fx
    res["model_arm"] = {**MODEL_ARM, "quotes_verbatim": [q in t for q in MODEL_ARM["quotes"]],
                        "citation_correct": all(q in t for q in MODEL_ARM["quotes"]), "latency": "not meaningful (in-session reader)"}
    res["forecast_comparison"] = "INSUFFICIENT (SN447's 8 reaction sessions are development fixtures; no new session has accrued)"
    OUT.write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(res, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
