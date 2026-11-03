"""Audit fixed joint-fit candidate. Explicitly in-sample after failed exam."""
from dataclasses import asdict,replace
import json
import iterate as I
import data as D
import e02_lab as E
from audit import native_audit,fixed_entry_stress


def main():
    r=E.Rule(setup='PULLBACK',look=10,efficiency=.7,stretch=4.,premium_low=5.,premium_high=20.,option_rise=0.,
             stop=.4,arm=.4,keep=.6,target=1.,hold=8,start=780,end=900,slots=2,underlying_stop=2.,reach=1.)
    target=I.HERE/'candidate-audit.json';assert not target.exists()
    years={};checked=0;near=[]
    space={'efficiency':(.5,.6,.8),'stretch':(3.,5.),'premium_low':(3.,7.),'premium_high':(15.,25.),
           'stop':(.3,.5),'arm':(.25,.5),'keep':(.5,.7),'hold':(5,10,15),'start':(795,),
           'end':(870,915),'underlying_stop':(1.,3.),'reach':(.75,1.25,2.),'slots':(1,)}
    tapes={y:D.load_year(y,exam=y==2024) for y in (2024,2025)}
    for y,t in tapes.items():
        results={}
        for s in ('ordinary','adverse','catastrophe'):
            results[s]=I.run(t,r,s,True)
            checked+=sum(native_audit(day,r,row,s) for day,row in zip(t,results[s]['days']))
        results['fixed_entry_stress']=fixed_entry_stress(results['ordinary'])
        years[str(y)]=results
    for key,values in space.items():
        for v in values:
            spec=replace(r,**{key:v});row=dict(parameter=key,value=v,years={})
            for y,t in tapes.items():row['years'][str(y)]={s:I.run(t,spec,s)['summary'] for s in ('ordinary','adverse')}
            row['positive_all']=all(z['net']>0 for x in row['years'].values() for z in x.values())
            near.append(row)
    # Continuous own cash, no year boundary refill or reset.
    all_tapes=tapes[2024]+tapes[2025]
    continuous={s:I.run(all_tapes,r,s,True) for s in ('ordinary','adverse','catastrophe')}
    D.dump(target,dict(rule=asdict(r),years=years,continuous=continuous,native_positions_checked=checked,mismatches=0,
          neighbours=near,neighbour_positive_fraction=sum(n['positive_all'] for n in near)/len(near),
          per_year_checks={y:{s:E.qualifies(v['summary']) for s,v in row.items() if s in ('ordinary','adverse')} for y,row in years.items()},
          classification='RESEARCH_ONLY_JOINT_FIT; 2024/2025 both seen; original failed exam immutable; no fresh out-of-sample pass'))
    D.dump(I.HERE/'candidate.json',dict(version='expiry-e02-r3-v1',rule=asdict(r),max_lots=1,starting_cash=25000,daily_original_reserve=2500,
         eligibility='RESEARCH_ONLY: joint seen-year fit; future paired paper evidence required',forward_minimum=20,minimum_each_index=5,
         enable_nifty=False,enable_sensex=False))
    print('R3_AUDIT',checked,'positions, no mismatches; neighbours',sum(n['positive_all'] for n in near),'/',len(near))
    print('CONTINUOUS',{s:v['summary'] for s,v in continuous.items()})


if __name__=='__main__':main()
