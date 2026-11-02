"""State order, invalidation, mirrored direction and prefix-causality regressions."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lab_follow as X
import diagnose as D


def fixture(family):
    idx = pd.date_range("2026-03-02 09:15", periods=55, freq="5min")
    t = pd.DataFrame({"open": 100., "high": 100.5, "low": 99.5, "close": 100., "atr": 4., "vwap": 100.,
                      "minute": idx.hour * 60 + idx.minute}, index=idx)
    tr = pd.DataFrame({"pdi": 15., "mdi": 15., "adx": 15.}, index=idx)
    if family == "DMI_VWAP_RETEST":
        vals = {20: [100, 103, 99.8, 102.8], 21: [102, 102.2, 100.2, 101], 22: [101, 103, 100.8, 102.5]}
        tr.iloc[20:24] = [35., 10., 30.]
        tr.iloc[22, tr.columns.get_loc("adx")] = 31.
    else:
        vals = {15: [100, 104, 100, 103.8], 16: [103.8, 103.8, 102.5, 103],
                17: [103, 103.5, 102.6, 103.2], 18: [103.2, 105, 103.1, 104.5]}
    for i, v in vals.items():
        t.iloc[i, t.columns.get_indexer(["open", "high", "low", "close"])] = v
    return {"t": t, "stamps": list(idx.strftime("%Y-%m-%d %H:%M:%S"))}, tr


@pytest.mark.parametrize("family", X.FAMILIES)
def test_entry_after_distinct_confirmation_and_symmetric_prices(family):
    f, trend = fixture(family)
    got = X.entries({"family": family}, f, trend)
    i = 22 if family == "DMI_VWAP_RETEST" else 18
    d, stop, target = got[f["stamps"][i]]
    assert d == 1 and stop < f["t"]["close"].iloc[i] < target
    m = f["t"].copy()
    m["open"], m["close"], m["vwap"] = 200-m["open"], 200-m["close"], 200-m["vwap"]
    m["high"], m["low"] = 200-f["t"]["low"], 200-f["t"]["high"]
    tr = trend.copy();tr["pdi"], tr["mdi"] = trend["mdi"], trend["pdi"]
    rd, rs, rt = X.entries({"family": family}, {**f,"t":m}, tr)[f["stamps"][i]]
    assert rd == -1 and rs == pytest.approx(200-stop) and rt == pytest.approx(200-target)


@pytest.mark.parametrize("family", X.FAMILIES)
def test_all_prefixes_and_changed_future_match(family):
    f, tr = fixture(family)
    full = X.entries({"family":family}, f, tr)
    for cut in range(13,len(f["t"])):
        short = {**f,"t":f["t"].iloc[:cut],"stamps":f["stamps"][:cut]}
        want = {k:v for k,v in full.items() if k in short["stamps"]}
        assert X.entries({"family":family},short,tr.iloc[:cut]) == want
        mutated = f["t"].copy();mutated.iloc[cut:,:4] *= 3
        again = X.entries({"family":family},{**f,"t":mutated},tr)
        assert {k:v for k,v in again.items() if k in short["stamps"]} == want


@pytest.mark.parametrize("family", X.FAMILIES)
def test_invalidation_gap_and_wait_deadline(family):
    f,tr = fixture(family); touch = 21 if family == "DMI_VWAP_RETEST" else 17
    changed = f["t"].copy();changed.iloc[touch,changed.columns.get_loc("close")] = 99.
    assert not X.entries({"family":family},{**f,"t":changed},tr)
    changed = f["t"].copy();changed.iloc[touch,changed.columns.get_loc("minute")] += 30
    assert not X.entries({"family":family},{**f,"t":changed},tr)
    changed = f["t"].copy();changed.loc[changed.index>=changed.index[touch],"minute"] += 180
    assert not X.entries({"family":family},{**f,"t":changed},tr)


def test_no_shock_entry_before_two_inside_bars_and_no_same_bar_retest():
    f,tr = fixture("SHOCK_FLAG")
    f["t"].iloc[16,f["t"].columns.get_loc("high")] = 105.
    assert not X.entries({"family":"SHOCK_FLAG"},f,tr)
    f,tr = fixture("DMI_VWAP_RETEST")
    hit = X.entries({"family":"DMI_VWAP_RETEST"},f,tr)
    assert f["stamps"][20] not in hit and f["stamps"][21] not in hit


def test_large_or_missing_risk_is_rejected():
    for family in X.FAMILIES:
        f,tr = fixture(family);f["t"]["atr"] = .1
        assert not X.entries({"family":family},f,tr)
        f["t"]["atr"] = np.nan
        assert not X.entries({"family":family},f,tr)


def test_missing_trend_or_vwap_cannot_confirm():
    f,tr = fixture("DMI_VWAP_RETEST")
    tr.iloc[22:,tr.columns.get_loc('adx')] = np.nan
    assert not X.entries({'family':'DMI_VWAP_RETEST'},f,tr)
    for family in X.FAMILIES:
        f,tr = fixture(family);f['t']['vwap'] = np.nan
        assert not X.entries({'family':family},f,tr)


@pytest.mark.parametrize('family',X.FAMILIES)
def test_wait_expiry_is_not_extended_by_a_late_confirmation(family):
    f,tr = fixture(family)
    if family=='DMI_VWAP_RETEST':
        for i in range(22,28):
            f['t'].iloc[i,f['t'].columns.get_indexer(['open','high','low','close'])]=[101,101.2,100.2,101]
        f['t'].iloc[28,f['t'].columns.get_indexer(['open','high','low','close'])]=[101,103,100.8,102.5]
        tr.iloc[20:30]=[35,10,30]
    else:
        for i in range(18,22):
            f['t'].iloc[i,f['t'].columns.get_indexer(['open','high','low','close'])]=[103,103.8,102.6,103]
        f['t'].iloc[22,f['t'].columns.get_indexer(['open','high','low','close'])]=[103.5,105,103.5,104.5]
    assert not X.entries({'family':family},f,tr)


@pytest.mark.parametrize('family',X.FAMILIES)
def test_dispatch_only_reads_completed_bars(family):
    from datetime import datetime
    f,_=fixture(family);frame=f['t'][['open','high','low','close']].copy()
    prior=frame.copy();prior.index-=pd.Timedelta(days=1)
    frame=pd.concat([prior,frame]);frame['volume']=1000.
    now=X.Y.replay.IST.localize(datetime(2026,3,2,11,9,59))
    X._CACHE.clear();X.O27F._FEATURES.clear()
    a=X.signal(X.member(family),frame,'UNKNOWN',now)
    assert pd.Timestamp(a.bar_ts)==pd.Timestamp('2026-03-02 11:00')
    frame.loc[frame.index>=pd.Timestamp('2026-03-02 11:05'),['open','high','low','close']]*=3
    X._CACHE.clear();X.O27F._FEATURES.clear()
    b=X.signal(X.member(family),frame,'UNKNOWN',now)
    assert repr(a)==repr(b)


def test_combined_contract_and_unknown_gate():
    b = X.books()
    for family in X.FAMILIES:
        ex = b['EX|'+family]
        assert ex['members'][:4] == b['EX|MAIN']['members']
        assert ex['members'][4]['gate'] == 'adx_abs30:LOW'
        assert ex['cfg'] == {} and ex['skip'] == .5 and ex['cost'] == [200,5]
        assert b['RAW|'+family]['cfg']['FNO_MAX_LOTS'] == 1
    assert not X.Y.ROUTER.allowed('adx_abs30:LOW',{'side':{'adx_abs30':None}})


def test_diagnostic_missing_is_not_a_good_condition_and_partitions_reconcile():
    assert D.bucket('rvol', None) == 'MISSING'
    assert D.bucket('rv10', float('nan')) == 'MISSING'
    rows=[{'day':'2025-01-01','net':100.},{'day':'2025-01-02','net':-50.}]
    s=D.aggregate(rows)
    assert s['trades']==2 and s['net']==50 and s['without_best_day']==-50
