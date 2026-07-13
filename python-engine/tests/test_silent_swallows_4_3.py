"""[ROADMAP-4.3 2026-07-13] Witness tests for the silent-swallow fixes.

Every test here fails against the pre-fix code. The shared theme is not
"an exception was ignored" -- it is that ignoring it made a BROKEN system
render identically to a HEALTHY one:

  - a positions table missing its migration  == a normal positions table
  - a database that cannot be read           == a genuinely flat book
  - a P&L query that blew up                 == a flat P&L day

Each of those is a lie told to the operator in the exact number they use
to decide whether to put more money at risk. The 2026-07-13 outage is the
proof case: a full disk made every SQLite call raise, and the bare
`except Exception: pass` sites turned that into silence.
"""
import sqlite3
import sqlite3 as _sqlite3

import pytest

import nifty_commands
import penny_commands
from position_tracker import init_positions_db

# _add_column_if_missing is imported lazily inside the tests that need it,
# NOT at module scope. At module scope, running this file against the
# pre-fix code raises ImportError during collection, which aborts the whole
# module -- and that would hide whether the two behavioural witnesses below
# (penny "?" / nifty "UNKNOWN") actually fail without their fix. A witness
# suite has to be observable failing, so it must stay importable.


# ===================================================================
# position_tracker: ALTER TABLE migrations
# ===================================================================

class _FakeDB:
    """Minimal aiosqlite-ish stub whose execute() raises what we choose."""

    def __init__(self, exc: Exception | None = None):
        self.exc = exc
        self.calls: list[str] = []

    async def execute(self, sql, *a, **kw):
        self.calls.append(sql)
        if self.exc is not None:
            raise self.exc
        return None


@pytest.mark.asyncio
async def test_duplicate_column_is_swallowed():
    """The one benign outcome: the column is already there. Steady state on
    every boot after the first, so it must stay silent and not raise."""
    from position_tracker import _add_column_if_missing

    db = _FakeDB(sqlite3.OperationalError("duplicate column name: t1_fired"))
    await _add_column_if_missing(db, "t1_fired", "INTEGER DEFAULT 0")  # no raise


@pytest.mark.asyncio
async def test_disk_io_error_during_migration_is_NOT_swallowed():
    """THE 2026-07-13 WITNESS.

    When the disk filled, every SQLite call in the engine raised
    `disk I/O error`. Pre-fix this ALTER TABLE was wrapped in
    `except Exception: pass`, so the migration would be skipped in silence
    and the engine would carry on with a positions table missing
    atr_1min_post_t1 -- which evaluate_connors_exit then reads as 0.0,
    collapsing the CNC post-T1 trailing stop to a hard floor at
    breakeven+0.5%. Real exits, at wrong prices, with no error anywhere.

    A broken disk must be loud.
    """
    from position_tracker import _add_column_if_missing

    db = _FakeDB(sqlite3.OperationalError("disk I/O error"))
    with pytest.raises(sqlite3.OperationalError, match="disk I/O error"):
        await _add_column_if_missing(db, "atr_1min_post_t1", "REAL")


@pytest.mark.asyncio
async def test_migrations_are_idempotent_against_a_real_db(tmp_path):
    """Belt and braces: init twice against a real sqlite file. The second
    call hits 'duplicate column name' for every migration and must be a
    no-op, not an error."""
    db_path = str(tmp_path / "cache.db")
    await init_positions_db(db_path)
    await init_positions_db(db_path)  # must not raise

    con = sqlite3.connect(db_path)
    cols = {r[1] for r in con.execute("PRAGMA table_info(positions)")}
    con.close()
    # The columns the exit logic depends on must actually exist.
    assert {"product_type", "regime_at_entry",
            "atr_1min_post_t1", "t1_fired"} <= cols


# ===================================================================
# penny_commands: "open: 0" vs "open: ?"
# ===================================================================

def test_penny_stats_reports_unknown_not_zero_when_positions_unreadable(tmp_path):
    """Pre-fix, a dead database rendered 'Open positions: 0' -- identical to
    a genuinely flat book, and precisely the reading an operator would use
    to justify opening new risk while the engine still holds stock it can
    no longer see.

    An empty DB file reproduces it honestly: the count query raises
    `no such table: positions`, the same sqlite3.Error class the disk-full
    outage produced.
    """
    db_path = str(tmp_path / "cache.db")
    _sqlite3.connect(db_path).close()  # exists, but has no tables

    out = penny_commands.cmd_stats(db_path)

    assert "Open positions: ?" in out, f"expected an explicit unknown, got:\n{out}"
    assert "Open positions: 0" not in out


# ===================================================================
# nifty_commands: "Deployed: Rs 0" vs "Deployed: UNKNOWN"
# ===================================================================

def test_nifty_stats_reports_unknown_deployed_when_positions_unreadable(
    tmp_path, monkeypatch
):
    """Same lie, different subsystem: a failed position read rendered
    'Deployed: Rs 0 (0.0% util)' -- i.e. "you have full capacity, go ahead".

    cmd_nifty_stats imports get_open_positions INSIDE the function, so the
    patch has to land on the source module, not on nifty_commands.
    """
    import position_tracker

    db_path = str(tmp_path / "cache.db")

    async def boom(_db_path):
        raise RuntimeError("positions table is gone")

    monkeypatch.setattr(position_tracker, "get_open_positions", boom)

    out = nifty_commands.cmd_nifty_stats(db_path)

    assert "Deployed: UNKNOWN" in out, f"expected UNKNOWN deployed, got:\n{out}"
    assert "0.0% util" not in out
