"""Render results9.json + anatomy9.json into ANATOMY9-tables.md (reporting only; recomputes no verdict)."""
import json
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
R = json.loads((HERE / "results9.json").read_text(encoding="utf-8"))
A = json.loads((HERE / "anatomy9.json").read_text(encoding="utf-8"))
L = []; w = L.append
f0 = lambda x: "—" if x is None else f"{x:,.0f}" if isinstance(x, (int, float)) else str(x)
f1 = lambda x: "—" if x is None else f"{x:+,.1f}"


def table(head, rows):
    w("| " + " | ".join(head) + " |"); w("|" + "---|" * len(head))
    for r in rows:
        w("| " + " | ".join(f0(x) if not isinstance(x, str) else x for x in r) + " |")
    w("")


def st(settings):
    return ", ".join(f"{k}={v}" for k, v in settings.items()) or "—"


w("# Round 9 tables (rendered from results9.json / anatomy9.json by render9.py)\n")
w("Rupees after charges, today's lots. Independent sessions = ₹30,000 and the full day room every session; wallet = one continuous ₹30,000 "
  "own-cash wallet with brakes and sweep. Development screen on already studied sessions; inference descriptive only.\n")

w("## 1. Family verdicts\n")
rows = []
for fam, lab in R["labels"].items():
    s = R["stitched"][fam]
    rows.append([fam, lab["label"], R["families"][fam]["reference"], f"{R['families'][fam]['run_cells']}/{R['families'][fam]['cells']}",
                 lab["most_selected"] or "reference", lab["final_pick"] or "reference",
                 f"{f0(s['wallet_ordinary']['P'])} / {f0(s['wallet_adverse']['P'])}", f"{f0(s['reference_wallet_ordinary']['P'])} / {f0(s['reference_wallet_adverse']['P'])}",
                 f"{s['wallet_adverse']['halted']}", f"{f1(s['indep_adverse']['paired']['mean'])}", s["fallback_folds"],
                 f"{lab['grid_share_positive']:.0%}", f1(lab["grid_median_adverse_gain"])])
table(["family", "label", "reference", "cells run", "most selected", "final pick", "stitched wallet ord / adv", "reference stitched ord / adv",
       "adv halted days", "outer paired adv per session", "fallback folds", "grid cells beating ref (adv)", "grid median gain"], rows)
w("Champions: " + (json.dumps(R["champions"]) if R["champions"] else "none") + "\n")

for fam in R["labels"]:
    if fam == "EN105":
        continue
    w(f"## {fam}: full grid (NIFTY)\n")
    rows = []
    for key, c in R["configs"].items():
        cid, u = key.rsplit("|", 1)
        if u != "NIFTY" or c["family"] != fam:
            continue
        v = c.get("vs_reference", {}); tk = v.get("tickets", {}); pa = v.get("adverse", {})
        o, a = c["ordinary"], c["adverse"]
        rows.append([cid.split(":", 1)[1], st(c["settings"]) if c["kind"] == "CELL" else c["note"][:60], o["net"], a["net"], c["catastrophe"]["net"],
                     f"{o['trades']}/{o['traded_expiries']}", o["without_top2"], f"{f0(c['wallet']['ordinary']['P'])} / {f0(c['wallet']['adverse']['P'])}",
                     f"{c['wallet']['ordinary']['halted']}/{c['wallet']['adverse']['halted']}", c["wallet"]["ordinary"]["liq_dd"],
                     f"{f1(pa.get('mean'))} [{f1(pa.get('lo'))}, {f1(pa.get('hi'))}]" if pa else "—",
                     f"+{tk.get('candidate_only', 0)} ({f0(tk.get('candidate_only_net'))}) / −{tk.get('reference_only', 0)} ({f0(tk.get('reference_only_net'))}, {tk.get('reference_only_winners', 0)}W) / Δ{f0(tk.get('matched_net_delta'))}" if tk else "—",
                     c["hash"][:8]])
    table(["id", "settings", "ordinary", "adverse", "catastrophe", "parents / expiries", "without best two", "wallet ord / adv", "halted o/a",
           "liq dd", "paired adv per session [descr. 95%]", "vs ref: added (net) / removed (net, winners) / matched Δ", "ledger"], rows)
    by = R["stageb"]["selections"].get(fam, {})
    w(f"**Stage B {fam}:** " + "; ".join(f"{s}: {v['pick'] or 'reference (' + v['why']['reason'] + ')'}" for s, v in by.items()) + "\n")
    mx = R["families"][fam].get("maxt_uncalibrated") or {}
    if mx.get("best"):
        w(f"Uncalibrated family max-t (descriptive): best {mx['best']}, t {mx.get('t_best')}, family p {mx.get('p_family')}.\n")

w("## EN105: component combinations by boundary\n")
for s, v in A["en105"].items():
    w(f"**Boundary {s}.** Components: {json.dumps(v['components'])}. Pick: {v['pick'] or 'reference'} ({v['why']['reason']}).")
    ab = v["ablation"]
    w("- Single-gene mean change (inner adverse / outer adverse): " + "; ".join(f"{g}: {f1(x['inner_adverse_mean_change'])} / {f1(x['outer_adverse_mean_change'])} (identical pairs {x['identical_pairs']})"
                                                                             for g, x in ab.items() if g != "pair_interactions_inner_adverse"))
    w("- Pair interactions (inner adverse): " + "; ".join(f"{k} {f1(x)}" for k, x in ab["pair_interactions_inner_adverse"].items()))
    passed = [r for r in v["genotypes"] if r["passed"]]
    w(f"- Genotypes passing the constraints: {len(passed)}/64; distinct ledgers {len({r['hash'] for r in v['genotypes']})}.")
    if v["outer"]:
        best = sorted(v["outer"].items(), key=lambda x: -x[1]["adverse"])[:3]
        w(f"- Outer block adverse, genotype 000000: {f0(v['outer']['000000']['adverse'])}; top three: " + ", ".join(f"{g} {f0(x['adverse'])}" for g, x in best))
    w("")

w("## SENSEX (no Stage B: 63 sessions)\n")
rows = []
for key, c in R["configs"].items():
    cid, u = key.rsplit("|", 1)
    if u != "SENSEX":
        continue
    v = c.get("vs_reference", {}).get("adverse", {})
    rows.append([cid, st(c["settings"]) if c["kind"] == "CELL" else c["note"][:50], c["ordinary"]["net"], c["adverse"]["net"], f"{c['ordinary']['trades']}/{c['ordinary']['traded_expiries']}",
                 f"{f0(c['wallet']['ordinary']['P'])} / {f0(c['wallet']['adverse']['P'])}", f1(v.get("mean"))])
table(["id", "settings", "ordinary", "adverse", "parents / expiries", "wallet ord / adv", "paired adv vs E03_env"], rows)
w(f"DATA UNAVAILABLE on SENSEX: {len([k for k in R['unavailable'] if k.endswith('|SENSEX')])} OI-dependent cells (null money).\n")

w("## Diagnostics (descriptive)\n")
for k, v in R.get("diagnostics", {}).items():
    w(f"**{k}:** `{json.dumps(v)[:3000]}`\n")
w("## Arm and context logs (NIFTY, counts by status)\n")
for k, v in sorted(A["logs"].get("NIFTY", {}).items()):
    w(f"- {k}: {json.dumps(v)}")
w("")
w(f"Dedup: {json.dumps(R['dedup_counts'])}.\n")
(HERE / "ANATOMY9-tables.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("rendered", len(L), "lines")
