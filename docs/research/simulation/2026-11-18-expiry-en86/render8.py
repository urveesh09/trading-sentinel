"""Render the immutable round8 score into the shared anatomy convention."""
from pathlib import Path
from collections import defaultdict
import json
HERE=Path(__file__).resolve().parent
IDEAS={86:'Validate the received option-information lead',87:'OI at E03 entry clocks',88:'OI residual beyond price',89:'Pullback/reclaim with price ceiling',90:'OI contraction versus growth',91:'24-minute option-information hold',92:'One affordable higher-sensitivity contract',93:'Realized net-payoff model',94:'Information reversal exit',95:'Predetermined complete trader'}

def money(x):return f'{x:,.2f}'

def main():
    r=json.loads((HERE/'results8.json').read_text());a=json.loads((HERE/'anatomy8.json').read_text())
    table=['# Round 8 tables — EN86–EN95','',
           'All money is modeled research P&L after charges, present-policy lots/costs. All history is already studied. No qualification or deployment.','',
           '| Arm (NIFTY) | Ordinary | Adverse | Catastrophe | Trades | Worst expiry | Without best two | Ordinary wallet net | Wallet liquidation DD |',
           '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
    for key,out in r['arms'].items():
        if not key.endswith('|NIFTY'):continue
        m=out['ordinary'];table.append(f"| {key.split('|')[0]} | {money(m['net'])} | {money(out['adverse']['net'])} | {money(out['catastrophe']['net'])} | {m['trades']} | {money(m['worst'])} | {money(m['without_top2'])} | {money(out['wallet|ordinary']['P'])} | {money(out['wallet|ordinary']['liq_dd'])} |")
    lines=['# Round 8 anatomy — EN86–EN95','',
           'Developed and scored by Codex under PLAN8.md and freeze8.json. One fixed version per slot. No fresh historical holdout exists. These are development screens, not broker fills or proof of an edge.','',
           'Machine-readable evidence: results8.json, anatomy8.json, verification8.json. Full tables: ANATOMY8-tables.md. Source/runner corrections: ERRATUM8.md.','',
           '## Financial summary','',
           '| Slot | Ordinary / adverse, NIFTY | Status |','|---|---:|---|']
    for i in range(87,96):
        key=f'EN{i}|NIFTY';out=r['arms'][key]
        lines.append(f"| EN{i} | {money(out['ordinary']['net'])} / {money(out['adverse']['net'])} | {r['hypotheses'][key]['status']} |")
    lines+=['','SENSEX: DATA UNAVAILABLE for all nine new primaries because its stored OI is not supplied. Its baseline controls are reported separately in results8.json. No NIFTY positioning is substituted.','',
            'Independent-session sums and cash/brake-constrained wallets are different experiments. Do not add the shadow wallets together. No candidate is qualified while EN86 source validation remains incomplete.','',
            '## EN86 — source mechanism','']
    p=r['EN86'].get('packet_pilot',{})
    lines.append(f"Packet pilot: {p.get('day','not run')}, coverage {p.get('coverage',0):.1%}, {len(p.get('events',[]))} events. {p.get('reason','')}.")
    for key,v in r['EN86']['canonical'].items():
        totals=sum(x['net'] for x in v['days']);rnd=sum(x['random_expectation'] for x in v['days'])
        lines.append(f"- {key}: canonical one-lot fixed-hold net {money(totals)}, random-side expectation {money(rnd)}; {len(v['events'])} events. This is an overlapping-action diagnostic, not a funded book.")
    for i in range(87,96):
        name=f'EN{i}';key=name+'|NIFTY';out=r['arms'][key];m=out['ordinary'];h=r['hypotheses'][key]
        tickets=a['tickets'][key];side=defaultdict(float);reason=defaultdict(float)
        for t in tickets:side['CALL' if t['direction']>0 else 'PUT']+=t['net'];reason[t['first_exit']]+=t['net']
        years=', '.join(f'{y}: {money(v)}' for y,v in m['by_year'].items())
        lines+=['',f'## {name} — {IDEAS[i]}','',
                f"**{h['status']}.** {m['trades']} parents on {m['traded_expiries']} of {m['sessions']} expiries. Ordinary {money(m['net'])}; adverse {money(out['adverse']['net'])}; without its best two days {money(m['without_top2'])}.",
                '',f'By year: {years}.', '',
                'Where money came from: '+', '.join(f'{k} {money(v)}' for k,v in side.items())+'.',
                'By first exit: '+', '.join(f'{k} {money(v)}' for k,v in reason.items())+'.','',
                f"Versus matched E03: {h['statistics']['vs_control']['mean']:.2f} per expiry; 95% long-group interval [{h['statistics']['vs_control']['lo']}, {h['statistics']['vs_control']['hi']}]; Holm p {h['holm']:.4f}.",
                f"Changed opportunities: {h['affected']['changed_opportunities']} on {h['affected']['changed_expiries']} expiries. Matched-parent delta {money(h['affected']['matched_net_delta'])}; new-only net {money(h['affected']['candidate_only_net'])}; forgone control net {money(h['affected']['forgone_control_net'])}.",
                f"Wallet: net {money(out['wallet|ordinary']['P'])}, swept {money(out['wallet|ordinary']['swept'])}, trading cash {money(out['wallet|ordinary']['wallet'])}, liquidation DD {money(out['wallet|ordinary']['liq_dd'])}, first halt {out['wallet|ordinary']['first_halt']}."]
        if i==93:
            models=r['EN93']['models'];pred=r['EN93']['predictions'];sel=[x for x in pred if x['setup']=='PAYOFF' and x['selected']]
            lines+=['',f"Forecast support: {sum(x['eligible'] for x in models)} eligible model dates; {len(sel)} selected potential events. Startup and missing-input decisions remain explicit. Conservative scores are heuristic, not guaranteed bounds."]
        if i==95:
            lines+=['','Predetermined remove-one controls (not eligible replacement winners):']
            for k in ('EN95_noentry_ctl','EN95_nochooser_ctl','EN95_noexit_ctl'):
                v=r['arms'][k+'|NIFTY'];lines.append(f"- {k}: {money(v['ordinary']['net'])} / {money(v['adverse']['net'])} ordinary/adverse.")
    lines+=['','## Verification, limits and remaining work','',
            'Control parity, mechanics, causal prefixes, calibration, one-shot scoring, financial reconciliation and forward rehearsals have separate receipts. The final verification receipt states what actually ran; the full engine suite is not implied.',
            '', 'No downloads, broker orders, Telegram messages, scheduler change or Production edits. E03.2 and EN55 remain unchanged. All financial results are old-data research with modeled fills; the packet mechanism has one expiry and cannot establish a profitable lead. New prospective observations and the explicit dated calendar/snapshot workflow are still needed.']
    (HERE/'ANATOMY8.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    (HERE/'ANATOMY8-tables.md').write_text('\n'.join(table)+'\n',encoding='utf-8')
    print('ANATOMY8 rendered')

if __name__=='__main__':main()
