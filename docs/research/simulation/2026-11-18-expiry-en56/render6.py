"""Renders ANATOMY6-tables.md from results6.json (no computation beyond formatting)."""
from __future__ import annotations
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
R = json.loads((HERE / "results6.json").read_text(encoding="utf-8"))
L = []
w = L.append


def rs(x):
    return "—" if x is None else f"{x:,.0f}" if isinstance(x, (int, float)) else str(x)


def pct(x):
    return "—" if x is None else f"{100 * x:.1f}%"


w("# EN56–EN70 tables (rendered from results6.json)\n")
w(f"Freeze head `{R['freeze_head'][:8]}`; sessions {R['sessions']}; evaluation starts {R.get('evaluation_from')}.\n")
w("## Verdicts\n")
w("| Slot | NIFTY | SENSEX |\n|---|---|---|")
for k in sorted(R["status"], key=lambda s: int(s[2:])):
    v = R["status"][k]
    w(f"| {k} | {v.get('NIFTY', v.get('ALL', '—'))} | {v.get('SENSEX', v.get('ALL', '—') if 'ALL' in v else '—')} |")
w("\n## The family test (18 hypotheses, Holm)\n")
w("| Hypothesis | support | affected parents / expiries | bootstrap p | Holm p |\n|---|---|---|---:|---:|")
for k, v in R["tests"].items():
    w(f"| {k} | {v['support']} | {v.get('affected', '—')} / {v.get('affected_expiries', '—')} | {v['p']} | {v['holm']} |")
w("\n## Every arm (fixed-cap net by fill level; wallet at ordinary fills)\n")
w("| Arm | Index | ordinary | adverse | severe | w/o top 2 | worst | parents | expiries | wallet P | swept | halted | first halt | liq. DD | worst marked |")
w("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|")
for name, v in R["arms"].items():
    for bk, a in v.items():
        o, ad, ca, wl = a["ordinary"], a["adverse"], a["catastrophe"], a["wallet|ordinary"]
        w(f"| {name} | {bk} | {rs(o['net'])} | {rs(ad['net'])} | {rs(ca['net'])} | {rs(o['without_top2'])} | {rs(o['worst'])} | {o['tickets']} | "
          f"{o['expiries']} | {rs(wl['P'])} | {rs(wl['swept'])} | {wl['halted']} | {wl['first_halt'] or 'never'} | {rs(wl['liq_dd'])} | {rs(o['worst_marked'])} |")
w("\n## Matched views used by the verdicts (evaluation sessions)\n")
w("| Hypothesis | arm ord. | ctl ord. | arm adv. | ctl adv. | arm worst | ctl worst | arm w/o top 2 | arm wallet / halt | ctl wallet / halt |")
w("|---|---:|---:|---:|---:|---:|---:|---:|---|---|")
for k, v in R["tests"].items():
    if "view" not in v:
        continue
    a, c = v["view"]["arm"], v["view"]["ctl"]
    w(f"| {k} | {rs(a['ordinary']['net'])} | {rs(c['ordinary']['net'])} | {rs(a['adverse']['net'])} | {rs(c['adverse']['net'])} | {rs(a['ordinary']['worst'])} | "
      f"{rs(c['ordinary']['worst'])} | {rs(a['ordinary']['without_top2'])} | {rs(a['wallet']['P'])} / {a['wallet']['first_halt'] or 'never'} | "
      f"{rs(c['wallet']['P'])} / {c['wallet']['first_halt'] or 'never'} |")
w("\n## Random-side nulls (40 seeds, same trigger times)\n")
w("| Slot | Index | primary (eval. sessions) | null median | null p10 | null p90 |\n|---|---|---:|---:|---:|---:|")
for slot, v in R["nulls"].items():
    for bk, n in v.items():
        t = R["tests"].get(f"{slot}|{bk}", {}).get("view", {}).get("arm", {}).get("ordinary", {}).get("net")
        w(f"| {slot} | {bk} | {rs(t)} | {rs(n['median'])} | {rs(n['p10'])} | {rs(n['p90'])} |")
w("\n## Where each arm won and lost (ordinary fixed-cap tickets)\n")
for name, v in R["arms"].items():
    for bk, a in v.items():
        tk = a.get("tickets", {})
        if not tk or not a["ordinary"]["tickets"]:
            continue
        fe = "; ".join(f"{k or '—'} {x['tickets']} ({x['winners']} won) {rs(x['net'])}" for k, x in tk["by_first_exit"].items())
        sd = "; ".join(f"{k} {x['tickets']} {rs(x['net'])}" for k, x in tk["by_side"].items())
        org = "; ".join(f"{k} {x['tickets']} {rs(x['net'])}" for k, x in tk["by_origin"].items())
        yr = "; ".join(f"{k} {rs(x)}" for k, x in a["ordinary"]["by_year"].items())
        w(f"- **{name} {bk}:** first exits: {fe}. Sides: {sd}. Origins: {org}. Years: {yr}.")
D = R["diagnostics"]
w("\n## EN56: the opportunity library\n")
for bk in ("NIFTY", "SENSEX"):
    e = D["EN56"][bk]
    w(f"### {bk} ({e['rows']:,} rows)\n")
    w("| Reserve · horizon · strike | decisions | filled | unaffordable | no fill | net / decision | net / fill | share > 0 | gross / fill | fees / fill | slippage / fill | no-spread net / fill | MAE | MFE | ever net-positive |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for k, c in e["cells"].items():
        R_, h, off = k.split("|"); lab = {"-1": "ITM1", "0": "ATM", "1": "OTM1", "2": "OTM2"}[off]
        w(f"| Rs {R_} · {h} min · {lab} | {c['decisions']} | {c['filled']} | {c['unaffordable']} | {c['nofill']} | {rs(c['net_per_decision'])} | {rs(c['net_per_fill'])} | "
          f"{pct(c['share_positive'])} | {rs(c['gross_per_fill'])} | {rs(c['fees_per_fill'])} | {rs(c['slip_per_fill'])} | {rs(c['nospread_per_fill'])} | {rs(c['mae'])} | {rs(c['mfe'])} | {pct(c['ever_positive'])} |")
    w("\n| Adverse fills: reserve · horizon · strike | net / fill | share > 0 |\n|---|---:|---:|")
    for k, c in e["cells_adverse"].items():
        R_, h, off = k.split("|"); lab = {"-1": "ITM1", "0": "ATM", "1": "OTM1", "2": "OTM2"}[off]
        w(f"| Rs {R_} · {h} · {lab} | {rs(c['net_per_fill'])} | {pct(c['share_positive'])} |")
    w("\n| Rs 2,500, bucket · horizon | fills | net / fill | share > 0 | calls | puts |\n|---|---:|---:|---:|---:|---:|")
    for k, c in e["buckets"].items():
        w(f"| {k.replace('|', ' · ')} min | {c['fills']} | {rs(c['net_per_fill'])} | {pct(c['share_positive'])} | {rs(c['calls'])} | {rs(c['puts'])} |")
    w("\n| 13:00–14:30, reserve · horizon | at E03.2's minutes and side (mean, n) | random side at those minutes | the 5-minute grid |\n|---|---|---|---|")
    for k, c in e["e03_minutes"].items():
        w(f"| Rs {k.replace('|', ' · ')} min | {c['e03']} | {c['random_side']} | {c['grid']} |")
    w("\n| Hindsight ceiling | expiries | best ≥ Rs 250 | best ≥ Rs 1,250 | best that first hit −35% | median best |\n|---|---:|---:|---:|---:|---:|")
    for k, c in e["ceiling"].items():
        w(f"| Rs {k} | {c['expiries']} | {c['best_ge_250']} | {c['best_ge_1250']} | {c['best_hit_stop_first']} | {rs(c['median_best'])} |")
    u = e["underlying"]
    w(f"\nUnderlying diagnostic (Rs 2,500, 8 min): {u['rows']} fills; direction right {pct(u['direction_right'])}; right but the option lost {pct(u['right_but_option_lost'])}; "
      f"wrong but the option won {pct(u['wrong_but_option_won'])}; delta-equivalent mean Rs {rs(u['delta_equiv_mean'])} against option net Rs {rs(u['option_net_mean'])}; "
      f"correlation {u['corr_delta_vs_net']}.\n")
if D.get("EN56_packets"):
    w("**EN56 on recorder depth, NIFTY Nov 17** (reserve · horizon: rows, packet net mean, bar-proxy net mean, packet − bar, correlation)\n")
    for k, c in D["EN56_packets"].items():
        w(f"- Rs {k.replace('|', ' · ')} min: {c['rows']} rows; packet {c['packet_net_mean']}; bar {c['bar_net_mean']}; difference {c['packet_minus_bar']}; corr {c['corr']}")
w("\n## EN57: what EN55's survival comes from\n")
for bk, e in D["EN57"].items():
    w(f"### {bk}\n")
    w(f"Main effects on fixed-cap ordinary net (mean over the four pairs): patient {rs(e['main_effect_patient'])}, scout {rs(e['main_effect_scout'])}, stall {rs(e['main_effect_stall'])}.\n")
    w("| Against E03.2 | matched | Δ on matched | of which size | exit / price | fees | new parents (net) | lost parents (net) |\n|---|---:|---:|---:|---:|---:|---|---|")
    for k, a in e["attribution"].items():
        w(f"| {k} | {a['matched']} | {rs(a['matched_delta'])} | {rs(a['size'])} | {rs(a['exit_price'])} | {rs(a['fees'])} | {a['new']} ({rs(a['new_net'])}) | {a['lost']} ({rs(a['lost_net'])}) |")
    w("\n| Run | fixed | wallet P | halted | first halt | liq. DD |\n|---|---:|---:|---:|---|---:|")
    for k, a in e["perturbations"].items():
        w(f"| {k} | {rs(a.get('fixed'))} | {rs(a['P'])} | {a['halted']} | {a['first_halt'] or 'never'} | {rs(a['liq_dd'])} |")
    w(f"\nHalt crossings against each base run: {e['halt_crossings']}. Wallet adverse − ordinary by factorial arm: {e['wallet_adverse_minus_ordinary']}.\n")
    if "heroes" in e:
        w(f"Hero days removed: {e['heroes']['days']}.\n")
        for k, a in e["heroes"]["runs"].items():
            w(f"- {k}: fixed {rs(a['fixed'])}; wallet {rs(a['P'])}, halted {a['halted']} (first {a['first_halt'] or 'never'})")
w("\n## EN58: entry policies on recorder depth (NIFTY Nov 17)\n")
e = D["EN58"]
w(f"EN55 intents: {e['intents']}. Verdict: {e['verdict']}.\n")
w("| Tag · policy · proxy | n | filled | how | cost vs mid | 8-min net (sum) | fill +60 s | fill +180 s | missed winner | decision mid +180 s (filled / unfilled) |")
w("|---|---:|---:|---|---:|---:|---:|---:|---:|---|")
for k, a in e["policies"].items():
    w(f"| {k.replace('|', ' · ')} | {a['n']} | {a['filled']} | {a['how']} | {pct(a['cost_vs_mid'])} | {rs(a['net_8min'])} | {pct(a['fill60'])} | {pct(a['fill180'])} | "
      f"{pct(a['missed_winner'])} | {pct(a['decision_mid180_filled'])} / {pct(a['decision_mid180_unfilled'])} |")
w("\n## EN61: the payoff model\n")
for bk, a in R["ml61"].items():
    w(f"- **{bk}:** {a}")
w("\n## EN66: one wallet for both indices\n")
e = D["EN66"]
w(f"Period {e['period']}, {e['sessions']} sessions.\n")
w("| Arm | fills | combined P | swept | halted | first halt | liq. DD | separate P (NIFTY + SENSEX) | parents / week | weeks won / lost / flat |\n|---|---|---:|---:|---:|---|---:|---:|---:|---|")
for name, v in e.items():
    if name in ("period", "sessions"):
        continue
    for sc, a in v.items():
        c = a["combined"]; lw = a["losing_weeks"]
        w(f"| {name} | {sc} | {rs(c['P'])} | {rs(c['swept'])} | {c['halted']} | {c['first_halt'] or 'never'} | {rs(c['liq_dd'])} | {rs(a['separate']['P'])} | "
          f"{a['parents_per_week']} | {lw['winning']} / {lw['losing']} / {lw['flat']} |")
w("\n## EN68: the probability of a halt (policy replay, circular blocks)\n")
w("| Arm | Book | paths × length (block) | P(halt) | P(year-end loss) | median | p5 | p95 | mean swept | liq. DD median / p95 |\n|---|---|---|---:|---:|---:|---:|---:|---:|---|")
for name, v in D["EN68"].items():
    for bk, a in v.items():
        w(f"| {name} | {bk} | {a['paths']} × {a['length']} ({a['block']}) | {pct(a['p_halt'])} | {pct(a['p_loss'])} | {rs(a['median'])} | {rs(a['p5'])} | {rs(a['p95'])} | "
          f"{rs(a['mean_swept'])} | {rs(a['liq_dd_median'])} / {rs(a['liq_dd_p95'])} |")
w("\n## EN69: why the puts earn\n")
for bk, v in D["EN69"].items():
    w(f"### {bk}\n")
    for name in ("E032_30k", "EN55"):
        for side, a in v[name].items():
            w(f"- **{name} {side}:** " + ", ".join(f"{k} {rs(x) if k != 'tickets' else x}" for k, x in a.items()))
    w("\n| Library (Rs 2,500, 8 min) | n | mean IV change | vol Rs / unit | underlying Rs / unit | time Rs / unit |\n|---|---:|---:|---:|---:|---:|")
    for k, a in v["library_iv"].items():
        w(f"| {k} | {a['n']} | {a['mean_d_iv']} | {a['vol_per_unit']} | {a['underlying_per_unit']} | {a['time_per_unit']} |")
w("\n## EN70: recorder minute bars\n")
e = D["EN70"]
w(f"Verdict: **{e['verdict']}**. Reasons: {e['reasons']}.\n\nParity: {e['parity']}.\n\nDecisions: {e['decisions']}.\n\nNov 17 ledgers (seen day): {e['nov17_ledgers']}.")
(HERE / "ANATOMY6-tables.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print("rendered", len(L), "lines")
