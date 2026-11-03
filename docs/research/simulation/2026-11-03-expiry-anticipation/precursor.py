"""Causal large-move features, isolated executable labels and fixed logistic forecasts."""
from dataclasses import dataclass,asdict,replace
import math
import numpy as np
import risk_lab as R
E,X,D,L=R.E,R.X,R.D,R.L
LOT,PARTIAL=R.LOT,R.PARTIAL
stalled,timed_out,recover_lots=L.stalled,L.timed_out,X.recover_lots

@dataclass(frozen=True)
class ForecastRule(R.RiskRule):
    predictor:str='baseline'
    multiple:float=2.

BASE=ForecastRule(**asdict(R.BASE))
def forecast_rule(m):
    return replace(BASE,predictor='forecast',multiple=float(m),max_lots=1,target=float(m-1),
        stop=.35,arm=999.,lock_arm=0.,runner_keep=0.,split=False,hold=20)

NAMES=('spot3','spot10','future3','basis3','efficiency10','option_momentum3','option_acceleration',
       'relative_volume','oi_fraction5','moneyness20','minutes_left','fees_fraction','synthetic_basis',
       'noise_ratio','log_premium','direction')

def feature(t,i,j,d):
    """Never accesses beyond i. Missing optional inputs stay explicitly missing."""
    if i<30:return None
    atr=float(t.features[10][i,4]);s=t.close;f=t.f[:,3];q=t.q[:,j]
    if not np.isfinite([atr,s[i],s[i-3],s[i-10],f[i],f[i-3]]).all() or atr<=0:return None
    price=float(q[i,3]);old=float(q[i-3,3]);older=float(q[i-6,3])
    momentum=math.log(price/old) if min(price,old)>0 else np.nan
    accel=momentum-math.log(old/older) if np.isfinite(momentum) and older>0 else np.nan
    recent=q[i-2:i+1,4];prior=q[i-22:i-2,4]
    volume=math.log((float(np.sum(recent))+1)/(3*float(np.median(prior))+1)) if np.isfinite(recent).all() and np.isfinite(prior).all() else np.nan
    oi=getattr(t,'oi',None);change=np.nan
    if oi is not None and np.isfinite([oi[i,j],oi[i-5,j]]).all() and oi[i-5,j]>0:
        change=float(np.clip((oi[i,j]-oi[i-5,j])/oi[i-5,j],-1,1))
    ask=E.up(price+E.half(price));bid=E.down(price-E.half(price))
    fees=(E.fee(ask,LOT,True)+E.fee(bid,LOT,False))/(ask*LOT)
    other=np.flatnonzero((t.strikes==t.strikes[j])&(t.kinds==-d));synthetic=np.nan
    if len(other)==1:
        p=float(t.q[i,int(other[0]),3]);v=float(t.q[i,int(other[0]),4])
        if np.isfinite(p) and p>0 and np.isfinite(v) and v>0:synthetic=d*(float(t.strikes[j])+d*(price-p)-s[i])/atr
    returns=np.diff(s[i-20:i+1]);noise=np.nan
    if np.isfinite(returns).all() and np.std(returns)>0:noise=float(np.std(returns[-3:])/np.std(returns))
    return np.array([d*(s[i]-s[i-3])/atr,d*(s[i]-s[i-10])/atr,d*(f[i]-f[i-3])/atr,
       d*((f[i]-s[i])-(f[i-3]-s[i-3]))/atr,d*t.features[10][i,2],momentum,accel,volume,change,
       d*(t.strikes[j]-s[i])/(atr*math.sqrt(20)),(930-t.minute[i])/150,fees,synthetic,noise,math.log(price),d],float)

def label(t,i,j,d,limit,multiple):
    """One possible one-lot experiment. A TARGET is an actual later open sale, not MFE."""
    n,entry=E.executable(t,i+1,j,'BUY','adverse',1)
    if not n or entry>limit or E.reserve(entry,1)>1250.01:return dict(hit=0,status='NO_ENTRY',net=0.,entry_i=None,exit_i=None)
    cost=E.fee(entry,LOT,True);underlying=t.close[i]-d*t.features[10][i,4]*2;stop=round(entry*.65,2)
    pending=None
    for k in range(i+1,t.n):
        if pending:
            n,price=E.executable(t,k,j,'SELL','adverse',1)
            if n:
                return dict(hit=int(pending=='TARGET'),status=pending,net=round((price-entry)*LOT-cost-E.fee(price,LOT,False),2),entry_i=i+1,exit_i=k)
            continue
        row=t.q[k,j]
        bid=E.down(float(row[3])-E.half(float(row[3]))) if np.isfinite(row[3]) and np.isfinite(row[4]) and row[4]*.2>=LOT else None
        if t.minute[k]>=928:pending='FLAT_TIME'
        elif bid is not None and bid>0:
            if bid<=stop:pending='STOP'
            elif np.isfinite(t.close[k]) and d*(t.close[k]-underlying)<0:pending='STRUCTURE'
            elif bid>=entry*multiple:pending='TARGET'
            elif k-(i+1)>=20:pending='TIME'
    return dict(hit=0,status='UNRESOLVED',net=round(-entry*LOT-cost,2),entry_i=i+1,exit_i=None)

def sigmoid(z):return 1/(1+np.exp(-np.clip(z,-40,40)))

def transform(x,impute,mean,scale):
    missing=~np.isfinite(x);filled=np.where(missing,impute,x)
    return np.column_stack([np.ones(len(x)),np.clip((filled-mean)/scale,-5,5),missing.astype(float)])

def fit(x,y,days):
    """One independent day of weight per expiry; all preprocessing fitted here only."""
    _,inverse,counts=np.unique(days,return_inverse=True,return_counts=True)
    weight=1./counts[inverse]
    impute=np.array([np.median(x[np.isfinite(x[:,j]),j]) if np.isfinite(x[:,j]).any() else 0. for j in range(x.shape[1])])
    filled=np.where(np.isfinite(x),x,impute);mean=np.average(filled,axis=0,weights=weight)
    scale=np.sqrt(np.average((filled-mean)**2,axis=0,weights=weight));scale=np.where(scale<1e-8,1.,scale)
    z=transform(x,impute,mean,scale);b=np.zeros(z.shape[1]);p=(np.sum(weight*y)+.5)/(weight.sum()+1)
    b[0]=math.log(p/(1-p));penalty=np.ones(len(b));penalty[0]=1e-8
    def objective(beta):
        v=z@beta
        return float(np.sum(weight*(np.logaddexp(0,v)-y*v))+.5*np.sum(penalty*beta*beta))
    iterations=0
    for it in range(60):
        p=sigmoid(z@b);g=z.T@(weight*(p-y))+penalty*b
        h=z.T@((weight*p*(1-p))[:,None]*z)+np.diag(penalty)
        step=np.linalg.solve(h,g);value=objective(b);a=1.
        while a>1e-7 and objective(b-a*step)>value-1e-4*a*float(g@step):a*=.5
        b-=a*step;iterations=it+1
        if np.max(np.abs(a*step))<1e-7:break
    return dict(impute=impute.tolist(),mean=mean.tolist(),scale=scale.tolist(),coefficients=b.tolist(),
        iterations=iterations,training_rows=len(x),training_days=len(counts),training_day_weight=float(weight.sum()),
        training_hit_rate=float(np.sum(weight*y)/weight.sum()),penalty=1.)

def predict(model,x):
    return sigmoid(transform(x,np.array(model['impute']),np.array(model['mean']),np.array(model['scale']))@np.array(model['coefficients']))

def hurdle(t,i,j,multiple):
    raw=float(t.q[i,j,3]);ask=E.up(raw+E.half(raw))
    fraction=(E.fee(ask,LOT,True)+E.fee(ask*multiple,LOT,False))/(ask*LOT)
    return (1+fraction)/multiple

# Each run activates a frozen trained model's current-row scores only. No future ranking.
ACTIVE={}
def directions(t,rule):
    if rule.predictor=='baseline':return L.directions(t,rule)
    out=np.zeros(t.n,dtype=np.int8)
    for i,(j,d,p) in ACTIVE.get(t.day,{}).items():
        if p>hurdle(t,i,j,rule.multiple):out[i]=d
    return out

def choose(t,i,d,rule,budget,cash):
    if rule.predictor=='baseline':return R.choose(t,i,d,rule,budget,cash)
    row=ACTIVE.get(t.day,{}).get(i)
    if not row:return None
    j,sign,p=row
    if sign!=d:return None
    return R.resize(t,i,j,1,budget,cash,.10)

def activate(meta,probability,multiple):
    """Compare only the two CURRENT directions; never the best future minute/day."""
    global ACTIVE
    ACTIVE={}
    for row,p in zip(meta,probability):
        day=row['day'];i=row['i'];surplus=float(p)*multiple-(1+row[f'fees{multiple}'])
        old=ACTIVE.setdefault(day,{}).get(i)
        if old is None or surplus>old[2]*multiple-(1+old[3]):
            ACTIVE[day][i]=(row['j'],row['direction'],float(p),row[f'fees{multiple}'])
    ACTIVE={day:{i:v[:3] for i,v in rows.items()} for day,rows in ACTIVE.items()}

def run(tapes,rule=BASE,scenario='ordinary',details=False):
    from precursor_day import run_day
    cash=peak=E.START_CASH;days=[]
    for t in tapes:
        dd=peak-cash;scale=0. if dd>=4000 else .25 if dd>=3000 else .5 if dd>=1500 else 1.
        row=run_day(t,rule,scenario,cash,min(E.BUDGET*scale,cash),details)
        cash=round(cash+row['net'],2);peak=max(peak,cash);assert cash>=-.01
        row.update(cash_after=cash,scale=scale);days.append(row)
    return dict(rule=asdict(rule),scenario=scenario,summary=E.summary(days),days=days)
