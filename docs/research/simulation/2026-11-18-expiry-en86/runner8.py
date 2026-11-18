"""Offline sealed-snapshot forward runner: status/run/review/rehearse. Never downloads data."""
from pathlib import Path
from datetime import datetime
import argparse,json,sqlite3,uuid,shutil
import offline8
import data8,lab8,signals8,payoff8,forward8,score8
HERE=Path(__file__).resolve().parent
POLICIES=('E03_env','E032_native','EN55_native','EN83',*lab8.PRIMARY)

def evaluate(calendar,snapshot,expected_sha,ledger,now,rehearsal=False):
    f,B=score8.verify_freeze();snapshot=Path(snapshot).resolve()
    if data8.sha(snapshot)!=expected_sha:raise ValueError('snapshot identity mismatch')
    # An actively changing SQLite store is not a sealed research input.
    wal=Path(str(snapshot)+'-wal')
    if wal.exists() and wal.stat().st_size:raise ValueError('snapshot has active WAL')
    sealed=HERE/'_local'/'sealed-forward';sealed.mkdir(parents=True,exist_ok=True)
    copy=sealed/(expected_sha+'.sqlite')
    if not copy.exists():
        with open(snapshot,'rb') as src,open(copy,'xb') as dst:shutil.copyfileobj(src,dst,1024*1024)
    if data8.sha(copy)!=expected_sha:raise ValueError('copied snapshot identity mismatch')
    snapshot=copy
    freeze_time=datetime.fromisoformat(f['created_utc'].replace('Z','+00:00'))
    cal=calendar;cohort={'NIFTY':'0001-01-01','SENSEX':'0001-01-01'}
    scheduled=forward8.due(cal,now,cohort)
    if not rehearsal:
        scheduled=[x for x in scheduled if datetime.fromisoformat(x['day']+'T'+x.get('close','15:30:00')).replace(tzinfo=forward8.IST)>freeze_time]
    records=ledger.rows();done={(r['policy'],r['underlying'],r['day']):r for r in records}
    pending=[];ready=[]
    for x in scheduled:
        und,day=x['underlying'],x['day']
        todo=[p for p in POLICIES if (p,und,day) not in done]
        if not todo:continue
        cov=forward8.coverage(snapshot,und,day,False)
        oi_cov=None
        for p in todo:
            need_oi=p not in ('E03_env','E032_native','EN55_native')
            c=cov
            if need_oi:
                if und=='SENSEX':c=dict(eligible=False,missing=['SENSEX OI unavailable'])
                else:
                    if oi_cov is None:oi_cov=forward8.coverage(snapshot,und,day,True)
                    c=oi_cov
            key=(p,und,day);body=dict(snapshot=str(snapshot),snapshot_sha256=expected_sha,
                calendar_sha256=forward8.digest(cal),freeze_sha256=data8.sha(score8.FREEZE),dry_run=rehearsal)
            if not c['eligible']:
                status=forward8.record_availability(ledger,key,c,now,body);pending.append([p,und,day,status]);continue
            ready.append((p,und,day,body))
    if not ready:
        return dict(new=0,unavailable=pending,already_final=len(done),dry_run=rehearsal)
    needed={(u,d) for p,u,d,b in ready};forward={u:[] for u in B}
    for u,d in sorted(needed):forward[u].append(forward8.build_tape(snapshot,u,d))
    # Rehearsal dates are removed from history: never duplicate a training session.
    for u in B:
        hist=[t for t in B[u] if (u,t.day) not in needed]
        full=sorted(hist+forward[u],key=lambda t:t.day)
        signals8.prepare(full)
        if u=='NIFTY':payoff8.prepare(full)
    tapes={(u,t.day):t for u in forward for t in forward[u]};owner=uuid.uuid4().hex;new=0
    for p,u,d,body in ready:
        key=(p,u,d)
        if not ledger.claim(key,owner,now.timestamp()):continue
        t=tapes[(u,d)];out=dict(body)
        for sc in ('ordinary','adverse','catastrophe'):
            day=lab8.run_day8(t,lab8.ARMS[p],sc,30000.,lab8.L7.budget_of(lab8.ARMS[p]),True);day['und']=u
            out[sc]=dict(net=day['net'],trades=day['trades'],fees=day['fees'],unresolved=day['unresolved'],marked_worst=day['marked_worst'])
        if data8.sha(snapshot)!=expected_sha:raise ValueError('sealed input changed before commit')
        ledger.record(key,'ELIGIBLE',out,owner);new+=1
    if data8.sha(snapshot)!=expected_sha:raise ValueError('snapshot changed during replay; reject these run receipts')
    return dict(new=new,unavailable=pending,already_final=len(done),dry_run=rehearsal)

def review(ledger):
    report=forward8.review(ledger,POLICIES)
    rows=ledger.rows();snapshots={r['body'].get('snapshot'):r['body'].get('snapshot_sha256') for r in rows if r['status']=='ELIGIBLE'}
    _,B=score8.verify_freeze();forward={u:[] for u in B}
    for u,d in sorted({(r['underlying'],r['day']) for r in rows if r['status']=='ELIGIBLE'}):
        r=next(x for x in rows if x['underlying']==u and x['day']==d and x['status']=='ELIGIBLE');p=Path(r['body']['snapshot'])
        if data8.sha(p)!=r['body']['snapshot_sha256']:raise ValueError('review snapshot changed')
        forward[u].append(forward8.build_tape(p,u,d))
    for u in B:
        ids={t.day for t in forward[u]};full=sorted([t for t in B[u] if t.day not in ids]+forward[u],key=lambda t:t.day)
        signals8.prepare(full)
        if u=='NIFTY':payoff8.prepare(full)
        for p in POLICIES:
            eligible={r['day'] for r in rows if r['underlying']==u and r['policy']==p and r['status']=='ELIGIBLE'}
            book=[t for t in forward[u] if t.day in eligible]
            if not book:continue
            w=lab8.wallet(book,lab8.ARMS[p]);report[p+'|'+u]['wallet']={k:v for k,v in w.items() if k!='days'}
            report[p+'|'+u]['wallet_note']='repriced over eligible sessions only; any missing session prevents an exact continuous-wallet claim'
    return report

def rehearse():
    f,B=score8.verify_freeze();local=HERE/'_local';local.mkdir(exist_ok=True)
    snap=local/'rehearsal8.sqlite';db=local/'rehearsal8-ledger.sqlite'
    if snap.exists() or db.exists():raise ValueError('rehearsal exists; preserve its evidence')
    chosen={'NIFTY':B['NIFTY'][-8:],'SENSEX':B['SENSEX'][-4:]}
    con=sqlite3.connect(snap)
    try:
        con.execute('CREATE TABLE candles(kind TEXT,underlying TEXT,expiry TEXT,strike REAL,opt TEXT,datetime TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL,oi REAL,interval TEXT)')
        for u,book in chosen.items():
            for t in book:
                source=sqlite3.connect(Path(t.oi_source8['path']).resolve().as_uri()+'?mode=ro',uri=True)
                try:
                    rows=source.execute('SELECT kind,underlying,expiry,strike,opt,datetime,open,high,low,close,volume,oi FROM candles WHERE underlying=? AND datetime BETWEEN ? AND ?',
                         (u,t.day+' 09:15:00',t.day+' 15:29:00')).fetchall()
                finally:source.close()
                con.executemany('INSERT INTO candles VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',[(*r,'1minute') for r in rows])
        con.execute('CREATE INDEX k ON candles(underlying,datetime,kind)');con.commit()
    finally:con.close()
    cal=dict(source='sealed round7 historical sample; rehearsal only, not an exhaustive exchange calendar',verified_through=max(t.day for b in chosen.values() for t in b),
             sessions=[dict(underlying=u,day=t.day) for u,b in chosen.items() for t in b])
    ledger=forward8.Ledger(db);now=datetime(2026,11,18,23,0,tzinfo=forward8.IST);sha=data8.sha(snap)
    a=evaluate(cal,snap,sha,ledger,now,True);before=ledger.rows();b=evaluate(cal,snap,sha,ledger,now,True)
    assert b['new']==0 and ledger.rows()==before
    expected=json.loads((HERE/'anatomy8.json').read_text())['days'];checks=0
    for row in before:
        if row['status']!='ELIGIBLE':continue
        key=row['policy']+'|'+row['underlying']
        ref=next(d for d in expected[key] if d['day']==row['day'])
        assert row['body']['ordinary']['net']==ref['net'],(key,row['day'],row['body']['ordinary'],ref)
        checks+=1
    score8.write(HERE/'rehearsal8.json',dict(status='PASS',dry_run=True,first=a,second=b,matched_arm_days=checks,
        receipt_count=len(before),snapshot_sha256=sha,calendar=cal,note='seen dates only; strict coverage may reject some of the 12 days'))
    print('REHEARSAL PASS',checks,'arm-days matched; second run added zero',flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['status','run','review','rehearse'])
    p.add_argument('--ledger',type=Path,default=HERE/'forward8'/'ledger.sqlite')
    p.add_argument('--calendar',type=Path);p.add_argument('--snapshot',type=Path);p.add_argument('--expected-snapshot-sha');p.add_argument('--now')
    a=p.parse_args()
    if a.command=='rehearse':rehearse();return
    l=forward8.Ledger(a.ledger)
    if a.command=='status':print(json.dumps(dict(rows=l.rows(),notice='explicit dated calendar and sealed snapshot required; no automatic acquisition'),indent=2));return
    if a.command=='review':print(json.dumps(score8.clean(review(l)),indent=2));return
    if not all([a.calendar,a.snapshot,a.expected_snapshot_sha,a.now]):p.error('run needs --calendar --snapshot --expected-snapshot-sha --now (aware ISO)')
    now=datetime.fromisoformat(a.now)
    if now.tzinfo is None:p.error('--now must be timezone-aware')
    r=evaluate(json.loads(a.calendar.read_text()),a.snapshot,a.expected_snapshot_sha,l,now)
    print(json.dumps(r,indent=2))

if __name__=='__main__':main()
