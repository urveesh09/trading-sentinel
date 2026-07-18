"""
[PARTNER-TIPS-TESTS 2026-07-18] OI snapshot store (plan WS3): round-trip,
the >=09:25 open-baseline rule (early-session Kite OI is garbage), and
retention purge (disk at 86% -- purge is load-bearing).
"""
from datetime import date, datetime

import pytest
import pytz

import fno_oi_store as store
from fno_chain import ChainSnapshot
from fno_models import Contract, ContractQuote

IST = pytz.timezone("Asia/Kolkata")
EXPIRY = date(2026, 7, 23)


def _snap(ts: datetime, oi_ce: int = 1000, oi_pe: int = 2000, fut_oi: int = 50000):
    def q(strike, ot, oi):
        c = Contract(
            token=int(strike) * 10 + (1 if ot == "CE" else 2),
            tradingsymbol=f"NIFTY{int(strike)}{ot}", name="NIFTY",
            expiry=EXPIRY, strike=strike, instrument_type=ot, lot_size=75,
        )
        return ContractQuote(contract=c, bid=99, ask=101, ltp=100, oi=oi, volume=10)

    fut_c = Contract(token=900, tradingsymbol="NIFTYFUT", name="NIFTY",
                     expiry=EXPIRY, strike=0.0, instrument_type="FUT", lot_size=75)
    return ChainSnapshot(
        taken_at=ts, expiry=EXPIRY, forward=25000.0, parity_forward=None,
        lot_size=75,
        fut_quote=ContractQuote(contract=fut_c, ltp=25000.0, oi=fut_oi),
        quotes={
            (25000.0, "CE"): q(25000.0, "CE", oi_ce),
            (25000.0, "PE"): q(25000.0, "PE", oi_pe),
        },
    )


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / "oi.db")


@pytest.mark.asyncio
async def test_persist_and_latest_row(db):
    await store.init_oi_db(db)
    ts = IST.localize(datetime(2026, 7, 20, 10, 2))
    await store.persist_snapshot(db, "NIFTY", _snap(ts), pcr=1.2,
                                 max_pain=25000.0, atm_iv_val=0.14)
    row = await store.latest_fut_row(db, "NIFTY")
    assert row["snap_ts"] == "2026-07-20 10:02:00"
    assert row["pcr"] == pytest.approx(1.2)
    assert row["max_pain"] == 25000.0
    assert row["atm_iv"] == pytest.approx(0.14)
    assert row["fut_oi"] == 50000
    assert await store.latest_fut_row(db, "BANKNIFTY") is None


@pytest.mark.asyncio
async def test_persist_same_ts_replaces_not_raises(db):
    await store.init_oi_db(db)
    ts = IST.localize(datetime(2026, 7, 20, 10, 2))
    await store.persist_snapshot(db, "NIFTY", _snap(ts), 1.0, None, None)
    await store.persist_snapshot(db, "NIFTY", _snap(ts, oi_ce=1111), 1.1, None, None)
    row = await store.latest_fut_row(db, "NIFTY")
    assert row["pcr"] == pytest.approx(1.1)


@pytest.mark.asyncio
async def test_open_baseline_respects_0925_floor(db):
    await store.init_oi_db(db)
    early = IST.localize(datetime(2026, 7, 20, 9, 20))   # pre-floor: garbage OI
    good = IST.localize(datetime(2026, 7, 20, 9, 27))
    later = IST.localize(datetime(2026, 7, 20, 10, 2))
    await store.persist_snapshot(db, "NIFTY", _snap(early, oi_ce=1), 1.0, None, None)
    await store.persist_snapshot(db, "NIFTY", _snap(good, oi_ce=1000), 1.0, None, None)
    await store.persist_snapshot(db, "NIFTY", _snap(later, oi_ce=5000), 1.0, None, None)
    base = await store.open_baseline(db, "NIFTY", "2026-07-20")
    # the 09:27 snapshot, not 09:20 and not 10:02
    assert base[(25000.0, "CE")] == 1000


@pytest.mark.asyncio
async def test_open_baseline_empty_before_first_snapshot(db):
    await store.init_oi_db(db)
    assert await store.open_baseline(db, "NIFTY", "2026-07-20") == {}


@pytest.mark.asyncio
async def test_first_fut_row_today(db):
    await store.init_oi_db(db)
    early = IST.localize(datetime(2026, 7, 20, 9, 20))
    good = IST.localize(datetime(2026, 7, 20, 9, 27))
    await store.persist_snapshot(db, "NIFTY", _snap(early), 0.5, None, None)
    await store.persist_snapshot(db, "NIFTY", _snap(good), 0.9, None, None)
    row = await store.first_fut_row_today(db, "NIFTY", "2026-07-20")
    assert row["snap_ts"] == "2026-07-20 09:27:00"
    assert row["pcr"] == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_latest_before_ts(db):
    await store.init_oi_db(db)
    t1 = IST.localize(datetime(2026, 7, 20, 10, 2))
    t2 = IST.localize(datetime(2026, 7, 20, 10, 7))
    await store.persist_snapshot(db, "NIFTY", _snap(t1), 1.0, None, None)
    await store.persist_snapshot(db, "NIFTY", _snap(t2), 2.0, None, None)
    row = await store.latest_fut_row(db, "NIFTY", before_ts="2026-07-20 10:07:00")
    assert row["snap_ts"] == "2026-07-20 10:02:00"


@pytest.mark.asyncio
async def test_purge_older_than(db):
    await store.init_oi_db(db)
    old = IST.localize(datetime(2026, 7, 1, 10, 0))
    new = IST.localize(datetime(2026, 7, 20, 10, 0))
    await store.persist_snapshot(db, "NIFTY", _snap(old), 1.0, None, None)
    await store.persist_snapshot(db, "NIFTY", _snap(new), 2.0, None, None)
    removed = await store.purge_older_than(
        db, days=7, now=datetime(2026, 7, 20, 16, 0)
    )
    assert removed == 2   # 2 chain rows from the old snapshot
    assert await store.first_fut_row_today(db, "NIFTY", "2026-07-01") is None
    assert (await store.latest_fut_row(db, "NIFTY"))["pcr"] == pytest.approx(2.0)
