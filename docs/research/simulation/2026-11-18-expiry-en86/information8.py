"""EN86: canonical side information and synchronized receipt-time quote pilot."""
from collections import defaultdict
import numpy as np
import data8
from data8 import L7
import execution8,lab8,signals8

def strict_at(book,s):
    """Latest received state only: a newer invalid quote invalidates the old depth."""
    k=int(np.searchsorted(book.s,s,side='right'))-1
    if k<0:return None
    bp,ap=book.a['bp'][k,0],book.a['ap'][k,0]
    if book.e[k]>book.s[k]+1e-6 or s-book.e[k]>2 or not np.isfinite([bp,ap]).all():return None
    return k if 0<bp<ap and book.a['bq'][k,0]>0 and book.a['aq'][k,0]>0 else None

def canonical(book):
    out={}
    for setup in ('RAW','RESID','CONTRACT'):
        daily=[];events=[]
        for day_index,t in enumerate(book):
            cash=control=0.;n=0;alternatives=dict(price=0.,lag3=0.,unrelated20=0.,leave_traded_strike_out=0.)
            for i in np.flatnonzero(lab8.signals8(t,lab8.R8(setup8=setup))[0]):
                d=int(t.signals8[setup][i]);a=execution8.fixed_action(t,int(i),d)
                b=execution8.fixed_action(t,int(i),-d)
                if a['net'] is None or b['net'] is None:continue
                net=a['net'];rnd=.5*(net+b['net']);cash+=net;control+=rnd;n+=1
                scores=t.frame8['components'][:,0]
                price=np.sign(t.f[i,3]-t.f[i-15,3]) if i>=15 and np.isfinite(t.f[[i,i-15],3]).all() else 0
                lag3=np.sign(scores[i-3]) if i>=3 and np.isfinite(scores[i-3]) else 0
                unrelated=np.sign(book[day_index-20].frame8['components'][i,0]) if day_index>=20 else 0
                pairs=data8.basket(t,int(i))
                if 'j' in a:pairs=[(c,p) for c,p in pairs if t.strikes[c]!=t.strikes[a['j']]]
                leave=data8.components(t,int(i),pairs)[0]
                sides=dict(price=price,lag3=lag3,unrelated20=unrelated,leave_traded_strike_out=np.sign(leave) if np.isfinite(leave) else 0)
                for key,sign in sides.items():
                    if np.isfinite(sign) and sign:
                        action=execution8.fixed_action(t,int(i),int(sign));alternatives[key]+=action['net'] or 0.
                events.append(dict(day=t.day,i=int(i),d=d,net=net,random_expectation=rnd,
                                   status=a['status'],opposite_status=b['status'],control_sides=sides))
            daily.append(dict(day=t.day,net=round(cash,2),random_expectation=round(control,2),events=n,
                              controls={k:round(v,2) for k,v in alternatives.items()}))
        out[setup]=dict(days=daily,events=events,
                       note='independent one-lot hypothetical actions; overlapping events are not a funded portfolio')
    return out

def packet_pilot(day='2026-11-17'):
    import pk6
    packets=pk6.decode(day);idx,fut,opts=pk6.tokens(day)
    ib=pk6.Book(packets.pop(idx))
    fb=pk6.Book(packets.pop(fut['token']));books={key:pk6.Book(packets.pop(token)) for key,token in opts.items() if token in packets}
    packets.clear()
    strikes=sorted({k for k,_ in books});times=np.arange(45600.,52680.)
    base=np.full(len(times),np.nan);up=np.zeros(len(times),bool);down=up.copy();fmid=base.copy()
    counts=defaultdict(int)
    for n,s in enumerate(times):
        if 46800<=s<52200:counts['seconds']+=1
        kf=strict_at(fb,s)
        if kf is None:
            if 46800<=s<52200:counts['future_unavailable_seconds']+=1
            continue
        fm=fb.mid(kf);fmid[n]=fm;rows=[]
        for K in sorted(strikes,key=lambda k:abs(k-fm))[:5]:
            c,p=books.get((K,'CE')),books.get((K,'PE'))
            if c is None or p is None:continue
            kc,kp=strict_at(c,s),strict_at(p,s)
            if kc is None or kp is None:continue
            epochs=[c.e[kc],p.e[kp],fb.e[kf]]
            if max(epochs)-min(epochs)>1:counts['skew_rejected_pairs']+=1;continue
            lo=K+c.a['bp'][kc,0]-p.a['ap'][kp,0]
            hi=K+c.a['ap'][kc,0]-p.a['bp'][kp,0]
            rows.append((lo,hi))
        if len(rows)>=3:base[n]=np.median([(lo+hi)/2-fm for lo,hi in rows])
        if s<46800 or s>=52200:continue
        if len(rows)<3:continue
        counts['covered_seconds']+=1
        w=base[max(0,n-1200):n];w=w[np.isfinite(w)]
        if len(w)<600:continue
        med=np.median(w);mad=np.median(abs(w-med))
        up[n]=sum(lo-med>fb.a['ap'][kf,0]+mad for lo,hi in rows)>=3
        down[n]=sum(hi-med<fb.a['bp'][kf,0]-mad for lo,hi in rows)>=3
    events=[];last=-10**9
    for n in range(3,len(times)):
        if times[n]<46800 or times[n]>=52200:continue
        for flag,d in ((up,1),(down,-1)):
            if flag[n] and flag[n-1] and flag[n-2] and not flag[n-3]:
                e=dict(s=float(times[n]),d=d,nonoverlap=times[n]-last>=480)
                for h in (30,60,180,480):
                    k=strict_at(fb,times[n]+h)
                    e['dF'+str(h)]=float(d*(fb.mid(k)-fmid[n])) if k is not None else None
                    later=n+h
                    if later<len(base) and np.isfinite([base[later],base[n],fmid[later],fmid[n]]).all():
                        e['dGap'+str(h)]=float(d*(base[later]-base[n]))
                        e['dOptionImplied'+str(h)]=float(d*(base[later]+fmid[later]-base[n]-fmid[n]))
                    x0,x1=pk6._idx(ib,times[n]),pk6._idx(ib,times[n]+h)
                    e['dCash'+str(h)]=float(d*(x1-x0)) if np.isfinite([x0,x1]).all() else None
                if e['nonoverlap']:last=times[n]
                events.append(e)
    out=dict(day=day,counts=dict(counts),coverage=counts['covered_seconds']/max(1,counts['seconds']),events=events,
             qualified=False,reason='one recorded expiry; requires >=20 covered expiries and >=100 nonoverlapping events',
             assumptions='two-second quote age, <=one-second cross-leg exchange skew; r=0 over intraday expiry; rolling carry/basis removed')
    for label,xs in [('all',events),('nonoverlap',[e for e in events if e['nonoverlap']])]:
        out[label]={}
        for h in (30,60,180,480):
            values=[e['dF'+str(h)] for e in xs if e['dF'+str(h)] is not None]
            out[label][str(h)]=dict(n=len(values),mean=float(np.mean(values)) if values else None)
    return out

def diagnostics(book):
    events=[];oi=[]
    for t in book:
        C=t.frame8['components'];lag=t.frame8['lag_components'];w=signals8.window(t)
        valid=w&np.isfinite(C[:,0])&np.isfinite(lag[:,0])
        oi.append(dict(day=t.day,valid=int(valid.sum()),basket_sign_disagreements=int(np.sum(np.sign(C[valid,0])!=np.sign(lag[valid,0]))),
                       identity_max_error=float(np.nanmax(abs(C[:,0]-C[:,1]-C[:,2]))) if np.isfinite(C[:,0]).any() else None))
        for setup in ('RAW','RESID','CONTRACT'):
            for i in np.flatnonzero(t.signals8[setup]):
                d=int(t.signals8[setup][i]);row=dict(day=t.day,i=int(i),setup=setup,d=d)
                for h in (1,3,8,16,24,32):
                    if i+h<t.n and np.isfinite(t.f[[i,i+h],3]).all():row['dF'+str(h)]=float(d*(t.f[i+h,3]-t.f[i,3]))
                events.append(row)
    return dict(oi_baskets=oi,event_responses=events,canonical=canonical(book),
                source_status='UNVALIDATED: historical synthetic spreads; packet mechanism has one expiry only')
