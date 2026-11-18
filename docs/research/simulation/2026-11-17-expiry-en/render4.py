"""Renders results4.json + anatomy4.json into ANATOMY4-tables.md (every number straight from the scored files)."""
from __future__ import annotations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
R = json.loads((HERE / "results4.json").read_text(encoding="utf-8"))
A = json.loads((HERE / "anatomy4.json").read_text(encoding="utf-8"))
DEV = ("2023", "2024", "2025"); X1 = ("N-X1", "S-X1"); X2 = ("N-X2", "S-X2"); ALL = ("N-ALL", "S-ALL")
SC = ("ordinary", "adverse", "catastrophe")


def rs(x):
    return "—" if x is None else f"{x:+,.0f}" if isinstance(x, (int, float)) else str(x)


def summary(s, books, ctl=None):
    out = ["| Book | Ordinary | Adverse | Severe | Without best day | Worst day | Tickets |" + (" E03.2 ordinary |" if ctl else ""),
           "|---|---:|---:|---:|---:|---:|---:|" + ("---:|" if ctl else "")]
    for b in books:
        o, a, c = s[f"{b}|ordinary"], s[f"{b}|adverse"], s[f"{b}|catastrophe"]
        out.append(f"| {b} | {rs(o['net'])} | {rs(a['net'])} | {rs(c['net'])} | {rs(o['without_best'])} | {rs(o['worst'])} | {o['trades']} |"
                   + (f" {rs(ctl[f'{b}|ordinary']['net'])} |" if ctl else ""))
    return out


def group(d, title):
    return f"*{title}:* " + "; ".join(f"{k or '-'} {v['tickets']}t {v['winners']}w {rs(v['net'])}" for k, v in d.items())


def book_lines(name, b):
    a = A[name][b]; vc = a["vs_control"]
    out = [f"**{b}**: {a['tickets']} tickets, {a['winners']} winners, {rs(a['net'])}.",
           "- " + group(a["by_side"], "side"), "- " + group(a["by_first_exit"], "first exit"), "- " + group(a["by_window"], "entry window")]
    if name != "E03.2 (control)":
        out.append(f"- *vs E03.2:* added {vc['added']} ({vc['added_winners']}w, {rs(vc['added_net'])}), removed {vc['removed']} "
                   f"({vc['removed_winners']}w, {rs(vc['removed_net'])}), changed {vc['changed']} ({vc['changed_better']} better, "
                   f"{vc['changed_worse']} worse, {rs(vc['changed_delta'])}).")
        if vc["biggest"]:
            out.append("- *biggest changes:* " + "; ".join(f"{z['day']} {z['side']} {rs(z['was'])} → {rs(z['now'])} ({z['now_path']})" for z in vc["biggest"]))
    out.append("- *best:* " + "; ".join(f"{z['day']} {z['side']} {rs(z['net'])} ({z['path']})" for z in a["best"]))
    out.append("- *worst:* " + "; ".join(f"{z['day']} {z['side']} {rs(z['net'])} ({z['path']})" for z in a["worst"]))
    return out


def arm(name, key=None):
    rec = R[key or name]; st = R["status"].get(key or name, rec.get("dev", {}).get("verdict"))
    out = [f"## {name} — {st}", ""]
    out += summary(rec["summary"], DEV + X1 + X2, R["E032"]); out.append("")
    if "dev" in rec and "checks" in rec["dev"]:
        bad = [k for k, v in rec["dev"]["checks"].items() if not v]
        out.append(f"Development verdict {rec['dev']['verdict']}; failed checks: {', '.join(bad) or 'none'}.")
    if "exam" in rec:
        for b in X1:
            e = rec["exam"][b]; bad = [k for k, v in e["checks"].items() if not v]
            out.append(f"Exam {b}: {e.get('verdict', 'diagnostic')}; failed checks: {', '.join(bad) or 'none'}.")
    if "evidence" in rec:
        out.append(f"Evidence: {json.dumps(rec['evidence'])}.")
    out.append("")
    for b in DEV + X1:
        out += book_lines(name, b); out.append("")
    return out


def main():
    L = ["# EN26–EN40 and the 2026 exam: tables (rendered from results4.json and anatomy4.json by render4.py)", "",
         "Rupees are net after fees on one Rs 25,000 book per year (development) or per exam book. t = tickets, w = winners.",
         "N-X1 = NIFTY Jan 6 – Sep 8 2026 (untouched), S-X1 = SENSEX Jul 29 2025 – Sep 3 2026 (untouched); X2 = partly seen.", "",
         f"Cohorts: {json.dumps(R['cohorts'])}", "", "## Status", "", "```json", json.dumps(R["status"], indent=1), "```", "",
         "## E03.2 (control)", ""]
    L += summary(R["E032"], DEV + X1 + X2 + ALL); L.append("")
    L.append(f"Unavailable decisions (coverage rule): {json.dumps(R['E032_unavailable'])}"); L.append("")
    for b in DEV + X1:
        L += book_lines("E03.2 (control)", b); L.append("")
    L += ["## E03.1", ""] + summary(R["E031"], DEV + X1 + X2, R["E032"]) + [""]
    L += ["## The E03-family exam (tests 7, 1, 5, 6)", "", "```json", json.dumps(R["family_exam"], indent=1), "```", ""]
    L += ["## Matched nulls (medians)", "", "```json", json.dumps(R["nulls"], indent=1), "```", ""]
    for name in ("EN26", "EN26_cat_diag", "EN11", "EN27", "EN21", "EN28", "EN28_opt_diag", "EN25", "EN29", "EN12", "EN12_full_sale_diag",
                 "EN30", "EN14", "EN14_immediate_diag", "EN31", "EN31_flip_diag", "EN32", "EN13", "EN35_diag", "EN36", "EN37", "EN38", "EN39", "EN40"):
        L += arm(name)
    L += ["## Slot diagnostics", "", "```json", json.dumps(R["diagnostics"], indent=1), "```", "",
          f"## EN33 cross-index lag — {R['EN33']['verdict']}", "", "```json", json.dumps(R["EN33"], indent=1), "```", "",
          f"## EN34 later expiry — {R['EN34']['verdict']}", "", "```json", json.dumps(R["EN34"], indent=1), "```", "",
          f"## Harness repair R1: EN16-R1 {R['EN16_R1']['verdict']}, EN18-R1 {R['EN18_R1']['verdict']}", "", "```json",
          json.dumps(dict(EN16_R1=R["EN16_R1"], EN18_R1=R["EN18_R1"]), indent=1), "```", "",
          f"## Risk dial K1 — recommended k {R['risk_dial']['recommended_k']}", "", "```json", json.dumps(R["risk_dial"], indent=1), "```", ""]
    (HERE / "ANATOMY4-tables.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("RENDERED", len(L), "lines")


if __name__ == "__main__":
    main()
