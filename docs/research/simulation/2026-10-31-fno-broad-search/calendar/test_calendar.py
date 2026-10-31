from datetime import datetime
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import calendar_lab as C


@pytest.mark.parametrize('day',['2024-03-02','2024-05-18'])
def test_exact_special_clock_and_boundaries(day):
    before=(C.settings.FNO_ENTRY_END_MIN,C.settings.FNO_HARD_FLAT_MIN)
    for clock in ('11:59','12:00','12:24','12:25','12:29'):
        now=datetime.fromisoformat(day+'T'+clock)
        with C.scoped_clock(now):
            minute=now.hour*60+now.minute
            assert (minute<C.settings.FNO_ENTRY_END_MIN)==(clock=='11:59')
            assert (minute>=C.settings.FNO_HARD_FLAT_MIN)==(clock in ('12:25','12:29'))
    assert (C.settings.FNO_ENTRY_END_MIN,C.settings.FNO_HARD_FLAT_MIN)==before


@pytest.mark.parametrize('day',['2024-01-20','2024-03-01','2024-05-17','2025-03-02','2026-05-18'])
def test_ordinary_call_parity(day):
    args=(object(),object(),datetime.fromisoformat(day+'T12:25'))
    def fn(self,*got):
        return got, C.settings.FNO_ENTRY_END_MIN,C.settings.FNO_HARD_FLAT_MIN
    assert C.wrap(fn)(None,*args)==fn(None,*args)


def test_restores_both_after_failure_and_nested_scope():
    before=(C.settings.FNO_ENTRY_END_MIN,C.settings.FNO_HARD_FLAT_MIN)
    now=datetime.fromisoformat('2024-03-02T12:25')
    with pytest.raises(RuntimeError):
        with C.scoped_clock(now):
            with C.scoped_clock(now):assert C.settings.FNO_HARD_FLAT_MIN==745
            raise RuntimeError('synthetic')
    assert (C.settings.FNO_ENTRY_END_MIN,C.settings.FNO_HARD_FLAT_MIN)==before


def test_keeps_already_stricter_clock():
    before=(C.settings.FNO_ENTRY_END_MIN,C.settings.FNO_HARD_FLAT_MIN)
    try:
        C.settings.FNO_ENTRY_END_MIN=700;C.settings.FNO_HARD_FLAT_MIN=730
        with C.scoped_clock(datetime.fromisoformat('2024-05-18T12:25')):
            assert (C.settings.FNO_ENTRY_END_MIN,C.settings.FNO_HARD_FLAT_MIN)==(700,730)
    finally:C.settings.FNO_ENTRY_END_MIN,C.settings.FNO_HARD_FLAT_MIN=before
