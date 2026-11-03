import numpy as np
import forest as F

def test_forest_is_deterministic_day_bootstrap_and_no_test_statistics():
    rng=np.random.default_rng(11);x=rng.normal(size=(120,4));y=np.where(x[:,0]>0,.5,-.3)
    days=np.repeat(np.arange(12),10)
    m=F.fit(x,y,days);n=F.fit(x,y,days)
    assert m==n and m['training_days']==12 and len(m['trees'])==64
    a=F.predict(m,np.array([[10.,1.,1.,1.]]),2)
    assert np.isfinite(a).all()
    def check(node,depth=0):
        assert depth<=2
        if 'feature' in node:
            assert node['left']['distinct_days']>=6 and node['right']['distinct_days']>=6
            check(node['left'],depth+1);check(node['right'],depth+1)
    for tree in m['trees']:check(tree)
