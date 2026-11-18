"""Synthetic source-routing and passive-bound checks; no historical result changed."""
from pathlib import Path
from types import SimpleNamespace
import json, sys
import numpy as np
HERE=Path(__file__).resolve().parent
ROUND=HERE.parent/'2026-11-18-expiry-en71'
sys.path.insert(0,str(ROUND))
import prep7 as P, pk7

fake=SimpleNamespace(und='NIFTY',day='2026-11-17',n=375,
                     strikes=np.array([25300.,25300.]),kinds=np.array([1,-1]))
oi=P.oi_of(fake)
assert not np.isfinite(oi).any()
next_year=SimpleNamespace(**{**vars(fake),'day':'2027-01-01'})
try:
    P.oi_of(next_year)
except KeyError as e:
    year_error=str(e)
else:
    raise AssertionError('expected fixed-year source mapping to reject 2027')

epoch=1794871800
raw=dict(recv=np.array([epoch,epoch+2],np.int64)*10**9,
         exch=np.array([epoch,epoch+2]),lt=np.array([epoch-60,epoch-60]),
         ltp=np.array([10.1,10.1]),vol=np.array([100,100]),oi=np.array([0,0]),
         bp=np.full((2,5),9.9),ap=np.full((2,5),10.1),
         bq=np.full((2,5),100),aq=np.full((2,5),100))
raw['ap'][1,0]=9.95
raw['aq'][1,0]=1
b=pk7.pk6.Book(raw); s=float(b.s[0])
got=pk7.rest2(b,s,10.,65,s+10,'LOWER')
assert got is not None and got[1]==65
out=dict(oi_source=dict(future_tape_day=fake.day,valid_oi_cells=int(np.isfinite(oi).sum()),
                        next_year_error=year_error),
         passive_lower_quote_witness=dict(order_units=65,visible_units_at_or_below_limit=1,
            fresh_quote_after_seconds=2,volume_change=0,last_trade_predates_order=True,
            model_filled_units=got[1],
            finding='LOWER is not a guaranteed whole-order lower bound from this quote evidence'))
(HERE/'mechanics.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps(out,indent=2))
