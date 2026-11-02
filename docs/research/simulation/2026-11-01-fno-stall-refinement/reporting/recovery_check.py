"""Check the two motivating recovery cases using exact economic fingerprints."""
import hashlib,json,sys
from datetime import date,datetime
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import analyze_refine as A
L=A.L
def fingerprint(t):
    e={f:t[f] for f in ('initial_entry_time','initial_entry_premium','initial_quantity','initial_stop_underlying','initial_target_underlying')};e.update(tradingsymbol=t['tradingsymbol'],direction=t['direction']);return hashlib.sha256(json.dumps(e,sort_keys=True).encode()).hexdigest()
def run():
    L.B.O27F.deny_network();L.verify();L.B.L._init();assert L.B.YEAR=='2024';data=L.Y.dataset('year');rows=A.objects()['2024']['NORMAL|BALANCED_RETEST|STRUCT30']['trades'];index={fingerprint(t):t for t in rows};assert len(index)==len(rows)
    cases=A.load(L.PARENT/'stall-case-audit.json')['exact_economic_pairs'];checks=[]
    for case in cases:
        if case['year']!='2024' or case['later_paired_exit_label']['delta']>=0:continue
        t=index[case['economic_fingerprint']];label=case['later_paired_exit_label'];now=datetime.fromisoformat(label['stall_exit_time']);day=now.date();frame=data.futures_frame(data.future_contract(data.front_expiry(day)).token,day);c=L.P.E.context(frame,now);level=t['n03_entry_context']['broken_level'];sign=1 if t['direction']=='LONG' else -1
        assert c and c['fresh'] and sign*(c['close']-level)>=0 and t['net_pnl']==label['base_net'] and t['exit_time']==label['base_exit_time']
        checks.append({'economic_fingerprint':case['economic_fingerprint'],'new_admission_id':t['admission_id'],'old_review_time':now.isoformat(),'known_then':{'closed_bar':c['bar'],'close':c['close'],'original_retest_level':level,'fresh':c['fresh']},'later_labels':{'struct_net':t['net_pnl'],'old_early_net':label['stall_net'],'original_net':label['base_net']}})
    assert len(checks)==2;L.verify();L.X.write(HERE/'recovery-checks.json',{'status':'DESCRIPTIVE_CASE_VERIFICATION_NOT_FITTING','checks':checks,'both_level_still_intact_at_old_review':True,'same_original_exit_economics_retained':True});print('RECOVERY_CASES_VERIFIED',len(checks),flush=True)
if __name__=='__main__':run()
