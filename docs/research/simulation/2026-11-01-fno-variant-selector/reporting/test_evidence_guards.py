"""Adversarial histories and read-only inventory boundaries."""
from datetime import date,timedelta
import hashlib,importlib.util,json,sqlite3,sys
from pathlib import Path
import pytest
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import variant_policy as R
spec=importlib.util.spec_from_file_location('inventory',HERE/'reporting/execution_inventory.py');I=importlib.util.module_from_spec(spec);spec.loader.exec_module(I)


def rows():
    days=[(date(2024,1,1)+timedelta(days=i)).isoformat() for i in range(100) if (date(2024,1,1)+timedelta(days=i)).weekday()<5]
    rs={p:[dict(entry_time=d+'T10:00:00+05:30',exit_time=d+'T11:00:00+05:30',net_pnl=100.) for d in days] for p in R.ORDER}
    return days,rs


def test_single_lucky_day_cannot_justify_switch():
    ds,rs=rows();rs['BASE'][4]['net_pnl']=50000.
    c=R.evidence(rs,ds[-1],ds,'MAIN')['profiles']['BASE']
    assert not c['eligible'] and not c['checks']['paired_days'] and not c['checks']['without_best']


def test_drawdown_guard_rejects_higher_profit_with_worse_path():
    ds,rs=rows()
    for i,t in enumerate(rs['BASE']):t['net_pnl']=-100. if i%2==0 else 500.
    c=R.evidence(rs,ds[-1],ds,'MAIN')['profiles']['BASE']
    assert c['paired_net']>0 and c['checks']['paired_days'] and not c['checks']['drawdown'] and not c['eligible']


def test_many_losing_labels_do_not_create_positive_score():
    ds,rs=rows()
    for t in rs['BASE']:t['net_pnl']=50.
    c=R.evidence(rs,ds[-1],ds,'MAIN')['profiles']['BASE']
    assert c['score']<0 and not c['checks']['score'] and not c['eligible']


def test_inventory_reports_absence_without_touching_source(tmp_path):
    db=tmp_path/'cache.db';c=sqlite3.connect(db);c.execute('CREATE TABLE fno_positions(source TEXT,status TEXT)');c.execute("INSERT INTO fno_positions VALUES('FNO_PAPER','CLOSED')");c.commit();c.close()
    before=hashlib.sha256(db.read_bytes()).hexdigest();out=I.inventory(tmp_path)
    assert out['tables']['fno_positions']['rows']==1 and not out['tables']['fno_live_execution_events']['available']
    assert hashlib.sha256(db.read_bytes()).hexdigest()==before


def test_inventory_never_exports_private_event_details(tmp_path):
    c=sqlite3.connect(tmp_path/'cache.db');c.execute('CREATE TABLE fno_live_execution_events(at TEXT,kind TEXT,detail TEXT)');c.execute('INSERT INTO fno_live_execution_events VALUES(?,?,?)',('2024-01-02','entry_filled','PRIVATE_ACCOUNT_TOKEN'));c.commit();c.close()
    out=I.inventory(tmp_path);assert out['tables']['fno_live_execution_events']['counts_by_kind']=={'entry_filled':1}
    assert 'PRIVATE_ACCOUNT_TOKEN' not in json.dumps(out)


def test_missing_database_is_unavailable_never_created(tmp_path):
    with pytest.raises(sqlite3.OperationalError):I.inventory(tmp_path)
    assert not (tmp_path/'cache.db').exists()
