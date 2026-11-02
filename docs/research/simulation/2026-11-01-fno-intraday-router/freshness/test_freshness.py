from datetime import datetime
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import fresh_lab as F


@pytest.mark.parametrize('clock,expected',[('10:09:59',False),('10:10:00',True),('11:30:00',True)])
def test_closed_bar_end_age_boundary(clock,expected):
    assert F.stale('2024-03-02 10:00:00',datetime.fromisoformat('2024-03-02T'+clock+'+05:30')) is expected


def test_gap_resumption_does_not_reuse_pre_gap_state_or_exit_history(monkeypatch):
    original=({'state':'TREND_UP'},'2024-03-02 09:55:00',{'old':{'state':'RANGE'}})
    monkeypatch.setattr(F,'_original_state',lambda *a:original)
    row,bar,history=F.state_at(None,datetime.fromisoformat('2024-03-02T11:30:59+05:30'))
    assert row['state']=='UNAVAILABLE' and history=={} and bar==original[1]
    assert not F.X.R.invalidates('TREND_UP',[], 'LONG')


def test_fresh_and_no_bar_cases(monkeypatch):
    original=({'state':'RANGE'},'2024-03-02 09:50:00',{'real':{'state':'RANGE'}})
    monkeypatch.setattr(F,'_original_state',lambda *a:original)
    assert F.state_at(None,datetime.fromisoformat('2024-03-02T09:59:59+05:30'))==original
    monkeypatch.setattr(F,'_original_state',lambda *a:({'state':'UNAVAILABLE'},None,{}))
    assert F.state_at(None,datetime.fromisoformat('2024-03-02T09:20:00+05:30'))[0]['state']=='UNAVAILABLE'
