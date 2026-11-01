"""Independent past-label/sample/score audit; no choice or threshold changes."""
import json,math,statistics,sys
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import router_lab as X
import analyze_router as A


def run():
    ds=A.sessions();every=sorted(d for v in ds.values() for d in v)
    labels=sum((A.load(HERE/f'_local/training-records-{y}.json') for y in A.YEARS),[])
    checked=0;choices=0;largest_error=0.
    for y in A.YEARS:
        packet=A.load(HERE/f'_local/models-{y}.json')
        assert packet['session_index']=={d:i for i,d in enumerate(every) if d[:4]==y}
        for asof,m in packet['models'].items():
            checked+=1;dates=set([d for d in every if d<asof][-252:])
            sample=[r for r in labels if r['day'] in dates and r['exit_time'][:10]<asof]
            assert len(sample)==m['labels'] and len(dates)==m['past_sessions']
            assert max((r['exit_time'] for r in sample),default=None)==m['latest_label_exit']
            assert all(r['entry_time']<=r['exit_time'] and r['exit_time'][:10]<asof for r in sample)
            for cell,ranks in m['choices'].items():
                expected=[]
                for expert in X.R.EXPERTS:
                    global_=[r['net'] for r in sample if r['expert']==expert]
                    local=[r['net'] for r in sample if r['expert']==expert and r['cell']==cell]
                    if len(global_)<30 or len(local)<12:continue
                    mean=(sum(local)+12*statistics.fmean(global_))/(len(local)+12)
                    sd=statistics.stdev(local);score=mean-.5*sd/math.sqrt(len(local)+12)
                    if score>0:expected.append((expert,score,len(local),len(global_)))
                expected.sort(key=lambda r:(-r[1],X.R.EXPERTS.index(r[0])))
                assert [r[0] for r in expected]==[r['expert'] for r in ranks]
                for e,r in zip(expected,ranks):
                    error=abs(e[1]-r['score']);largest_error=max(largest_error,error);assert error<1e-8
                    assert e[2]==r['cell_trades'] and e[3]==r['global_trades'];choices+=1
    result={'monthly_models':checked,'positive_expert_cells_checked':choices,'counterfactual_labels':len(labels),'future_or_unclosed_labels_used':0,'independent_score_max_error':largest_error,'sample_and_ranking_mismatches':0}
    X.write(HERE/'training-crosschecks.json',result);print('TRAINING_VERIFIED',result,flush=True)


if __name__=='__main__':run()
