import sys
from pathlib import Path
from types import SimpleNamespace as S
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import lab_p as P

@pytest.mark.parametrize('delta',[.40,.65,.75])
def test_target_delta_used_only_during_entry_and_restored(monkeypatch,delta):
    original=P.settings.FNO_TARGET_DELTA
    def base(*args):
        assert P.settings.FNO_TARGET_DELTA==delta
        return 'checked'
    monkeypatch.setattr(P,'_entry_before',base)
    assert P.entry(S(book={'target_delta':delta}),None,None,None,None,None)=='checked'
    assert P.settings.FNO_TARGET_DELTA==original

def test_failed_entry_restores_setting(monkeypatch):
    original=P.settings.FNO_TARGET_DELTA
    def fail(*args):raise ValueError('offline failure')
    monkeypatch.setattr(P,'_entry_before',fail)
    with pytest.raises(ValueError):P.entry(S(book={'target_delta':.75}),None,None,None,None,None)
    assert P.settings.FNO_TARGET_DELTA==original

def test_reference_books_and_exits_unchanged():
    b=P.books();assert len(b)==29
    assert sum(k.startswith('P|') for k in b)==6
    assert b['REF|BEST']==P.N.books()['REF|BEST']
    for k,v in b.items():
        if k.startswith('P|'):
            assert v['members']==b['REF|'+k.split('|')[1]]['members']
            assert 'micro' not in v
