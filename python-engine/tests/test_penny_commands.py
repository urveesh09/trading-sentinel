"""
[PENNY-COMMANDS-TEST 2026-06-25] Tests for penny_commands (T3-B).

Pins:
- cmd_help() returns the command list
- cmd_skip() / cmd_unskip() persist to the override file (atomic write)
- cmd_skips() lists disabled tickers
- cmd_dispatch() routes commands correctly
- is_disabled() in penny_risk reads from the override file (so changes
  take effect on the next scanner cycle, not on container restart)
- Override file write is atomic (no partial-write corruption)
- Idempotency: cmd_skip(GOLDSTAR-SM) twice -> "already disabled"
- Fail-open: malformed override file = empty effective list
"""
import json
import os
import sqlite3
import tempfile

import pytest


# ---- helpers ---------------------------------------------------------

@pytest.fixture
def override_path(tmp_path):
    """Fresh override file per test. Also patches the settings default
    so penny_risk.is_disabled reads from this test's path."""
    p = tmp_path / "penny_disable_overrides.json"
    p.write_text('{"disabled": [], "enabled": []}')
    from config import settings
    settings_backup = settings.PENNY_DISABLE_OVERRIDES_PATH
    settings.PENNY_DISABLE_OVERRIDES_PATH = str(p)
    yield str(p)
    settings.PENNY_DISABLE_OVERRIDES_PATH = settings_backup


# ---- override file I/O ----------------------------------------------

def test_overrides_read_missing_file_returns_empty():
    """Fail-open: missing file = empty effective overrides."""
    from penny_commands import _read_overrides
    out = _read_overrides("/no/such/file.json")
    assert out["disabled"] == []
    assert out["enabled"] == []


def test_overrides_read_malformed_file_returns_empty():
    """Fail-open: malformed JSON = empty effective overrides."""
    import tempfile
    from penny_commands import _read_overrides
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{not valid json")
        path = f.name
    try:
        out = _read_overrides(path)
        assert out["disabled"] == []
    finally:
        os.unlink(path)


def test_overrides_read_normalises_case(override_path):
    """Symbols stored in lowercase or mixed case -> uppercased on read."""
    from penny_commands import _read_overrides
    with open(override_path, "w") as f:
        json.dump({"disabled": ["goldstar-sm", "RELIANCE"], "enabled": []}, f)
    out = _read_overrides(override_path)
    assert out["disabled"] == ["GOLDSTAR-SM", "RELIANCE"]


def test_overrides_write_is_atomic(override_path):
    """Write must use tmp+rename so a crash mid-write doesn't corrupt
    the file. We can verify by inspecting the file after write."""
    from penny_commands import _write_overrides, _read_overrides
    _write_overrides(override_path, {"disabled": ["AAA"], "enabled": []})
    assert os.path.exists(override_path)
    out = _read_overrides(override_path)
    assert out["disabled"] == ["AAA"]
    # No leftover .tmp file
    assert not os.path.exists(override_path + ".tmp")
    # _updated_at was stamped
    assert out["_updated_at"] is not None


# ---- cmd_skip / cmd_unskip / cmd_skips -----------------------------

def test_cmd_skip_adds_to_disable_list(override_path):
    from penny_commands import cmd_skip, _read_overrides
    reply = cmd_skip("GOLDSTAR-SM", path=override_path)
    assert "GOLDSTAR-SM" in reply
    assert "will be skipped" in reply.lower() or "✓" in reply
    out = _read_overrides(override_path)
    assert "GOLDSTAR-SM" in out["disabled"]


def test_cmd_skip_idempotent(override_path):
    """Skip twice -> 'already disabled' message, no error."""
    from penny_commands import cmd_skip
    r1 = cmd_skip("AAA", path=override_path)
    r2 = cmd_skip("AAA", path=override_path)
    assert "✓" in r1
    assert "already" in r2.lower()


def test_cmd_skip_lowercases_input(override_path):
    """Ticker case doesn't matter."""
    from penny_commands import cmd_skip, _read_overrides
    cmd_skip("reliance", path=override_path)
    out = _read_overrides(override_path)
    assert "RELIANCE" in out["disabled"]


def test_cmd_skip_empty_ticker_returns_usage(override_path):
    """Defensive: blank ticker = usage hint, not crash."""
    from penny_commands import cmd_skip
    r = cmd_skip("", path=override_path)
    assert "Usage" in r


def test_cmd_unskip_removes_from_disable_list(override_path):
    from penny_commands import cmd_skip, cmd_unskip, _read_overrides
    cmd_skip("AAA", path=override_path)
    cmd_unskip("AAA", path=override_path)
    out = _read_overrides(override_path)
    assert "AAA" not in out["disabled"]
    assert "AAA" in out["enabled"]   # tracked as 'enabled' for visibility


def test_cmd_unskip_idempotent_when_not_disabled(override_path):
    from penny_commands import cmd_unskip
    r = cmd_unskip("NEVER-DISABLED", path=override_path)
    assert "not in" in r.lower()


def test_cmd_skips_lists_disabled(override_path):
    from penny_commands import cmd_skip, cmd_skips
    cmd_skip("AAA", path=override_path)
    cmd_skip("BBB", path=override_path)
    out = cmd_skips(path=override_path)
    assert "AAA" in out
    assert "BBB" in out


def test_cmd_skips_empty(override_path):
    from penny_commands import cmd_skips
    out = cmd_skips(path=override_path)
    assert "empty" in out.lower()


# ---- cmd_help / dispatch -------------------------------------------

def test_cmd_help_lists_commands():
    from penny_commands import cmd_help
    out = cmd_help()
    assert "/penny stats" in out
    assert "/penny skip" in out
    assert "/penny unskip" in out
    assert "/penny regime" in out
    assert "/penny help" in out


def test_dispatch_routes_correctly(override_path, tmp_path):
    """dispatch() routes each subcommand to the right handler."""
    from penny_commands import dispatch
    db = str(tmp_path / "noop.db")  # stats/regime will read this; empty is fine
    assert "Penny commands" in dispatch("help", "", db)
    assert "Penny runtime disable list" in dispatch("skips", "", db)
    assert "will be skipped" in dispatch("skip", "AAA", db)
    assert "re-enabled" in dispatch("unskip", "AAA", db)


def test_dispatch_unknown_command_returns_help_hint(override_path, tmp_path):
    from penny_commands import dispatch
    out = dispatch("foobar", "", str(tmp_path / "noop.db"))
    assert "Unknown command" in out


def test_dispatch_empty_command_returns_help(override_path, tmp_path):
    from penny_commands import dispatch
    out = dispatch("", "", str(tmp_path / "noop.db"))
    assert "Penny commands" in out


# ---- is_disabled reads override file (integration with penny_risk) -

def test_penny_risk_is_disabled_checks_override_file(override_path, tmp_path):
    """penny_risk.is_disabled() reads the override file on every call.
    Writes take effect immediately (next scan, ~30s in prod)."""
    from penny_risk import PennyRiskEngine
    from penny_commands import cmd_skip, get_overridden_disabled_tickers
    r = PennyRiskEngine(bankroll=2500.0)

    # Initially: nothing disabled
    assert not r.is_disabled("GOLDSTAR-SM")

    # Simulate /penny skip GOLDSTAR-SM via Telegram
    cmd_skip("GOLDSTAR-SM", path=override_path)

    # Next scan call -> disabled
    assert r.is_disabled("GOLDSTAR-SM")


def test_penny_risk_is_disabled_combines_static_and_runtime(override_path):
    """Both PENNY_DISABLE_TICKERS (env var) AND the runtime override
    should disable -- source of truth is union."""
    from penny_risk import PennyRiskEngine
    from penny_commands import cmd_skip
    # Static: RELIANCE via env-var-style init
    r = PennyRiskEngine(bankroll=2500.0)
    r.disable_tickers = "RELIANCE"
    # Runtime: GOLDSTAR-SM via /penny skip
    cmd_skip("GOLDSTAR-SM", path=override_path)

    assert r.is_disabled("RELIANCE")        # static
    assert r.is_disabled("GOLDSTAR-SM")    # runtime
    assert not r.is_disabled("WIPRO")      # neither


def test_penny_risk_is_disabled_handles_lowercase(override_path):
    """Input symbol is normalised to uppercase."""
    from penny_risk import PennyRiskEngine
    from penny_commands import cmd_skip
    r = PennyRiskEngine(bankroll=2500.0)
    cmd_skip("aaa", path=override_path)
    assert r.is_disabled("aaa")        # lowercase input
    assert r.is_disabled("AAA")        # uppercase input
    assert r.is_disabled("Aaa")        # mixed case


# ---- end-to-end: dispatch + is_disabled ----------------------------

def test_end_to_end_skip_then_scan_excludes(override_path, tmp_path):
    """Full flow: /penny skip via dispatch -> scanner's is_disabled() returns True."""
    from penny_commands import dispatch
    from penny_risk import PennyRiskEngine

    # Simulate Telegram user typing "/penny skip GOLDSTAR-SM"
    reply = dispatch("skip", "GOLDSTAR-SM", str(tmp_path / "noop.db"))
    assert "✓" in reply

    # Scanner's risk engine now treats GOLDSTAR-SM as disabled
    r = PennyRiskEngine(bankroll=2500.0)
    assert r.is_disabled("GOLDSTAR-SM")

    # /penny skips shows it
    reply2 = dispatch("skips", "", str(tmp_path / "noop.db"))
    assert "GOLDSTAR-SM" in reply2

    # /penny unskip removes it
    reply3 = dispatch("unskip", "GOLDSTAR-SM", str(tmp_path / "noop.db"))
    assert "✓" in reply3
    assert not r.is_disabled("GOLDSTAR-SM")
