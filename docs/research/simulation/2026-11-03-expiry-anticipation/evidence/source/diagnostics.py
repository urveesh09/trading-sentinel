"""Fixed coarse risk/friction checks and complete factor descriptions; no selected new rule."""
from dataclasses import replace
import json,socket
def denied(*a,**k):raise AssertionError('Offline only')
socket.socket.connect=denied;socket.socket.connect_ex=denied;socket.create_connection=denied
import numpy as np
import guard as G
import risk_lab as R
import precursor as P
import forecast_study as F
import return_study as T
import smart_lab as S
import smart_study as SS
import anticipation_audit as A

def main():
    SS.verify();ts,x,ys,days,years,meta=T.load();all_tapes=ts[2024]+ts[2025]
    archive=json.loads((G.HERE/'forecast-results.json').read_text());controls={}
    for sc in F.SZ.SCENARIOS:
        old=archive['runs'][f'E031|matched_causal|{sc}'];new=P.run(all_tapes[13:],P.BASE,sc,True)
        assert old==new;controls[sc]=A.financial(old,all_tapes[13:],P.BASE)
    neighbours={}
    for allocation in ('scale','runner'):
        for extra in (.20,.30):
            rule=replace(R.BASE,allocation=allocation,extra=extra)
            for basis,tt in [('continuous',all_tapes),('2024',ts[2024]),('2025',ts[2025])]:
                for sc in F.SZ.SCENARIOS:
                    r=R.run(tt,rule,sc,True)
                    neighbours[f'{allocation}|{extra}|{basis}|{sc}']=dict(summary=r['summary'],audit=A.financial(r,tt,rule))
    SS.prepare();friction={};original=R.E.executable
    def extra_cost(t,i,j,side,scenario,lots):
        n,price=original(t,i,j,side,scenario,lots)
        if not n:return n,price
        price=R.E.up(price*1.01+.05) if side=='BUY' else R.E.down(price*.99-.05)
        return (n,price) if price>0 else (0,None)
    try:
        R.E.executable=extra_cost
        for name,rule,runner in [('E031',R.BASE,R.run),('SCALE25',R.ARMS['SCALE25'],R.run),
                                ('RUNNER25',R.ARMS['RUNNER25'],R.run),('SMART_RUNNER25',S.ARMS['SMART_RUNNER25'],S.run)]:
            for sc in F.SZ.SCENARIOS:
                r=runner(all_tapes,rule,sc,True);friction[f'{name}|{sc}']=dict(summary=r['summary'],audit=A.financial(r,all_tapes,rule))
    finally:R.E.executable=original
    original_size=json.loads((G.HERE/'size-results.json').read_text())['runs'];smart=json.loads((G.HERE/'smart-results.json').read_text())['runs']
    concentration={}
    for name,source in [('SCALE25',original_size),('RUNNER25',original_size),('CLOCK_RUNNER25',smart),('SMART_RUNNER25',smart)]:
        for sc in F.SZ.SCENARIOS:
            base=original_size[f'E031|continuous|{sc}'];new=source[f'{name}|continuous|{sc}'];delta=[a['net']-b['net'] for a,b in zip(new['days'],base['days'])]
            concentration[f'{name}|{sc}']=dict(increment=round(sum(delta),2),increment_without_best=round(sum(delta)-max(delta),2),
                increment_without_best_two=round(sum(delta)-sum(sorted(delta,reverse=True)[:2]),2),
                improved_days=sum(v>.01 for v in delta),worsened_days=sum(v<-.01 for v in delta),
                actual_reserve_ratio=sum(d['spent'] for d in new['days'])/sum(d['spent'] for d in base['days']) if sum(d['spent'] for d in base['days']) else None,
                changed=[dict(day=a['day'],increment=round(v,2)) for a,v in zip(new['days'],delta) if abs(v)>.01])
    # Describe all five predefined economic feature directions. No winner becomes an entry rule.
    z=np.load(G.LOCAL/'cases.npz');hits=z['y5'];features={}
    factor_specs={'option_momentum3':'high','relative_volume':'high','basis3':'high','oi_fraction5':'low','moneyness20':'low'}
    for train,test in ((2024,2025),(2025,2024)):
        a=years==train;b=years==test
        for name,direction in factor_specs.items():
            j=P.NAMES.index(name);fit=x[a,j];fit=fit[np.isfinite(fit)]
            threshold=float(np.quantile(fit,.8 if direction=='high' else .2));available=b&np.isfinite(x[:,j])
            selected=available&(x[:,j]>threshold if direction=='high' else x[:,j]<threshold)
            features[f'{name}|train{train}|test{test}']=dict(direction=direction,training_feature_threshold=threshold,
               rows=int(selected.sum()),expiry_days=len(set(days[selected])),hero_hits=int(hits[selected].sum()),
               hero_fraction=float(hits[selected].mean()) if selected.any() else None,
               mean_bounded_adverse_return=float(ys[5][selected].mean()) if selected.any() else None,
               population_hero_fraction=float(hits[b].mean()),
               caveat='Descriptive overlapping examples, fixed feature-only quantiles; neither independent evidence nor summed portfolio PnL')
    G.save('diagnostics.json',dict(matched_control_native_audit=controls,coarse_budget_neighbours=neighbours,
       fixed_one_percent_plus_tick=friction,concentration=concentration,factor_descriptions=features,
       no_new_strategy_selected=True))
    print('DIAGNOSTICS_COMPLETE',len(neighbours),'risk-neighbour runs,',len(friction),'friction runs; no optimum selected',flush=True)
    print('FACTORS',json.dumps(features),flush=True)

if __name__=='__main__':main()
