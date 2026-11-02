"""All-trade failure/benefit attribution and causal selector receipts."""
import json,math,sys
from collections import Counter,defaultdict
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path[:0]=[str(HERE),str(HERE.parent/'2026-11-01-fno-variant-selector')]
import variant_lab as V
load=lambda p:json.loads(p.read_text())


def run():
    d=load(HERE/'diagnosis.json');out={};costs=[]
    for y,files in V.reference_files().items():
        for v in ('STALL30','STRUCT30'):
            rows=load(files[v])['trades'];cash=peak=250000.;peak_at=y+'-01-01';worst={};worst_pct=0.;member_net={m:math.fsum(t['net_pnl'] for t in rows if t['entry_expert']==m) for m in ('SHIPPED','OR20','EFF','TPB')}
            for t in sorted(rows,key=lambda t:(t['exit_time'],t['entry_time'])):
                cash+=t['net_pnl']
                if cash>=peak:peak=cash;peak_at=t['exit_time']
                dd=(peak-cash)/peak
                if dd>worst_pct:worst_pct=dd;worst=dict(peak_at=peak_at,trough_at=t['exit_time'],fall_rs=peak-cash,fall_pct=dd,peak_equity=peak)
            loss=[t for t in rows if t['net_pnl']<0];small_gross_positive=[t for t in loss if t['exit_premium']>t['entry_premium']]
            out[y+'|'+v]=dict(member_net=member_net,losing_trades=len(loss),gross_positive_net_losses=len(small_gross_positive),gross_positive_loss_net=math.fsum(t['net_pnl'] for t in small_gross_positive),worst_closed_drawdown=worst)
        for p in d['changed_exit_pairs']:
            if p['year']!=y or p['candidate']!='STALL30':continue
            terms=p['immutable_terms'];c=p['known_at_candidate_exit'];lots=terms['entry_qty']//65;gross=(c['bid']-terms['entry_premium'])*terms['entry_qty'];stress=(200+5*lots)*lots
            fees=V.P.P.E.calc_fno_costs(terms['entry_premium'],c['bid'],terms['entry_qty'])
            assert abs(gross-fees-stress-c['net_at_bid_after_cost'])<1e-7
            costs.append(dict(year=y,entry_time=terms['entry_time'],gross=gross,estimated_fees=fees,synthetic_stress=stress,net_before_stress=gross-fees,net_after_stress=gross-fees-stress,
                              later_paired_effect=p['later_labels']['delta'],not_known_then=True))
    switch={}
    for y in ('2024','2025','2026'):
        rows=[r for r in d['selected_n04_trades'] if r['year']==y];profits=[r for r in rows if r['later_labels']['net']>0];losses=[r for r in rows if r['later_labels']['net']<0]
        for r in rows:
            known=r['known_before_day'];assert known['stall_evidence']['eligible'] and known['cutoff'][:10]<r['entry_time'][:10]
            assert known['decision']['consecutive_days']>=2
        switch[y]=dict(trades=len(rows),wins=len(profits),losses=len(losses),net=math.fsum(r['later_labels']['net'] for r in rows),
                       loss_net=math.fsum(r['later_labels']['net'] for r in losses),by_member={m:dict(trades=sum(r['expert']==m for r in rows),net=math.fsum(r['later_labels']['net'] for r in rows if r['expert']==m)) for m in ('SHIPPED','OR20','EFF','TPB')},
                       worst_cases=sorted(losses,key=lambda r:r['later_labels']['net'])[:3])
    anatomy=[]
    for y in ('2024','2025','2026'):
        rs=load(HERE/f'path-anatomy-{y}.json')['records'];losers=[r for r in rs if r['later_labels']['net']<0]
        anatomy.append(dict(year=y,losing_count=len(losers),previously_net_positive_losers=sum(r['later_labels']['best_observed_held_net']>0 for r in losers),
            never_observed_net_positive_losers=sum(r['later_labels']['best_observed_held_net']<=0 for r in losers),
            note='Observed held snapshots only; later profitable counterfactuals are labels, no ability to sell at an unobserved perfect peak.'))
    result=dict(all_trade_diagnostics=out,early_cut_cost_decomposition=costs,selected_n04_switches=switch,path_loss_anatomy=anatomy,
                attribution='Same admitted entry economic pairs only; reference-book switch receipts and later labels are separate; positive past score is not proof next trade wins.',diagnostic_errors=0)
    V.X.write(HERE/'failure-explanation.json',result)
    print('FAILURE_EXPLANATION',out,'SWITCHES',{y:{k:v for k,v in s.items() if k not in ('worst_cases','by_member')} for y,s in switch.items()},flush=True)


if __name__=='__main__':run()
