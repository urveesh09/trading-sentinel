"""[HALT 2026-08-05] Tests for the filesystem kill switch.

The properties that matter are the failure modes, not the happy path. A kill
switch that works when everything is fine is not a kill switch.
"""
import json
import os
import stat
from unittest.mock import patch

import pytest

import halt_switch


@pytest.fixture
def halt_dir(tmp_path, monkeypatch):
    """Point the module at a temp dir instead of /data."""
    monkeypatch.setattr(halt_switch, "HALT_DIR", str(tmp_path))
    return tmp_path


# ── the basic contract ────────────────────────────────────────────────────

def test_no_sentinel_means_not_halted(halt_dir):
    halted, attribution = halt_switch.halt_state()
    assert halted is False
    assert attribution is None


def test_trip_then_state_is_halted(halt_dir):
    halt_switch.trip("daily loss limit", by="circuit_breaker")
    halted, attribution = halt_switch.halt_state()
    assert halted is True
    assert attribution["reason"] == "daily loss limit"
    assert attribution["by"] == "circuit_breaker"
    assert attribution["scope"] == "global"


def test_clear_removes_the_halt(halt_dir):
    halt_switch.trip("test")
    assert halt_switch.clear() is True
    assert halt_switch.halt_state()[0] is False


def test_clear_when_nothing_set_returns_false(halt_dir):
    assert halt_switch.clear() is False


def test_assert_not_halted_raises_with_attribution(halt_dir):
    halt_switch.trip("bad fills", by="operator")
    with pytest.raises(halt_switch.TradingHalted) as exc:
        halt_switch.assert_not_halted()
    assert "bad fills" in str(exc.value)
    assert exc.value.attribution["by"] == "operator"


# ── the point of the module: contents can never un-halt ───────────────────

def test_touched_empty_file_still_halts(halt_dir):
    """`docker exec python-engine touch /data/HALT` must work."""
    (halt_dir / "HALT").write_text("")
    halted, attribution = halt_switch.halt_state()
    assert halted is True
    assert attribution["by"] == "manual_file"


def test_corrupt_json_still_halts(halt_dir):
    (halt_dir / "HALT").write_text("{not json at all")
    assert halt_switch.halt_state()[0] is True


def test_json_that_is_not_an_object_still_halts(halt_dir):
    (halt_dir / "HALT").write_text('["halted", false]')
    halted, attribution = halt_switch.halt_state()
    assert halted is True
    assert attribution["by"] == "manual_file"


def test_payload_claiming_not_halted_is_ignored(halt_dir):
    """Existence is the halt. A payload cannot argue with it."""
    (halt_dir / "HALT").write_text(json.dumps({"halted": False, "active": False}))
    assert halt_switch.halt_state()[0] is True


def test_unreadable_sentinel_fails_closed(halt_dir):
    """A stat() error that is not ENOENT must read as HALTED, not as clear.

    This is the fail-open that os.path.exists() would have introduced: it
    swallows EACCES/EIO into False.
    """
    with patch("halt_switch.os.stat", side_effect=PermissionError("EACCES")):
        halted, attribution = halt_switch.halt_state()
    assert halted is True
    assert attribution["unreadable"] is True


# ── scope ─────────────────────────────────────────────────────────────────

def test_channel_sentinel_halts_only_that_channel(halt_dir):
    halt_switch.trip("penny only", channel="penny")
    assert halt_switch.halt_state("penny")[0] is True
    assert halt_switch.halt_state("momentum")[0] is False
    assert halt_switch.halt_state()[0] is False


def test_global_sentinel_wins_over_a_clear_channel(halt_dir):
    halt_switch.trip("everything")
    for channel in ("penny", "momentum", "fno"):
        halted, attribution = halt_switch.halt_state(channel)
        assert halted is True
        assert attribution["scope"] == "global"


def test_channel_state_ignores_the_global_sentinel(halt_dir):
    """The status display must show what a global clear would leave behind."""
    halt_switch.trip("global reason")
    halt_switch.trip("penny reason", channel="penny")

    assert halt_switch.channel_state("penny")[0] is True
    assert halt_switch.channel_state("momentum")[0] is False
    # ...even though the enforcement view says everything is halted.
    assert halt_switch.halt_state("momentum")[0] is True


def test_clearing_global_leaves_channel_halt_intact(halt_dir):
    halt_switch.trip("global")
    halt_switch.trip("penny", channel="penny")
    halt_switch.clear()
    assert halt_switch.halt_state("momentum")[0] is False
    assert halt_switch.halt_state("penny")[0] is True


# ── path safety ───────────────────────────────────────────────────────────

def test_channel_name_cannot_escape_the_halt_dir(halt_dir):
    path = halt_switch.sentinel_path("../../etc/passwd")
    assert os.path.dirname(os.path.abspath(path)) == str(halt_dir)


def test_channel_that_sanitises_to_empty_is_rejected(halt_dir):
    """Must not silently collapse into the GLOBAL sentinel."""
    with pytest.raises(ValueError):
        halt_switch.sentinel_path("///")


def test_invalid_channel_fails_closed_in_halt_state(halt_dir):
    halted, attribution = halt_switch.halt_state("///")
    assert halted is True
    assert "invalid halt channel" in attribution["reason"]


# ── trip semantics ────────────────────────────────────────────────────────

def test_retrip_preserves_the_first_reason(halt_dir):
    """The first trip is the diagnostic one; an aftershock must not erase it."""
    first = halt_switch.trip("daily loss", by="circuit_breaker")
    second = halt_switch.trip("drawdown", by="circuit_breaker")
    assert second["reason"] == "daily loss"
    assert second["tripped_at"] == first["tripped_at"]


def test_trip_writes_atomically_leaving_no_temp_files(halt_dir):
    halt_switch.trip("test")
    leftovers = [p.name for p in halt_dir.iterdir() if p.name.startswith(".halt-")]
    assert leftovers == []


def test_trip_raises_when_the_sentinel_cannot_be_written(halt_dir):
    """A kill switch that silently fails to engage is worse than none."""
    with patch("halt_switch.tempfile.mkstemp", side_effect=OSError("ENOSPC")):
        with pytest.raises(OSError):
            halt_switch.trip("test")


def test_reason_is_truncated_not_rejected(halt_dir):
    payload = halt_switch.trip("x" * 5000)
    assert len(payload["reason"]) == 500


# ── describe ──────────────────────────────────────────────────────────────

def test_describe_when_armed(halt_dir):
    assert "ARMED" in halt_switch.describe()


def test_describe_when_halted_names_the_reason(halt_dir):
    halt_switch.trip("daily loss limit", by="circuit_breaker")
    text = halt_switch.describe()
    assert "HALTED" in text
    assert "daily loss limit" in text
    assert "circuit_breaker" in text
