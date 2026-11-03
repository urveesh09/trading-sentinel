"""Materialize a reviewable E03.1 loop with one narrowly bounded order-state hook."""
from pathlib import Path
import inspect
import mechanisms as M

def build():
    source=inspect.getsource(M.L.run_day)
    old='''            filled, price = E.executable(t, i, j, "BUY", scenario, lots)
            if filled < max(1, math.ceil(lots * .25)) or price is None or price > limit:
                rejected += 1; continue'''
    new='''            if rule.mechanism == "patient" and patient_cancel(t, i, decision, sign, atr, rule):
                rejected += 1; continue
            filled, price = E.executable(t, i, j, "BUY", scenario, lots)
            if filled < max(1, math.ceil(lots * .25)) or price is None or price > limit:
                if rule.mechanism == "patient" and i - decision < rule.wait_bars:
                    pending_entry = (j, lots, limit, decision, sign, atr, room)
                rejected += 1; continue'''
    assert source.count(old)==1
    source=source.replace(old,new)
    pre='''"""Generated from frozen E03.1 run_day by build_loop.py; inspect its one asserted hook."""
from mechanisms import E, X, LOT, PARTIAL, directions, choose, stalled, timed_out, recover_lots, patient_cancel
import math
import numpy as np

'''
    path=Path(__file__).with_name('mechanism_day.py')
    assert not path.exists()
    path.write_text(pre+source,encoding='utf-8')
    print('MATERIALIZED',path.name)

if __name__=='__main__':build()
