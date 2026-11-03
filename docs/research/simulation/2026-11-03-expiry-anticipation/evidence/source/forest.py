"""Shallow day-bootstrap regression forest; fixed complexity and no test-PnL selection."""
import math
import numpy as np
import precursor as P
import return_lab as V

def fit(x,y,days,seed=314159):
    # Reuse EXACT training-only preprocessing; linear coefficients are not used.
    prep=V.fit(x,y,days);z=P.transform(x,np.array(prep['impute']),np.array(prep['mean']),np.array(prep['scale']))[:,1:]
    unique,group,counts=np.unique(days,return_inverse=True,return_counts=True);rng=np.random.default_rng(seed)
    trees=[]
    for _ in range(64):
        sampled=rng.integers(0,len(unique),size=len(unique));multiplicity=np.bincount(sampled,minlength=len(unique))
        w=multiplicity[group]/counts[group];active=np.flatnonzero(w>0);global_mean=float(np.average(y[active],weights=w[active]))
        def node(ids,depth):
            weights=w[ids];mass=float(weights.sum());total=float(weights@y[ids]);value=(total+8*global_mean)/(mass+8)
            out=dict(value=value,distinct_days=len(np.unique(group[ids])),day_weight=mass)
            if depth>=2 or out['distinct_days']<12:return out
            parent_sse=float(weights@(y[ids]**2))-total*total/mass;best=None
            for j in rng.choice(z.shape[1],size=max(1,int(math.sqrt(z.shape[1]))),replace=False):
                for threshold in np.unique(np.quantile(z[ids,j],[.25,.5,.75])):
                    mask=z[ids,j]<=threshold;left=ids[mask];right=ids[~mask]
                    if min(len(np.unique(group[left])),len(np.unique(group[right])))<6:continue
                    lw=w[left];rw=w[right];lm=float(lw.sum());rm=float(rw.sum())
                    lt=float(lw@y[left]);rt=float(rw@y[right])
                    sse=float(lw@(y[left]**2))+float(rw@(y[right]**2))-lt*lt/lm-rt*rt/rm
                    gain=parent_sse-sse
                    if gain>1e-10 and (best is None or gain>best[0]):best=(gain,int(j),float(threshold),left,right)
            if best:
                gain,j,threshold,left,right=best
                out.update(feature=j,threshold=threshold,gain=gain,left=node(left,depth+1),right=node(right,depth+1))
            return out
        trees.append(node(active,0))
    return dict(impute=prep['impute'],mean=prep['mean'],scale=prep['scale'],trees=trees,
        training_days=len(unique),training_rows=len(y),seed=seed,max_depth=2,min_distinct_days=6,leaf_prior_days=8.)

def predict(model,x,multiple):
    z=P.transform(x,np.array(model['impute']),np.array(model['mean']),np.array(model['scale']))[:,1:]
    values=np.zeros(len(x))
    def visit(node,ids,out):
        if not len(ids):return
        if 'feature' not in node:out[ids]=node['value'];return
        mask=z[ids,node['feature']]<=node['threshold']
        visit(node['left'],ids[mask],out);visit(node['right'],ids[~mask],out)
    for tree in model['trees']:
        out=np.zeros(len(x));visit(tree,np.arange(len(x)),out);values+=out
    return np.clip(values/len(model['trees']),-1.25,multiple-1)
