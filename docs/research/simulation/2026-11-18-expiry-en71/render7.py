"""Render results7.json + anatomy7.json into ANATOMY7-tables.md (reporting only; no recomputation of any verdict)."""
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
R = json.loads((HERE / "results7.json").read_text(encoding="utf-8"))
A = json.loads((HERE / "anatomy7.json").read_text(encoding="utf-8"))
L = []
w = L.append
rs = lambda x: "—" if x is None else (f"{x:,.0f}" if isinstance(x, (int, float)) else str(x))


def table(head, rows):
    w("| " + " | ".join(head) + " |"); w("|" + "---|" * len(head))
    for r in rows:
        w("| " + " | ".join(rs(x) if not isinstance(x, str) else x for x in r) + " |")
    w("")


w("# Round 7 tables (rendered from results7.json by render7.py)\n")
w("All rupees after charges, today's lots and charges, fixed-cap independent sessions unless marked wallet. Development screen on seen sessions.\n")

w("## 1. The 24 hypotheses (paired against E03_env, calendar-week blocks)\n")
rows = []
for h, v in R["hypotheses"].items():
    if "diff_per_session" not in v:
        rows.append([h, v["verdict"], "", "", "", "", "", "", "", ""]); continue
    slot, bk = h.split("|"); m = R["arms"][f"{slot}|{bk}"]["ordinary"]; ma = R["arms"][f"{slot}|{bk}"]["adverse"]
    c = R["arms"][f"E03_env|{bk}"]["ordinary"]
    nl = v.get("null"); st = v.get("stress", {})
    rows.append([h, v["verdict"], f"{m['net']:,.0f} / {ma['net']:,.0f}", f"{c['net']:,.0f}", f"{v['diff_per_session']:+.1f} [{v['ci'][0]:+.1f}, {v['ci'][1]:+.1f}]",
                 f"{v['p_vs_control']:.3f} / {v['holm']:.3f}", f"{m['tickets']} / {m['traded_expiries']}", f"{m['without_top2']:,.0f}",
                 "—" if not nl else f"{nl['median']:,.0f} / {nl['p90']:,.0f}",
                 "; ".join(f"{k} {x:,.0f}" for k, x in st.items()) or "—"])
table(["hypothesis", "verdict", "net ordinary / adverse", "E03_env net", "diff per session [95% block CI]", "p vs control / Holm", "parents / traded expiries",
       "net without best two", "random-side null median / p90", "stresses (net)"], rows)

for bk in ("NIFTY", "SENSEX"):
    w(f"## 2. Every arm, {bk}\n")
    rows = []
    for k, v in R["arms"].items():
        name, b = k.split("|")
        if b != bk or "catastrophe" not in v:
            continue
        o, a, c = v["ordinary"], v["adverse"], v["catastrophe"]; wo = v.get("wallet|ordinary", {}); wa = v.get("wallet|adverse", {})
        rows.append([name, o["net"], a["net"], c["net"], o["tickets"], o["traded_expiries"], o["worst"], o["without_top2"], o["fees"], o["minutes_in"],
                     f"{rs(wo.get('P'))} / {rs(wo.get('swept'))} / {rs(wo.get('combined'))}", f"{wo.get('halted')} {wo.get('first_halt') or ''}",
                     wo.get("liq_dd"), f"{rs(wa.get('P'))} / {wa.get('halted')}"])
    table(["arm", "ordinary", "adverse", "catastrophe", "parents", "traded expiries", "worst expiry", "without best two", "fees", "minutes in",
           "wallet P / swept / combined", "halted (first)", "liquidation dd", "adverse wallet P / halted"], rows)
    w(f"### By year, {bk} (ordinary net)\n")
    years = sorted({y for k, v in R["arms"].items() if k.endswith(bk) and "ordinary" in v for y in v["ordinary"].get("by_year", {})})
    rows = [[k.split("|")[0]] + [v["ordinary"]["by_year"].get(y) for y in years] for k, v in R["arms"].items()
            if k.endswith("|" + bk) and "by_year" in v.get("ordinary", {})]
    table(["arm"] + years, rows)

w("## 3. EN71: the frontier\n")
for bk in ("NIFTY", "SENSEX"):
    f = R["EN71"][bk]
    w(f"**{bk}.** Rows: {f['rows']}. Coverage at delay 0: {json.dumps(f['coverage'])}.")
    w(f"- Library reproduced: {json.dumps(f['library_reproduced'])}.")
    w(f"- E03's causal side, fixed 8-bar hold: accuracy {f['e03_forecast']['accuracy']:.1%} on {f['e03_forecast']['filled_signed']} signed decisions. Net per expiry {f['e03_side_fixed_hold']['mean_per_expiry']:+.1f} [{f['e03_side_fixed_hold']['lo']:+.1f}, {f['e03_side_fixed_hold']['hi']:+.1f}] against a random side {f['random_side_fixed_hold']['mean_per_expiry']:+.1f}.")
    w(f"- Ceilings, all untradeable:")
    w(f"  - C1 direction known: grid {f['C1_direction_known']['grid']['mean_per_expiry']:+.1f} per expiry over {f['C1_direction_known']['grid']['decisions']} decisions; E03 clocks {f['C1_direction_known']['e03']['mean_per_expiry']:+.1f}.")
    w(f"  - C2 best action at a fixed clock: {f['C2_best_action_fixed_clock_grid_chooser']['mean_per_expiry']:+.1f}.")
    w(f"- Oracle action on the grid, means per action: {json.dumps(f['oracle_grid_anatomy'])}.")
    w(f"- Harness: {json.dumps(f['harness'])}.\n")
    rows = []
    for clock in ("grid", "e03"):
        for dl in (0, 1, 2, 3):
            rows.append([f"{clock} d{dl}"] + [f"{f['frontier'][f'{clock}|d{dl}|p{p:.2f}']['per_decision']:+.1f}" for p in (.5, .55, .6, .7, .8, 1.)])
        rows.append([f"{clock} first p that pays"] + [json.dumps(f["frontier"][f"{clock}|first_p_paying"])] + [""] * 5)
    table(["clock / bar delay", "p .50", ".55", ".60", ".70", ".80", "1.00"], rows)
if "packet_pilot" in R["EN71"]:
    w("**Nov 17 packet pilot (one session, no verdict):** " + json.dumps(R["EN71"]["packet_pilot"]["latency"]) + "\n")

w("## 4. Mechanism diagnostics\n")
for bk, d in R["diagnostics"].items():
    w(f"**{bk}**\n")
    for k, v in d.items() if isinstance(d, dict) else []:
        w(f"- {k}: `{json.dumps(v)}`")
    w("")
for k in ("EN75_packet_pilot", "EN78_packet_pilot"):
    if k in R:
        w(f"- {k}: `{json.dumps({x: y for x, y in R[k].items() if x != 'examples'})}`")
w("")

w("## 5. EN79: the selector\n")
for bk, v in R["EN79"].items():
    w(f"**{bk}.**")
    w(f"- Chosen: {v['chosen']}. Best fixed expert: {v['best_fixed']}. Totals: {v['totals']}.")
    w(f"- Missed recovery winners: {v['missed_winner_count']}.")
    w(f"- Wallet: {v['wallet']}; adverse {v['wallet_adverse']}.\n")
    table(["ledger", "net", "parents", "traded expiries", "worst", "without best two"],
          [[k, m["net"], m["tickets"], m["traded_expiries"], m["worst"], m["without_top2"]] for k, m in v["controls"].items()])

w("## 6. EN80: the shared wallet (fixture)\n")
e = R["EN80"]
w(f"- Fixture: {e['fixture']} ({e['members_note']}).")
w(f"- Ordinary: {json.dumps(e['ordinary'])}.")
w(f"- Adverse: {json.dumps(e['adverse'])}.")
w(f"- Restart: {e['restart']}.\n")
table(["blocks", "ordinary halt share", "ordinary median P", "ordinary 5th pct P", "adverse halt share", "adverse median P"],
      [[b, s["ordinary"]["halt_share"], s["ordinary"]["median_P"], s["ordinary"]["p05_P"], s["adverse"]["halt_share"], s["adverse"]["median_P"]]
       for b, s in e["scenarios"]["scenarios"].items()])
w(e["scenarios"]["note"] + "\n")

w("## 7. Calibration of the test\n")
h = R["harness"]
w(f"- {h['pairs']} pairs of null random-entry controls. The test rejected at 0.05 {h['null_rejections_at_05']} times.")
w(f"- The 95% interval covered zero {h['ci_covers_zero_under_null']} times.")
w(f"- A planted +₹100 per traded session was detected {h['known_effect_detected_at_05']} times.\n")

w("## 8. EN85: expected forward expiries to the support floor (development activity; planning only)\n")
pw = R.get("EN85_power", {})
table(["arm", "parents per expiry", "traded share", "expiries to support", "reaches by 100"],
      [[k, f"{v['parents_per_expiry']:.3f}", f"{v['traded_share']:.3f}", "—" if v["expiries_to_support"] is None else f"{v['expiries_to_support']:.0f}", str(v["reaches_by_100"])] for k, v in pw.items()
       if k.split("|")[0] in ("E03_env", "EN55_env", "EN72", "EN73", "EN75", "EN76", "EN78", "EN81", "EN82", "EN83", "EN84", "E032_30k", "EN55")])

w("## 9. Tickets: by side and first exit (ordinary)\n")
for k, v in R["arms"].items():
    name = k.split("|")[0]
    if "tickets" not in v or name not in ("E03_env", "EN72", "EN73", "EN75", "EN76", "EN78", "EN81", "EN82", "EN83", "EN84"):
        continue
    t = v["tickets"]
    w(f"**{k}:** winners {t['winners']}.")
    w(f"- Side: {json.dumps(t['by_side'])}.")
    w(f"- First exit: {json.dumps(t['by_first_exit'])}.\n")
(HERE / "ANATOMY7-tables.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("rendered", len(L), "lines")
