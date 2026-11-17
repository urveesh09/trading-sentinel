"""Renders results3.json + anatomy3.json into ANATOMY3-tables.md (every number straight from the scored files)."""
from __future__ import annotations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
R = json.loads((HERE / "results3.json").read_text(encoding="utf-8"))
A = json.loads((HERE / "anatomy3.json").read_text(encoding="utf-8"))
Y = ("2023", "2024", "2025")


def rs(x):
    return "—" if x is None else f"{x:+,.0f}" if isinstance(x, (int, float)) else str(x)


def summary_table(s, ctl=None):
    out = ["| Year | Ordinary | Adverse | Severe | Without best day | Worst day | Tickets |" + (" E03.2 ordinary |" if ctl else ""),
           "|---|---:|---:|---:|---:|---:|---:|" + ("---:|" if ctl else "")]
    for y in Y:
        o, a, c = s[f"{y}|ordinary"], s[f"{y}|adverse"], s[f"{y}|catastrophe"]
        out.append(f"| {y} | {rs(o['net'])} | {rs(a['net'])} | {rs(c['net'])} | {rs(o['without_best'])} | {rs(o['worst'])} | {o['trades']} |"
                   + (f" {rs(ctl[f'{y}|ordinary']['net'])} |" if ctl else ""))
    tot = lambda k, sc: sum(s[f"{y}|{sc}"][k] for y in Y)
    out.append(f"| **Sum** | **{rs(tot('net', 'ordinary'))}** | **{rs(tot('net', 'adverse'))}** | **{rs(tot('net', 'catastrophe'))}** | | | {tot('trades', 'ordinary')} |"
               + (f" {rs(sum(ctl[f'{y}|ordinary']['net'] for y in Y))} |" if ctl else ""))
    return out


def group(d, title):
    rows = [f"*{title}:* " + "; ".join(f"{k} {v['tickets']}t {v['winners']}w {rs(v['net'])}" for k, v in d.items())]
    return rows


def arm(name):
    out = [f"## {name} — {R[name]['verdict']}", ""]
    s = R[name]["summary"]; out += summary_table(s, R["E032"]); out.append("")
    if "checks" in R[name]:
        bad = [k for k, v in R[name]["checks"].items() if not v]
        out.append(f"Checks failed: {', '.join(bad) if bad else 'none'}." + (f" Null median: {R[name]['null_median']}." if "null_median" in R[name] else ""))
        out.append("")
    for y in Y:
        a = A[name][y]; vc = a["vs_control"]
        out.append(f"**{y}** — {a['tickets']} tickets, {a['winners']} winners, {rs(a['net'])}.")
        out += ["- " + x for x in group(a["by_side"], "side") + group(a["by_first_exit"], "first exit") + group(a["by_window"], "entry window")
                + group(a["on_e032_days"], "days")]
        out.append(f"- *vs E03.2:* added {vc['added']} ({vc['added_winners']}w, {rs(vc['added_net'])}), removed {vc['removed']} "
                   f"({vc['removed_winners']}w, {rs(vc['removed_net'])}), changed {vc['changed']} ({vc['changed_better']} better, "
                   f"{vc['changed_worse']} worse, {rs(vc['changed_delta'])}).")
        if vc["biggest"]:
            out.append("- *biggest changes:* " + "; ".join(f"{b['day']} {b['side']} {rs(b['was'])} → {rs(b['now'])} ({b['now_path']})" for b in vc["biggest"]))
        out.append("- *best:* " + "; ".join(f"{b['day']} {b['side']} {rs(b['net'])} ({b['path']})" for b in a["best"]))
        out.append("- *worst:* " + "; ".join(f"{b['day']} {b['side']} {rs(b['net'])} ({b['path']})" for b in a["worst"]))
        out.append("")
    return out


def main():
    L = ["# EN11–EN25 tables (rendered from results3.json and anatomy3.json by render3.py)", "",
         "Rupees are the net after fees on one Rs 25,000 book per year (ordinary fills unless stated). "
         "t = tickets, w = winners.", "", "## E03.2 (control)", ""]
    L += summary_table(R["E032"]); L.append("")
    for name in ("EN11", "EN12", "EN12_full_sale_diag", "EN13", "EN14", "EN14_immediate_diag", "EN17", "EN19", "EN20", "EN20_no_retry_diag",
                 "EN21", "EN22", "EN23", "EN24", "EN25"):
        L += arm(name)
    L += ["## Slot diagnostics", "", "```json", json.dumps(R["diagnostics"], indent=1), "```", "",
          "## EN11 1-second measurement", "", "```json", json.dumps(R["EN11_seconds"], indent=1), "```", "",
          f"## EN15 breadth — {R['EN15']['verdict']}", "", "```json", json.dumps({k: v for k, v in R["EN15"].items()}, indent=1), "```", "",
          f"## EN16 next-expiry confirmation — {R['EN16']['verdict']}", "", "```json",
          json.dumps(R["recorded2026"]["EN16"]["groups"], indent=1), "```", "",
          f"## EN18 strike by real cost — {R['EN18']['verdict']}", "", "```json",
          json.dumps({k: v for k, v in R["recorded2026"]["EN18"].items() if k != "rows_sample"}, indent=1), "```", ""]
    (HERE / "ANATOMY3-tables.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("RENDERED", len(L), "lines")


if __name__ == "__main__":
    main()
