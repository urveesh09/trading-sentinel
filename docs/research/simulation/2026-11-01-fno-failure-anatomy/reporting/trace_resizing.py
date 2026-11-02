"""Same opportunity with different quantity is a cash/risk-path effect, not an exit pair."""
import json,sys,math
from pathlib import Path
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE.parent/'2026-11-01-fno-variant-selector'))
import variant_lab as L
load=lambda p:json.loads(p.read_text())
FIELDS=('entry_time','tradingsymbol','direction','entry_premium','entry_underlying','initial_stop_underlying','initial_target_underlying','bar_ts','entry_expert')


def run():
    out=[]
    for y,fs in L.reference_files().items():
        old={tuple(t[k] for k in FIELDS):t for t in load(fs['STRUCT30'])['trades']};new={tuple(t[k] for k in FIELDS):t for t in load(fs['STALL30'])['trades']}
        for k in old.keys()&new.keys():
            a,b=old[k],new[k]
            if a['entry_qty']==b['entry_qty']:continue
            out.append(dict(year=y,opportunity={f:b[f] for f in FIELDS},struct_admission=a['admission_id'],stall_admission=b['admission_id'],struct_qty=a['entry_qty'],stall_qty=b['entry_qty'],
                struct_net=a['net_pnl'],stall_net=b['net_pnl'],actual_cash_contribution_delta=b['net_pnl']-a['net_pnl'],same_exit=(a['exit_time'],a['exit_premium'],a['exit_reason'])==(b['exit_time'],b['exit_premium'],b['exit_reason'])))
    L.X.write(HERE/'resizing-attribution.json',dict(records=out,note='Actual separate-book quantities/cash contributions; not identical-entry economics, not hypothetical scaled P&L or leverage recommendation. Prior loss history/cash/risk gates differ.'))
    print('SAVED_RESIZING',out,flush=True)


if __name__=='__main__':run()
