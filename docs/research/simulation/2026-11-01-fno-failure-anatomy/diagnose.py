"""N07 descriptive source-of-loss study; no candidate profit search."""
import json,sys,math
from collections import Counter,defaultdict
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=next(p for p in HERE.parents if (p/'python-engine').is_dir())
sys.path[:0]=[str(HERE),str(HERE.parent/'2026-11-01-fno-variant-selector')]
import variant_lab as N6
Y,B,C,X=N6.Y,N6.B,N6.C,N6.X
LOCAL=HERE/'_local';load=lambda p:json.loads(p.read_text())


def key(t):
    return tuple(t.get(k) for k in ('entry_time','tradingsymbol','direction','entry_premium','entry_underlying','entry_qty','initial_stop_underlying','initial_target_underlying','bar_ts','entry_expert'))


def summary(rows):
    losses=[t for t in rows if t['net_pnl']<0];wins=[t for t in rows if t['net_pnl']>0]
    fields={}
    for by in ('entry_expert','direction','origin','exit_reason'):
        groups={}
        for t in rows:
            group=groups.setdefault(t.get(by,'UNKNOWN'),dict(trades=0,wins=0,losses=0,net=0.,loss_net=0.,win_net=0.,gross=0.,costs=0.))
            net=t['net_pnl'];gross=(t['exit_premium']-t['entry_premium'])*t['entry_qty'];group['trades']+=1;group['wins']+=int(net>0);group['losses']+=int(net<0);group['net']+=net;group['loss_net']+=min(0.,net);group['win_net']+=max(0.,net);group['gross']+=gross;group['costs']+=gross-net
        fields[by]=groups
    return dict(trades=len(rows),losses=len(losses),wins=len(wins),net=math.fsum(t['net_pnl'] for t in rows),loss_net=math.fsum(t['net_pnl'] for t in losses),win_net=math.fsum(t['net_pnl'] for t in wins),groups=fields)


def run():
    allrows={y:{v:load(p)['trades'] for v,p in fs.items()} for y,fs in N6.reference_files().items()};totals={};pairs=[];selection=[];effects={};bindings={}
    for y,books in allrows.items():
        for variant in ('BASE','STALL30','STRUCT30'):
            totals[y+'|'+variant]=summary(books[variant])
        for candidate,base in [('STALL30','BASE'),('STRUCT30','STALL30')]:
            a={key(t):t for t in books[candidate]};b={key(t):t for t in books[base]};assert len(a)==len(books[candidate]) and len(b)==len(books[base])
            common=a.keys()&b.keys();paired=math.fsum(a[k]['net_pnl']-b[k]['net_pnl'] for k in common);extra=math.fsum(a[k]['net_pnl'] for k in a.keys()-b.keys());missing=math.fsum(b[k]['net_pnl'] for k in b.keys()-a.keys());total=totals[y+'|'+candidate]['net']-totals[y+'|'+base]['net'];assert abs(total-paired-extra+missing)<1e-7
            effects[y+'|'+candidate+'_vs_'+base]=dict(paired_delta=paired,unpaired_candidate_net=extra,unpaired_base_net=missing,total_delta=total,common=len(common),candidate_only=len(a.keys()-b.keys()),base_only=len(b.keys()-a.keys()))
            for k in sorted(common):
                a1,b1=a[k],b[k]
                if a1['net_pnl']==b1['net_pnl'] and a1['exit_time']==b1['exit_time']:continue
                pairs.append(dict(year=y,candidate=candidate,base=base,immutable_terms={n:a1[n] for n in ('entry_time','tradingsymbol','direction','entry_premium','entry_underlying','entry_qty','initial_stop_underlying','initial_target_underlying','entry_expert')},
                    candidate_admission=a1['admission_id'],base_admission=b1['admission_id'],known_at_candidate_exit=a1.get('n05_exit_context'),known_at_base_exit=b1.get('n05_exit_context'),
                    later_labels=dict(candidate_net=a1['net_pnl'],base_net=b1['net_pnl'],delta=a1['net_pnl']-b1['net_pnl'],candidate_exit=a1['exit_time'],base_exit=b1['exit_time'])))
        decisions=load(N6.LOCAL/f'decisions-{y}.json')['MAIN_ANCHOR'];models=load(N6.LOCAL/f'models-{y}.json')['MAIN_ANCHOR'];keys=load(N6.LOCAL/f'keys-candidate-{y}.json');rows=load(N6.LOCAL/'evals'/f'{keys["MAIN_ANCHOR"]}.json')['trades']
        for t in rows:
            if t['n06_variant']!='STALL30':continue
            day=t['entry_time'][:10];d=decisions[day];m=models[day];p=m['profiles']['STALL30'];assert d==t['n06_decision'] and p['eligible'] and m['latest_label_exit'][:10]<day
            selection.append(dict(year=y,admission_id=t['admission_id'],entry_time=t['entry_time'],expert=t['entry_expert'],direction=t['direction'],quantity=t['entry_qty'],
                known_before_day=dict(decision=d,stall_evidence=p,alternative_scores={v:r['score'] for v,r in m['profiles'].items()},cutoff=m['latest_label_exit']),
                later_labels=dict(net=t['net_pnl'],exit_reason=t['exit_reason'],exit_time=t['exit_time'])))
        for p in N6.reference_files()[y].values():bindings[p.relative_to(ROOT).as_posix()]=B.P.sha(p)
        for p in (N6.LOCAL/f'decisions-{y}.json',N6.LOCAL/f'models-{y}.json',N6.LOCAL/f'keys-candidate-{y}.json',N6.LOCAL/'evals'/f'{keys["MAIN_ANCHOR"]}.json'):
            bindings[p.relative_to(ROOT).as_posix()]=B.P.sha(p)
    out=dict(schema='n07_loss_anatomy_v1',status='DESCRIPTIVE_SEEN_DATA_NOT_CAUSAL_RETURN_PROOF',summaries=totals,exact_pair_effects=effects,changed_exit_pairs=pairs,selected_n04_trades=selection,input_eval_hashes=bindings,
             constraints='No future labels in earlier decision context; all member/direction losses retained; no candidate strategy scored here; selected N04 trades differ from fixed N04 counterfactual book.')
    X.write(HERE/'diagnosis.json',out)
    print('N04_VS_N03_PAIRS')
    for p in pairs:
        if p['candidate']=='STALL30':print(json.dumps(p))
    print('ALL_TRADE_SUMMARY',{k:{n:v[n] for n in ('trades','wins','losses','net')} for k,v in totals.items()})
    print('N04_SELECTOR_TRADES',dict(Counter((r['year'],'LOSS' if r['later_labels']['net']<0 else 'WIN') for r in selection)))


if __name__=='__main__':run()
