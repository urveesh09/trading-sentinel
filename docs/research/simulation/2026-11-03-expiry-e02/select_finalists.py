"""Pre-exam diagnosis, robustness and simple, explicitly named finalists."""
from dataclasses import asdict,replace
import json
import data as D
import e02_lab as E
from audit import evaluate_finalist


def main():
    tapes=D.load_year(2025)
    # Preserve two economically interpretable variants. Do not select a day,
    # month, strike or optimised condition tree. Optional reach/rise both off.
    core=E.Rule(setup='BREAK',look=10,efficiency=.5,stretch=4.,premium_low=10.,premium_high=20.,option_rise=0.,
                stop=.2,arm=1.,keep=.6,target=1.,hold=15,start=810,end=870,slots=1,underlying_stop=2.,reach=0.)
    runner=replace(core,target=2.,keep=.75)
    rules={'E02_CORE':core,'E02_RUNNER':runner}
    output={}
    neighbours={
      'look':(5,20),'efficiency':(.3,.7),'stretch':(2.5,3.5,4.5),
      'premium_low':(8.,12.),'premium_high':(15.,25.),'stop':(.15,.25,.3),
      'hold':(10,20,30),'start':(795,825),'end':(855,885),'underlying_stop':(1.,3.)}
    for name,rule in rules.items():
        result=evaluate_finalist(tapes,rule)
        near=[]
        for key,values in neighbours.items():
            for value in values:
                r=replace(rule,**{key:value})
                a=E.run_year(tapes,r)['summary'];b=E.run_year(tapes,r,'adverse')['summary']
                near.append(dict(parameter=key,value=value,ordinary=a,adverse=b,positive_both=a['net']>0 and b['net']>0))
        result['neighbours']=near
        result['neighbour_positive_fraction']=sum(x['positive_both'] for x in near)/len(near)
        result['lot_sensitivity']={}
        original_lot=E.LOT
        try:
            for lot in (25,50,75):
                E.LOT=lot
                result['lot_sensitivity'][str(lot)]={s:E.run_year(tapes,rule,s)['summary'] for s in ('ordinary','adverse')}
        finally:E.LOT=original_lot
        output[name]=result
        print('FINALIST_DEVELOPMENT',name,{s:v['summary']['net'] for s,v in result['results'].items()},'neighbours',result['neighbour_positive_fraction'],flush=True)
    wf={}
    for label,months in (('wf1',(7,8,9)),('wf2',(10,11,12))):
        trained=json.loads((D.HERE/f'round-{label}.json').read_text())
        best=E.Rule(**trained['leaders'][0]['rule'])
        held=[t for t in tapes if int(t.day[5:7]) in months]
        wf[label]=dict(rule=asdict(best),training_leader=trained['leaders'][0],held_months=months,
                       held={s:E.run_year(held,best,s,True) for s in ('ordinary','adverse')},
                       limitation='Fresh seeded fitting uses only prior months; family design and all 2025 market regimes were already seen, so diagnostic only')
        print('CHRONOLOGICAL_SELECTION',label,{s:v['summary']['net'] for s,v in wf[label]['held'].items()},flush=True)
    D.dump(D.HERE/'finalist-development.json',output)
    D.dump(D.HERE/'chronological-selection.json',wf)
    # Eligibility before any 2024 score. No rule can be added afterward.
    selected={}
    for name,r in rules.items():
        row=output[name]
        if all(all(E.qualifies(row['results'][s]['summary']).values()) for s in ('ordinary','adverse')) and row['neighbour_positive_fraction']>=.8 and row['results']['fixed_entry_stress']['summary']['without_best']>0:
            selected[name]=asdict(r)
    D.dump(D.HERE/'finalists.json',selected)
    print('FROZEN_CANDIDATE_SET',list(selected))


if __name__=='__main__':main()
