"""Calendar moving-block uncertainty; conditional on weak stationarity, not exact randomization."""
from datetime import date,timedelta
import numpy as np

def weeks(days,values):
    ds=[date.fromisoformat(d) for d in days]
    start=min(ds)-timedelta(days=min(ds).weekday());end=max(ds)
    n=(end-start).days//7+1
    x=np.zeros(n);counts=np.zeros(n)
    for d,v in zip(ds,values):
        k=(d-start).days//7;x[k]+=v;counts[k]+=1
    return x,counts

def infer(days,values,B=9999,block=4,seed=20261118):
    x,n=weeks(days,values);return group_t(x,n)

def group_t(x,n,groups=8):
    """Eight long chronological group means; t reference conditional on approx independent groups.

    Economic mean uses all sessions; test/interval target the equal-period mean.
    No independence/distribution-free claim. Too-short series is inconclusive.
    """
    from scipy.stats import t
    G=min(groups,len(x)//10)
    raw=float(np.sum(x)/np.sum(n))
    if G<4:return dict(mean=raw,lo=None,hi=None,p=1.,groups=G,method='GROUP_T_INSUFFICIENT')
    means=np.array([x[idx].sum()/n[idx].sum() for idx in np.array_split(np.arange(len(x)),G) if n[idx].sum()>0])
    G=len(means);mu=float(means.mean());se=float(means.std(ddof=1)/np.sqrt(G))
    statistic=mu/se if se else (np.inf if mu>0 else -np.inf if mu<0 else 0.)
    critical=t.ppf(.975,G-1)
    return dict(mean=round(raw,4),group_mean=round(mu,4),lo=round(mu-critical*se,4),hi=round(mu+critical*se,4),
                p=float(t.sf(statistic,G-1)),groups=G,method='LONG_GROUP_T',group_means=means.tolist())

def infer_arrays(x,n,B,block,seed):
    rng=np.random.default_rng(seed);N=len(x);block=min(block,N)
    obs=float(np.sum(x)/np.sum(n));means=[]
    for k in range(0,B,1000):
        starts=rng.integers(0,N,(min(1000,B-k),int(np.ceil(N/block))))
        idx=((starts[:,:,None]+np.arange(block))%N).reshape(len(starts),-1)[:,:N]
        den=n[idx].sum(1); good=den>0
        means.extend((x[idx].sum(1)[good]/den[good]).tolist())
    boot=np.array(means)
    p=(1+np.sum(boot-obs>=obs-1e-10))/(1+len(boot)) if obs>0 else 1.
    return dict(mean=round(obs,4),lo=round(float(np.percentile(boot,2.5)),4),
                hi=round(float(np.percentile(boot,97.5)),4),p=float(p),block=block,draws=len(boot))

def holm(ps):
    keys=sorted(ps,key=ps.get);prev=0.;out={}
    for rank,key in enumerate(keys):
        prev=max(prev,min(1.,(len(keys)-rank)*ps[key]));out[key]=float(prev)
    return out

def calibrate(paths=1000,n=197):
    rng=np.random.default_rng(860095);out={}
    for kind in ('gaussian','skewed','heavy_tail','dependent'):
        reject=detect=detect25=detect_trade100=0;cover=0
        for k in range(paths):
            if kind=='gaussian':x=rng.normal(size=n)
            elif kind=='skewed':x=1-rng.exponential(size=n)
            elif kind=='heavy_tail':x=rng.standard_t(3,size=n)/np.sqrt(3)
            else:
                z=rng.normal(size=n+200);a=np.zeros(n+200)
                for j in range(1,len(z)):a[j]=.6*a[j-1]+np.sqrt(1-.6**2)*z[j]
                x=a[-n:]
            x=x*500.;a=group_t(x,np.ones(n))
            reject+=a['p']<=.05;cover+=a['lo']<=0<=a['hi']
            # Large, specified positive effect: Rs250 per scheduled expiry.
            b=group_t(x+250,np.ones(n));detect+=b['p']<=.05
            detect25+=group_t(x+25,np.ones(n))['p']<=.05
            activity=np.random.default_rng(999000+1000*('gaussian','skewed','heavy_tail','dependent').index(kind)+k).random(n)<.35
            detect_trade100+=group_t(x+100*activity,np.ones(n))['p']<=.05
        from scipy.stats import beta
        lo=float(beta.ppf(.025,reject,paths-reject+1)) if reject else 0.
        hi=float(beta.ppf(.975,reject+1,paths-reject)) if reject<paths else 1.
        out[kind]=dict(paths=paths,rejections=reject,rejection_rate=reject/paths,
                       binomial_95=[lo,hi],interval_covers_zero=cover/paths,positive_250_detection=detect/paths,
                       positive_25_per_expiry_detection=detect25/paths,positive_100_on_35pct_activity_detection=detect_trade100/paths)
    return dict(cases=out,primary_method='eight long chronological groups, t7 reference',
                inference_validated=all(v['binomial_95'][1]<=.075 for v in out.values()),
                note='finite Monte Carlo diagnostic, not a guarantee for arbitrary market dependence')
