"""Renders results5.json + anatomy5.json into ANATOMY5-tables.md (every number straight from the scored files)."""
from __future__ import annotations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
R = json.loads((HERE / "results5.json").read_text(encoding="utf-8"))
A = json.loads((HERE / "anatomy5.json").read_text(encoding="utf-8"))
B = ("NIFTY", "SENSEX")


def rs(x):
    return "—" if x is None else f"{x:+,.0f}" if isinstance(x, (int, float)) else str(x)


def arm_table(name):
    s = R[name]["summary"]
    out = ["| Book | Ordinary | Adverse | Severe | Without top 2 | Worst expiry | Tickets / expiries | PF | Wallet (ordinary) | Swept | Halted |",
           "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for b in B:
        o, a, c, w = s[f"{b}|ordinary"], s[f"{b}|adverse"], s[f"{b}|catastrophe"], s[f"{b}|wallet_ordinary"]
        out.append(f"| {b} | {rs(o['net'])} | {rs(a['net'])} | {rs(c['net'])} | {rs(o['without_top2'])} | {rs(o['worst'])} | "
                   f"{o['tickets']} / {o['expiries']} | {o['profit_factor']} | {w['wallet']:,.0f} (P {rs(w['P'])}) | {w['swept']:,.0f} | {w['halted']} |")
    return out


def lines(name, b):
    a = A[name][b]; v = a["vs_control"]
    g = lambda d: "; ".join(f"{k or '-'} {x['tickets']}t {x['winners']}w {rs(x['net'])}" for k, x in d.items())  # noqa: E731
    return [f"**{b}**: {a['tickets']} tickets, {a['winners']} winners, {rs(a['net'])}. By year: {json.dumps(a['by_year'])}",
            f"- *side:* {g(a['by_side'])}", f"- *first exit:* {g(a['by_first_exit'])}", f"- *window:* {g(a['by_window'])}",
            f"- *vs control:* added {v['added']} ({rs(v['added_net'])}), removed {v['removed']} ({rs(v['removed_net'])}), changed {v['changed']} "
            f"({v['changed_better']} better, {v['changed_worse']} worse, {rs(v['changed_delta'])})",
            "- *best:* " + "; ".join(f"{z['day']} {z['side']} {rs(z['net'])} ({z['path']})" for z in a["best"]),
            "- *worst:* " + "; ".join(f"{z['day']} {z['side']} {rs(z['net'])} ({z['path']})" for z in a["worst"])]


def main():
    L = ["# EN41–EN55 tables (rendered from results5.json and anatomy5.json by render5.py)", "",
         "Fixed-cap: each expiry on its own (full day reserve, Rs 30,000 cash, no brakes). Wallet: one continuous Rs 30,000 book with brakes "
         "on the trading high-water and 50% profit sweeps (E032_25k: Rs 25,000, no sweeps). PF = profit factor of expiry results.", "",
         f"Sessions: {json.dumps(R['sessions'])}", "", "## Status", "", "```json", json.dumps(R["status"], indent=1), "```", "",
         "## Tests (one-sided sign-flip permutation, Holm across the ten primaries)", "", "```json", json.dumps(R["tests"], indent=1), "```", ""]
    order = ["E032_25k", "E032_30k", "E032_sym", "EN44", "EN44_now_diag", "EN44_noon_diag", "EN45", "EN45_now_diag", "EN46", "EN46_zero_diag",
             "EN36_sym_diag", "EN47", "EN47_native1_diag", "EN49", "EN49_icpt_diag", "EN49_trend_diag", "EN50", "EN50_3min_diag", "EN29_sym_diag",
             "EN51", "EN51_hold_diag", "EN52", "EN53", "EN54", "EN55"]
    for n in order:
        L += [f"## {n} — {R['status'].get(n, 'control / diagnostic')}", ""] + arm_table(n) + [""]
        rec = R[n]
        if "books" in rec:
            for b, x in rec["books"].items():
                bad = [k for k, v in x.get("checks", {}).items() if not v]
                L.append(f"{b}: {x['verdict']}; failed checks: {', '.join(bad) or 'none'}" + (f"; support {x['support']}" if "support" in x else ""))
            L.append("")
        for b in B:
            L += lines(n, b) + [""]
    L += ["## Capital (the three E03.2 controls and EN55 as continuous wallets)", "", "```json", json.dumps(R["capital"], indent=1), "```", "",
          "## Nulls", "", "```json", json.dumps(R["nulls"], indent=1), "```", "", "## Diagnostics", "", "```json",
          json.dumps(R["diagnostics"], indent=1), "```", "", "## Slots without data", "", "```json", json.dumps(R["no_data"], indent=1), "```", ""]
    (HERE / "ANATOMY5-tables.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("RENDERED", len(L))


if __name__ == "__main__":
    main()
