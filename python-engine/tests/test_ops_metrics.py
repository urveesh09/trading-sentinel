"""
[ROADMAP-2.8 2026-07-12] Persistent ops metrics time-series.

ops_liveness_daily: per-day scheduler-tick gaps (the F&O go-live
liveness attestation, replacing the rule-62 log grep).
ops_funnel_daily: per-day per-subsystem accept/reject counts that
survive log rotation.
"""
import json
from datetime import datetime, timedelta

import aiosqlite
import pytest

import ops_metrics
from ops_metrics import (
    IST,
    _gap_overlaps_market,
    funnel_window,
    init_ops_metrics_db,
    liveness_report,
    record_scheduler_tick,
    snapshot_funnels_for_day,
)


def _ist(y, mo, d, h, mi, s=0):
    return IST.localize(datetime(y, mo, d, h, mi, s))


async def _seed_liveness(db_path, rows):
    """rows: (date_ist, ticks, max_gap, max_gap_market)"""
    async with aiosqlite.connect(db_path) as db:
        await db.executemany(
            "INSERT INTO ops_liveness_daily VALUES (?, ?, ?, ?, 'test')",
            rows,
        )
        await db.commit()


# ===============================================================
# Init
# ===============================================================

@pytest.mark.asyncio
async def test_init_is_idempotent(db_path):
    await init_ops_metrics_db(db_path)
    await init_ops_metrics_db(db_path)
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE 'ops_%' ORDER BY name"
        ) as cur:
            names = [r[0] for r in await cur.fetchall()]
    assert names == ["ops_funnel_daily", "ops_liveness_daily"]


# ===============================================================
# Market-hours overlap (pure)
# ===============================================================

class TestGapOverlapsMarket:
    def test_gap_inside_session_counts(self):
        # Wed 2026-07-08, 60s gap ending 11:00 IST
        assert _gap_overlaps_market(_ist(2026, 7, 8, 11, 0), 60.0) is True

    def test_gap_at_night_does_not_count(self):
        assert _gap_overlaps_market(_ist(2026, 7, 8, 3, 0), 60.0) is False

    def test_weekend_gap_does_not_count(self):
        # Sat 2026-07-11
        assert _gap_overlaps_market(_ist(2026, 7, 11, 11, 0), 3600.0) is False

    def test_gap_ending_just_after_open_counts(self):
        # 08:00 -> 09:16 spans the open
        assert _gap_overlaps_market(_ist(2026, 7, 8, 9, 16), 4560.0) is True

    def test_overnight_freeze_into_next_session_counts(self):
        # Wed 16:00 -> Thu 09:20: the freeze ate Thursday's open.
        assert _gap_overlaps_market(
            _ist(2026, 7, 9, 9, 20), 17.33 * 3600
        ) is True

    def test_post_close_to_pre_open_gap_does_not_count(self):
        # Wed 15:35 -> Wed 20:35: entirely outside the session.
        assert _gap_overlaps_market(_ist(2026, 7, 8, 20, 35), 5 * 3600.0) is False


# ===============================================================
# record_scheduler_tick
# ===============================================================

class TestRecordSchedulerTick:
    """[2026-07-13] Every test here seeds a tick on a LITERAL date, so the
    report window must be anchored to a literal date too (`_ANCHOR`).

    The original versions called liveness_report(days=5) with no anchor,
    which silently used the wall clock. They passed on 2026-07-12 and
    failed on 2026-07-13 -- the seeded 2026-07-08 tick simply aged out of
    a window that kept sliding forward while the seed date stood still.
    A test whose result depends on the day you run it is not a test."""

    # One day after the seeded ticks, so a 5-day window comfortably
    # contains 2026-07-08 no matter when the suite is run.
    _ANCHOR = _ist(2026, 7, 9, 18, 0)

    @pytest.mark.asyncio
    async def test_first_tick_creates_row_without_gap(self, db_path):
        await init_ops_metrics_db(db_path)
        await record_scheduler_tick(db_path, _ist(2026, 7, 8, 11, 0), None)
        report = await liveness_report(db_path, days=5, now_ist=self._ANCHOR)
        assert report["days_covered"] == 1
        row = report["rows"][0]
        assert row == {
            "date_ist": "2026-07-08", "ticks": 1,
            "max_gap_seconds": 0.0, "max_gap_market_seconds": 0.0,
        }

    @pytest.mark.asyncio
    async def test_market_hours_gap_recorded_in_both_columns(self, db_path):
        await init_ops_metrics_db(db_path)
        await record_scheduler_tick(db_path, _ist(2026, 7, 8, 11, 0), None)
        await record_scheduler_tick(db_path, _ist(2026, 7, 8, 11, 2), 120.0)
        row = (await liveness_report(
            db_path, days=5, now_ist=self._ANCHOR))["rows"][0]
        assert row["ticks"] == 2
        assert row["max_gap_seconds"] == 120.0
        assert row["max_gap_market_seconds"] == 120.0

    @pytest.mark.asyncio
    async def test_night_gap_only_in_total_column(self, db_path):
        """A 65-min gap at 03:00 must not dirty the market-hours record
        the go-live gate reads."""
        await init_ops_metrics_db(db_path)
        await record_scheduler_tick(db_path, _ist(2026, 7, 8, 3, 0), 3900.0)
        row = (await liveness_report(
            db_path, days=5, now_ist=self._ANCHOR))["rows"][0]
        assert row["max_gap_seconds"] == 3900.0
        assert row["max_gap_market_seconds"] == 0.0

    @pytest.mark.asyncio
    async def test_max_is_kept_not_last(self, db_path):
        await init_ops_metrics_db(db_path)
        await record_scheduler_tick(db_path, _ist(2026, 7, 8, 11, 0), 400.0)
        await record_scheduler_tick(db_path, _ist(2026, 7, 8, 11, 5), 60.0)
        row = (await liveness_report(
            db_path, days=5, now_ist=self._ANCHOR))["rows"][0]
        assert row["max_gap_seconds"] == 400.0

    @pytest.mark.asyncio
    async def test_never_raises_on_missing_db_dir(self, tmp_path):
        await record_scheduler_tick(
            str(tmp_path / "nope" / "cache.db"), _ist(2026, 7, 8, 11, 0), 60.0
        )  # must not raise

    @pytest.mark.asyncio
    async def test_window_is_exclusive_at_the_far_edge(self, db_path):
        """Pins the (since, today] boundary that the rotting tests tripped
        over. A `days`-day window must yield AT MOST `days` rows, because
        market_gap_clean gates on `len(rows) >= days` -- if the far edge
        were inclusive, a 30-day window could return 31 rows and the F&O
        go-live attestation would pass a day early."""
        await init_ops_metrics_db(db_path)
        anchor = _ist(2026, 7, 13, 12, 0)
        # Seed one tick per day for 2026-07-08 .. 2026-07-13 (6 days).
        for day in range(8, 14):
            await record_scheduler_tick(db_path, _ist(2026, 7, day, 11, 0), None)

        report = await liveness_report(db_path, days=5, now_ist=anchor)
        dates = [r["date_ist"] for r in report["rows"]]

        # since = 2026-07-08; strictly-greater excludes it.
        assert dates == ["2026-07-09", "2026-07-10", "2026-07-11",
                         "2026-07-12", "2026-07-13"]
        assert report["days_covered"] == 5
        assert len(dates) <= 5


# ===============================================================
# liveness_report summary (the go-live attestation)
# ===============================================================

class TestLivenessReport:
    @pytest.mark.asyncio
    async def test_clean_window(self, db_path):
        await init_ops_metrics_db(db_path)
        today = datetime.now(IST).date()
        rows = [
            ((today - timedelta(days=i)).strftime("%Y-%m-%d"), 1440, 61.0, 61.0)
            for i in range(30)
        ]
        await _seed_liveness(db_path, rows)
        report = await liveness_report(db_path, days=30)
        assert report["days_covered"] == 30
        assert report["market_gap_clean"] is True

    @pytest.mark.asyncio
    async def test_one_market_freeze_dirties_window(self, db_path):
        await init_ops_metrics_db(db_path)
        today = datetime.now(IST).date()
        rows = [
            ((today - timedelta(days=i)).strftime("%Y-%m-%d"), 1440, 61.0, 61.0)
            for i in range(30)
        ]
        await _seed_liveness(db_path, rows)
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "UPDATE ops_liveness_daily SET max_gap_market_seconds = 400.0 "
                "WHERE date_ist = ?",
                ((today - timedelta(days=10)).strftime("%Y-%m-%d"),),
            )
            await db.commit()
        report = await liveness_report(db_path, days=30)
        assert report["worst_market_gap_seconds"] == 400.0
        assert report["market_gap_clean"] is False

    @pytest.mark.asyncio
    async def test_partial_coverage_is_not_clean(self, db_path):
        """5 clean days cannot attest a 30-day window."""
        await init_ops_metrics_db(db_path)
        today = datetime.now(IST).date()
        rows = [
            ((today - timedelta(days=i)).strftime("%Y-%m-%d"), 1440, 61.0, 61.0)
            for i in range(5)
        ]
        await _seed_liveness(db_path, rows)
        report = await liveness_report(db_path, days=30)
        assert report["days_covered"] == 5
        assert report["market_gap_clean"] is False


# ===============================================================
# Funnel snapshots
# ===============================================================

async def _seed_signals(db_path):
    """Minimal momentum/penny/fno rows across an IST day boundary."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """CREATE TABLE momentum_signals (
                scan_id TEXT, scanned_at TEXT, ticker TEXT,
                accepted INTEGER, reject_reason TEXT)"""
        )
        await db.execute(
            """CREATE TABLE penny_signals (
                scan_id TEXT, scanned_at TEXT, ticker TEXT,
                accepted INTEGER, reject_reason TEXT)"""
        )
        await db.execute(
            """CREATE TABLE fno_signals (
                scan_id TEXT, bar_ts TEXT,
                accepted INTEGER, reject_reason TEXT)"""
        )
        # 2026-07-08 IST spans 2026-07-07T18:30Z .. 2026-07-08T18:30Z.
        await db.executemany(
            "INSERT INTO momentum_signals VALUES (?, ?, ?, ?, ?)",
            [
                ("s1", "2026-07-08T05:00:00+00:00", "AAA", 1, ""),
                ("s1", "2026-07-08T05:00:00+00:00", "BBB", 0, "MC3_volume_surge_insufficient"),
                ("s1", "2026-07-08T09:00:00+00:00", "CCC", 0, "MC3_volume_surge_insufficient"),
                # 18:45Z = 00:15 IST NEXT day: must not leak into 07-08.
                ("s2", "2026-07-08T18:45:00+00:00", "DDD", 0, "MC1_no_vwap_reclaim"),
            ],
        )
        await db.executemany(
            "INSERT INTO penny_signals VALUES (?, ?, ?, ?, ?)",
            [
                # Per-ticker numbers must collapse to one 'volume' bucket.
                ("p1", "2026-07-08T05:00:00+00:00", "PEN1", 0, "volume 123 < 456"),
                ("p1", "2026-07-08T05:10:00+00:00", "PEN2", 0, "volume 99 < 500"),
            ],
        )
        await db.executemany(
            "INSERT INTO fno_signals VALUES (?, ?, ?, ?)",
            [
                ("f1", "2026-07-08T10:15:00", 0, "pool_below_min_viable"),
                ("f1", "2026-07-08T10:30:00", 1, ""),
                ("f2", "2026-07-09T10:15:00", 0, "pool_below_min_viable"),
            ],
        )
        await db.commit()


class TestSnapshotFunnels:
    @pytest.mark.asyncio
    async def test_counts_and_histograms_per_subsystem(self, db_path):
        await init_ops_metrics_db(db_path)
        await _seed_signals(db_path)
        written = await snapshot_funnels_for_day(db_path, "2026-07-08")
        assert written == {"momentum": 3, "penny": 2, "fno": 2}
        rows = {r["subsystem"]: r for r in await funnel_window(db_path, days=365)}
        mom = rows["momentum"]
        assert (mom["accepted"], mom["rejected"]) == (1, 2)
        assert mom["top_rejects"] == {"MC3_volume_surge_insufficient": 2}
        assert rows["penny"]["top_rejects"] == {"volume": 2}
        fno = rows["fno"]
        assert (fno["evaluated"], fno["accepted"]) == (2, 1)

    @pytest.mark.asyncio
    async def test_ist_day_boundary_respected(self, db_path):
        """The 18:45Z momentum row is 00:15 IST on 07-09 -- it belongs to
        the NEXT day's snapshot (a UTC-date bucket would misfile it, the
        penny kill-switch UTC bug class)."""
        await init_ops_metrics_db(db_path)
        await _seed_signals(db_path)
        await snapshot_funnels_for_day(db_path, "2026-07-08")
        written = await snapshot_funnels_for_day(db_path, "2026-07-09")
        assert written["momentum"] == 1
        rows = await funnel_window(db_path, days=365)
        d9_mom = [
            r for r in rows
            if r["date_ist"] == "2026-07-09" and r["subsystem"] == "momentum"
        ][0]
        assert d9_mom["top_rejects"] == {"MC1_no_vwap_reclaim": 1}

    @pytest.mark.asyncio
    async def test_zero_evaluation_day_writes_a_row(self, db_path):
        """'The scanner never ran' must be a visible 0-row, not absence."""
        await init_ops_metrics_db(db_path)
        await _seed_signals(db_path)
        written = await snapshot_funnels_for_day(db_path, "2026-01-01")
        assert written == {"momentum": 0, "penny": 0, "fno": 0}
        rows = [
            r for r in await funnel_window(db_path, days=365)
            if r["date_ist"] == "2026-01-01"
        ]
        assert len(rows) == 3
        assert all(r["evaluated"] == 0 for r in rows)

    @pytest.mark.asyncio
    async def test_missing_tables_skipped_not_fatal(self, db_path):
        """Fresh DB with no signal tables: snapshot writes nothing and
        does not raise (subsystem not initialised yet)."""
        await init_ops_metrics_db(db_path)
        written = await snapshot_funnels_for_day(db_path, "2026-07-08")
        assert written == {}

    @pytest.mark.asyncio
    async def test_rerun_is_idempotent_upsert(self, db_path):
        await init_ops_metrics_db(db_path)
        await _seed_signals(db_path)
        await snapshot_funnels_for_day(db_path, "2026-07-08")
        await snapshot_funnels_for_day(db_path, "2026-07-08")
        async with aiosqlite.connect(db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM ops_funnel_daily WHERE date_ist = '2026-07-08'"
            ) as cur:
                (n,) = await cur.fetchone()
        assert n == 3


# ===============================================================
# Wiring: scheduler tick job feeds the liveness table
# ===============================================================

@pytest.mark.asyncio
async def test_scheduler_tick_job_records_liveness(db_path, monkeypatch):
    import main as main_module
    from config import settings

    monkeypatch.setattr(settings, "DB_PATH", db_path)
    monkeypatch.setitem(
        main_module._scheduler_tick_state, "prev_monotonic", None
    )
    await init_ops_metrics_db(db_path)
    await main_module._scheduler_tick_job()
    await main_module._scheduler_tick_job()
    report = await liveness_report(db_path, days=2)
    assert report["days_covered"] == 1
    assert report["rows"][0]["ticks"] == 2


# ===============================================================
# GET /ops/metrics
# ===============================================================

@pytest.mark.asyncio
async def test_ops_metrics_endpoint_requires_secret(db_path, monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from config import settings
    from main import app

    monkeypatch.setattr(settings, "DB_PATH", db_path)
    await init_ops_metrics_db(db_path)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/ops/metrics")
        assert resp.status_code == 403
        resp = await ac.get(
            "/ops/metrics",
            headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "liveness" in body and "funnel" in body
        assert body["liveness"]["market_gap_clean"] is False  # empty window
