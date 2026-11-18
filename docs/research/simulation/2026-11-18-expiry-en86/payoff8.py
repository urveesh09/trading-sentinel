"""EN93: chronological real-lifecycle labels and net-return forecast, no option-pricing model."""
from dataclasses import replace
import numpy as np
import lab8
from signals8 import ridge_fit,predict,window
L7=lab8.L7; L4=L7.L4

def candidates(t):
    out=[];sp=L4.spec_of(t)
    for i in np.flatnonzero(lab8.signals8(t,lab8.ARMS['EN83'])[0]):
        d=int(t.signals8['RAW'][i]); S=t.frame8['components'][i,0]; innovation=t.frame8['innovation'][i]
        pick=L4.choose4(sp,t,int(i),d,lab8.ARMS['EN83'],2500.,30000.)
        if not pick or not np.isfinite([S,innovation]).all():continue
        j,n,lim=pick;cl=float(t.q[i,j,3]);ask=L4.ask_of(cl);bid=L4.bid_of(cl)
        reserve=L4.reserve(sp,lim,n);qty=n*sp.lot
        friction=(ask-bid)*qty+L4.fee(sp,ask,qty,True)+L4.fee(sp,bid,qty,False)
        out.append(dict(i=int(i),d=d,reserve=reserve,
                        x=np.array([d*S,d*innovation,friction/reserve,(t.minute[i]-780)/90.],float)))
    return out

def label(t,c,scenario='ordinary'):
    sig=np.zeros(t.n,np.int8);sig[c['i']]=c['d']
    r=replace(lab8.ARMS['EN83'],max_parents=1,max_intents=1)
    d=lab8.run_day8(t,r,scenario,30000.,2500.,True,direct=sig)
    return dict(y=d['net']/c['reserve'],net=d['net'],no_fill=not d['trades'],unresolved=d['unresolved'])

def prepare(book,labels=True):
    history=[];models=[];predictions=[]
    for t in book:
        rows=candidates(t)
        for key in ('PAYOFF','PAYOFF_ICPT','PAYOFF_NOINFO'):t.signals8[key]=np.zeros(t.n,np.int8)
        model_receipt=dict(day=t.day,eligible=False,reason='80 prior event-covered expiries required')
        if len(history)>=80:
            train=history[-80:-20];cal=history[-20:]
            n=sum(len(h['rows']) for h in train)
            if n>=100 and len(train)>=40 and len(cal)==20:
                model_receipt=dict(day=t.day,eligible=True,train_dates=[h['day'] for h in train],
                                   calibration_dates=[h['day'] for h in cal],training_rows=n)
                for key,cols,icpt in [('PAYOFF',[0,1,2,3],False),('PAYOFF_ICPT',[0,1,2,3],True),('PAYOFF_NOINFO',[2,3],False)]:
                    parts=[(np.array([r['x'][cols] for r in h['rows']]),np.array([r['y'] for r in h['rows']])) for h in train]
                    m=ridge_fit(parts,intercept_only=icpt)
                    errs=np.array([np.mean([r['y']-float(predict(m,r['x'][cols])) for r in h['rows']]) for h in cal])
                    correction=float(errs.mean()-1.645*errs.std(ddof=1)/np.sqrt(len(errs)))
                    model_receipt.setdefault('parameters',{})[key]=dict(mu=m['mu'].tolist(),sd=m['sd'].tolist(),beta=m['beta'].tolist(),
                        intercept=m['mean'],calibration_day_residuals=errs.tolist(),conservative_correction=correction)
                    for c in rows:
                        score=float(predict(m,c['x'][cols]))+correction
                        if score>0:t.signals8[key][c['i']]=c['d']
                        predictions.append(dict(day=t.day,setup=key,i=c['i'],forecast_return=float(predict(m,c['x'][cols])),
                                                conservative_return=score,reserve=c['reserve'],selected=score>0))
        models.append(model_receipt)
        # Label only after current predictions have been fixed. Outcomes enter future sessions only.
        if labels:
            for c in rows:c.update(label(t,c))
            if rows and np.mean(np.isfinite(t.frame8['components'][window(t),0]))>=.95:
                history.append(dict(day=t.day,rows=rows))
        t.payoff_rows8=rows
    labels_by={(t.day,c['i']):c for t in book for c in getattr(t,'payoff_rows8',[]) if 'y' in c}
    for r in predictions:
        c=labels_by.get((r['day'],r['i']))
        if c:r.update(actual_return=c['y'],actual_net=c['net'],no_fill=c['no_fill'])
    return dict(models=models,predictions=predictions,
                historical_labels=sum(len(t.payoff_rows8) for t in book),
                note='event-covered training dates selected on observable inputs, never future P&L; heuristic score')
