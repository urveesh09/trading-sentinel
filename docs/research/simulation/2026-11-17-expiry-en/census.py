"""Expiry-day option coverage census (counts only, no prices). NIFTY 2023 skipped (protected exam)."""
import sqlite3, pathlib, json, time
p = pathlib.Path.home()/"sentinel-operations/breeze-history-20261029/data/breeze-history.sqlite"
c = sqlite3.connect(p.resolve().as_uri()+"?mode=ro", uri=True)
out=[]
t=time.time()
for u in ('NIFTY','SENSEX'):
    last=''
    while True:
        r=c.execute("SELECT expiry FROM candles WHERE kind='option' AND underlying=? AND expiry>? ORDER BY expiry LIMIT 1",(u,last)).fetchone()
        if not r: break
        e=r[0]; last=e
        if u=='NIFTY' and e.startswith('2023'): out.append(dict(u=u,e=e,protected=True)); continue
        legs=[]; lk=(-1.0,'')
        while True:
            r=c.execute("SELECT strike,opt FROM candles WHERE kind='option' AND underlying=? AND expiry=? AND (strike>? OR (strike=? AND opt>?)) ORDER BY strike,opt LIMIT 1",(u,e,lk[0],lk[0],lk[1])).fetchone()
            if not r: break
            lk=(r[0],r[1]); legs.append(lk)
        full=0; aft=0; mins=0
        for s,o in legs:
            n=c.execute("SELECT count(*) FROM candles WHERE kind='option' AND underlying=? AND expiry=? AND strike=? AND opt=? AND interval='1minute' AND datetime BETWEEN ? AND ?",(u,e,s,o,e+' 13:00:00',e+' 15:29:59')).fetchone()[0]
            if n>=100: aft+=1
            mins+=n
        ix=c.execute("SELECT count(*) FROM candles WHERE kind='index' AND underlying=? AND expiry='' AND strike=0 AND opt='' AND interval='1minute' AND datetime BETWEEN ? AND ?",(u,e+' 09:15:00',e+' 15:30:00')).fetchone()[0] if False else None
        out.append(dict(u=u,e=e,legs=len(legs),aft_legs=aft,aft_rows=mins))
print(time.time()-t)
json.dump(out,open('census.json','w'),indent=0)
