"""Independent arithmetic/clock/cache reconciliation; no strategy selection."""
import argparse,json,sys
from collections import Counter
from datetime import datetime,timedelta
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(HERE),str(HERE/'calendar')]
import lab_broad as B
from fno_costs import calc_fno_costs
load=lambda p:json.loads(p.read_text())


def inputs():
    B.O27F.deny_network();B.verify('screen');B.Y.speedups()
    cached=B.Y.dataset('year');raw=B.Y.yeardata.YearData(B.Y.YEAR,cache=None)
    days=[d for d in raw.days if B.C.WINDOW[0]<=d<=B.C.WINDOW[1]]
    for i,d in enumerate(days,1):
        assert cached.observations(d)==raw._observations(d),('raw/cache mismatch',d)
        if i%50==0:print('Raw/cache',B.YEAR,i,'/',len(days),flush=True)
    B.verify('screen')
    B.P.write(HERE/f'_local/input-check-{B.YEAR}.json',{'year':B.YEAR,'sessions_checked':len(days),'raw_observations_identical_to_cache':True,'all_frozen_bindings_match':True})
    print('INPUT_VERIFIED',B.YEAR,len(days),flush=True)


def ledgers():
    B.verify('screen')
    for sub in ('calendar','expressions'):
        f=load(HERE/sub/'freeze.json')
        assert f['parent_freeze']==B.P.sha(HERE/'freeze.json')
        assert all(B.P.sha(B.ROOT/p)==h for p,h in f['sources'].items())
        if 'plan_sha256' in f:assert B.P.sha(HERE/sub/'PLAN.md')==f['plan_sha256']
    counts=Counter();max_error=0.;files={};special={'2024-03-02','2024-05-18'};calendar_changes={}
    for root in (HERE,HERE/'calendar'):
        for phase in ('screen','selected'):
            for year in ('2024','2025','2026'):
                keypath=root/f'_local/keys-{phase}-{year}.json'
                if not keypath.exists():continue
                for name,key in load(keypath).items():
                    file=root/'_local/evals'/f'{key}.json'
                    if file in files:continue
                    obj=load(file);perday=Counter();unresolved=0
                    for t in obj['trades']:
                        counts['records']+=1
                        if t.get('net_pnl') is None:
                            counts['unresolved_original' if root==HERE else 'unresolved_corrected']+=1;unresolved+=1
                            assert root==HERE and year=='2024' and t['entry_time'][:10] in special
                            continue
                        counts['closed_records']+=1;qty=t['entry_qty'];assert qty%65==0 and qty>0 and t['lots_at_exit']*65==qty and t['adds']==0
                        gross=(t['exit_premium']-t['entry_premium'])*qty
                        fees=calc_fno_costs(t['entry_premium'],t['exit_premium'],qty)
                        expected=gross-fees-float(t.get('extra_cost') or 0)
                        error=abs(expected-t['net_pnl']);max_error=max(max_error,error)
                        assert error<.0001 and abs(gross-t['gross_pnl'])<.0001
                        entry=datetime.fromisoformat(t['entry_time']);exit=datetime.fromisoformat(t['exit_time']);bar=datetime.fromisoformat(t['bar_ts']).replace(tzinfo=entry.tzinfo)
                        assert bar+timedelta(minutes=5)<=entry<=exit
                        minute=entry.hour*60+entry.minute;end=exit.hour*60+exit.minute
                        assert minute<885 and end<=910
                        if root!=HERE and entry.date().isoformat() in special:
                            assert minute<720 and end<=745
                            counts['special_closed_records']+=1
                        perday[entry.date().isoformat()]+=1
                        assert perday[entry.date().isoformat()]<=obj['book']['cfg'].get('FNO_MAX_TRADES_PER_DAY',3)
                    assert not any(v for k,v in obj['notes'].items() if 'conflict' in k or k=='named_memo_miss')
                    files[file]={'sha256':B.P.sha(file),'records':len(obj['trades']),'unresolved':unresolved}
    # All corrected2024 controls must be unchanged; ordinary-day records in
    # RAW books are independent across days and must also be exactly identical.
    original=load(HERE/'_local/keys-screen-2024.json');fixed=load(HERE/'calendar/_local/keys-screen-2024.json')
    for name,key in fixed.items():
        a=load(HERE/'_local/evals'/f'{original[name]}.json')['trades'];b=load(HERE/'calendar/_local/evals'/f'{key}.json')['trades']
        if name in ('EX|MAIN','RAW|MAIN','RAW|E|tpb_puts'):assert a==b,('calendar control changed',name)
        if name!='EX|MAIN':assert [t for t in a if t['entry_time'][:10] not in special]==[t for t in b if t['entry_time'][:10] not in special],('ordinary record changed',name)
        calendar_changes[name]={'original_unresolved':sum(t.get('net_pnl') is None for t in a),'corrected_unresolved':sum(t.get('net_pnl') is None for t in b),'records_changed':a!=b}
    reused=load(HERE/'calendar/_local/reuse-screen.json')
    assert len(reused)==118
    assert all(B.P.sha(B.ROOT/r['file'])==r['sha256'] and r['clock_override_active'] is False for r in reused.values())
    counts.setdefault('unresolved_original',0);counts.setdefault('unresolved_corrected',0)
    out={'schema':'o31i_ledger_reconciliation_v1','counts':dict(counts),'fresh_replay_files':len(files),'max_net_error_rs':max_error,'financial_or_clock_errors':0,'all_nested_source_hashes_match':True,'corrected_control_parity':True,'ordinary_raw_record_parity':True,'reused_screen_files':len(reused),'reused_file_hashes_match':True,'calendar_changes':calendar_changes,
         'replay_file_sha256':{p.relative_to(B.ROOT).as_posix():v for p,v in files.items()}}
    B.P.write(HERE/'crosschecks.json',out)
    print('LEDGER_VERIFIED',dict(counts),'files',len(files),'max_error',max_error,flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['inputs','ledgers']);a=p.parse_args();{'inputs':inputs,'ledgers':ledgers}[a.action]()
