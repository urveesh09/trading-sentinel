import numpy as np
import return_lab as V

def test_mean_return_fit_day_weights_and_training_only_imputation():
    x=np.array([[1.,np.nan],[2.,3.],[3.,4.],[4.,5.]])
    y=np.array([-.3,-.2,.8,.5]);days=np.array(['a','a','a','b'])
    m=V.fit(x,y,days);assert m['training_day_weight']==2 and m['impute'][1]==4
    first=V.predict(m,np.array([[100.,np.nan]]),2)
    assert np.isfinite(first).all() and (first<=1).all() and (first>=-1.25).all()
    assert m==V.fit(x,y,days)

def test_no_daywide_or_future_score_selects_earlier_entry():
    rows=[dict(day='d',i=1,j=0,direction=1),dict(day='d',i=1,j=1,direction=-1),dict(day='d',i=2,j=2,direction=1)]
    V.activate(rows,np.array([.1,-.2,.9]));assert V.ACTIVE['d'][1][0]==0
    V.activate(rows,np.array([.1,-.2,-.9]));assert V.ACTIVE['d'][1][0]==0
