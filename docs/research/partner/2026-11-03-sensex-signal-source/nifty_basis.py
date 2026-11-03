import sqlite3,sys
import pandas as pd, numpy as np
sys.stdout.reconfigure(encoding='utf-8')
p=r'C:\Users\Urveesh\sentinel-operations\breeze-history-20261029\data\breeze-history.sqlite'
c=sqlite3.connect(f'file:{p}?mode=ro',uri=True,timeout=1)
idx=pd.read_sql("select datetime,open,high,low,close from candles where kind='index' and underlying='NIFTY' and datetime>='2025-12-01'",c,parse_dates=['datetime'])
fut=pd.read_sql("select expiry,datetime,open,high,low,close,volume from candles where kind='future' and underlying='NIFTY' and datetime>='2025-12-01'",c,parse_dates=['datetime'])
c.close()
fut['day']=fut.datetime.dt.date
fut['exp']=pd.to_datetime(fut.expiry).dt.date
fut=fut[fut.exp>=fut.day]
front=fut.groupby('day').exp.min().rename('front')
fut=fut.join(front,on='day'); fut=fut[fut.exp==fut.front]
def bars5(df,vol=False):
    df=df.set_index('datetime').sort_index()
    agg={'open':'first','high':'max','low':'min','close':'last'}
    if vol: agg['volume']='sum'
    b=df.resample('5min',label='left',closed='left').agg(agg).dropna(subset=['close'])
    return b[(b.index.hour*60+b.index.minute>=555)&(b.index.hour*60+b.index.minute<=925)]
I=bars5(idx); F=bars5(fut,vol=True)
j=I.join(F,lsuffix='_i',rsuffix='_f',how='inner')
j['day']=j.index.date
j['basis']=j.close_f-j.close_i
j['bday']=j.groupby('day').basis.transform('median')
j['err']=j.close_f-(j.close_i+j.bday)
tr=pd.concat([j.high_i-j.low_i,(j.high_i-j.close_i.shift()).abs(),(j.low_i-j.close_i.shift()).abs()],axis=1).max(axis=1)
j['atr']=tr.rolling(14).mean()
j['err_atr']=j.err.abs()/j.atr
lots=j.volume/65
print('days',j.day.nunique(),'bars',len(j))
print('futures contracts per 5-min bar: median',round(lots.median(),1),'p25',round(lots.quantile(.25),1),'zero-volume share',round((j.volume==0).mean(),3))
print('|fut close - (index close + day basis)| points: median',round(j.err.abs().median(),1),'p90',round(j.err.abs().quantile(.9),1),'p99',round(j.err.abs().quantile(.99),1))
print('same in index ATR(14) units: median',round(j.err_atr.median(),3),'p90',round(j.err_atr.quantile(.9),3),'share > 0.5 ATR',round((j.err_atr>0.5).mean(),3),'share > 1 ATR',round((j.err_atr>1).mean(),3))
r_i=j.close_i.diff(); r_f=j.close_f.diff(); m=j.day==j.day.shift()
print('5-min move correlation fut vs index',round(np.corrcoef(r_i[m].dropna(),r_f[m].dropna())[0,1],3))
print('index ATR median points',round(j.atr.median(),1))
# Nov-ish recent month
rec=j[j.index>='2026-10-01']
print('Oct 2026: contracts median',round((rec.volume/20).median(),1),'|err| median',round(rec.err.abs().median(),1),'p90',round(rec.err.abs().quantile(.9),1),'share>0.5ATR',round((rec.err_atr>0.5).mean(),3))
