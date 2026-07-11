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


# ---- 2026-06-25 Tier 3 tests (T3-C: regime confidence reasons) -------

def test_confidence_reasons_empty_when_unchanged():
    """Engine with no compute yet -> reasons still include the
    '=> classified UNKNOWN' summary so the operator always gets
    a structured reply, never a blank one."""
    from penny_regime import PennyRegimeEngine
    # [TEST-POLLUTION-FIX 2026-07-10] PennyRegimeEngine became a real
    # singleton in the 2026-07-09 phase-2 audit fix, so "a fresh engine"
    # here is actually whatever state earlier test FILES left on the
    # shared instance (test_penny_audit_phase3_fixes and
    # test_penny_backtest both classify a regime). This test asserts the
    # no-compute-yet UNKNOWN state, so it must drop the singleton first
    # -- exactly what the class docstring prescribes for tests.
    PennyRegimeEngine.reset_state()
    re = PennyRegimeEngine()
    reasons = re.confidence_reasons()
    assert isinstance(reasons, list)
    # Should have at least the classification summary + breadth placeholder
    assert any("UNKNOWN" in r for r in reasons)


def test_confidence_reasons_for_pr1_calm():
    """Low vol + low VIX proxy = PR1_CALM."""
    from penny_regime import PennyRegimeEngine
    re = PennyRegimeEngine()
    re._vol_rank = 0.55    # < PR1 max 0.70
    re._vix_proxy = 0.40   # < PR1 max 0.70
    re._vix_distance = 0.02  # 2% above EMA
    re._breadth = 0.5
    re._today_regime = re.classify(re._vol_rank, re._vix_proxy)
    reasons = re.confidence_reasons()
    text = "\n".join(reasons)
    assert "PR1_CALM" in text
    assert "vol_rank=0.55" in text
    assert "vix_proxy=0.40" in text
    assert "below PR1 max" in text
    assert "calm" in text.lower()


def test_confidence_reasons_for_pr2_elevated():
    """vol_rank crossed PR1 -> PR2_ELEVATED."""
    from penny_regime import PennyRegimeEngine
    re = PennyRegimeEngine()
    re._vol_rank = 0.80    # > PR1 max 0.70, < PR2 max 0.90
    re._vix_proxy = 0.45
    re._vix_distance = -0.015
    re._breadth = 0.5
    re._today_regime = re.classify(re._vol_rank, re._vix_proxy)
    reasons = re.confidence_reasons()
    text = "\n".join(reasons)
    assert "PR2_ELEVATED" in text
    assert "between PR1 max 0.70 and PR2 max 0.90" in text


def test_confidence_reasons_for_pr3_hot():
    """vol_rank > PR2 max 0.90 = PR3_HOT."""
    from penny_regime import PennyRegimeEngine
    re = PennyRegimeEngine()
    re._vol_rank = 0.95    # > PR2 max 0.90
    re._vix_proxy = 0.50
    re._vix_distance = -0.05
    re._breadth = 0.5
    re._today_regime = re.classify(re._vol_rank, re._vix_proxy)
    reasons = re.confidence_reasons()
    text = "\n".join(reasons)
    assert "PR3_HOT" in text
    assert "PR3 threshold" in text or "PR2 max" in text


def test_confidence_reasons_vix_proxy_drives_pr3():
    """vol_rank calm but VIX proxy > 0.90 = PR3 (either input can drive)."""
    from penny_regime import PennyRegimeEngine
    re = PennyRegimeEngine()
    re._vol_rank = 0.30    # calm
    re._vix_proxy = 0.95   # > PR2 max -- drives PR3
    re._vix_distance = -0.12  # Nifty deeply below EMA
    re._breadth = 0.5
    re._today_regime = re.classify(re._vol_rank, re._vix_proxy)
    reasons = re.confidence_reasons()
    text = "\n".join(reasons)
    assert "PR3_HOT" in text
    assert "panic territory" in text.lower()
    # Raw distance surfaced
    assert "-12.0%" in text


def test_confidence_reasons_vol_rank_drives_pr2_vix_calm():
    """vix_proxy calm but vol_rank crosses PR1 -> PR2."""
    from penny_regime import PennyRegimeEngine
    re = PennyRegimeEngine()
    re._vol_rank = 0.75    # > PR1 max 0.70
    re._vix_proxy = 0.40   # calm
    re._vix_distance = 0.03
    re._breadth = 0.5
    re._today_regime = re.classify(re._vol_rank, re._vix_proxy)
    reasons = re.confidence_reasons()
    text = "\n".join(reasons)
    assert "PR2_ELEVATED" in text
    # VIX reason should say calm
    assert "calm" in text.lower() or "below PR1 max" in text


def test_confidence_reasons_vol_rank_missing():
    """vol_rank not yet fed -> 'unknown' reason, but still produce output."""
    from penny_regime import PennyRegimeEngine
    re = PennyRegimeEngine()
    re._vol_rank = None
    re._vix_proxy = 0.45
    re._vix_distance = 0.0
    re._breadth = 0.5
    re._today_regime = re.classify(re._vol_rank, re._vix_proxy)
    reasons = re.confidence_reasons()
    text = "\n".join(reasons)
    assert "vol_rank: unknown" in text


def test_confidence_reasons_vix_proxy_missing():
    """VIX proxy missing (Kite fetch failed) -> 'unknown' reason."""
    from penny_regime import PennyRegimeEngine
    re = PennyRegimeEngine()
    re._vol_rank = 0.55
    re._vix_proxy = None
    re._vix_distance = None
    re._breadth = 0.5
    re._today_regime = re.classify(re._vol_rank, re._vix_proxy)
    reasons = re.confidence_reasons()
    text = "\n".join(reasons)
    assert "vix_proxy: unknown" in text
    assert "fetch failed" in text


def test_confidence_reasons_includes_sizing_in_summary():
    """Final summary line shows the sizing implication."""
    from penny_regime import PennyRegimeEngine
    re = PennyRegimeEngine()
    re._vol_rank = 0.95
    re._vix_proxy = 0.50
    re._vix_distance = -0.05
    re._breadth = 0.5
    re._today_regime = re.classify(re._vol_rank, re._vix_proxy)
    reasons = re.confidence_reasons()
    text = "\n".join(reasons)
    # PR3 sizing is 0% -- all entries blocked
    assert "0.0% of bankroll per trade" in text or "sizing" in text


# ---- 2026-06-25 Tier 3 tests (T3-C: cmd_regime surfaces reasons) ------

def test_cmd_regime_surfaces_confidence_reasons(monkeypatch, override_path):
    """/penny regime now returns the full reason block, not just the label."""
    from penny_regime import PennyRegimeEngine
    import penny_commands
    # Build a fake engine with PR2_ELEVATED populated
    fake_engine = PennyRegimeEngine()
    fake_engine._vol_rank = 0.78
    fake_engine._vix_proxy = 0.62
    fake_engine._vix_distance = -0.025
    fake_engine._breadth = 0.5
    fake_engine._as_of = "2026-06-25"
    fake_engine._today_regime = fake_engine.classify(
        fake_engine._vol_rank, fake_engine._vix_proxy
    )
    # Monkey-patch the engine reference in main
    import main as _main
    monkeypatch.setattr(_main, "_penny_regime_engine", fake_engine)
    reply = penny_commands.cmd_regime("ignored.db")
    # Must contain the regime AND the reasons
    assert "PR2_ELEVATED" in reply
    assert "vol_rank=0.78" in reply
    assert "vix_proxy=0.62" in reply
    assert "between PR1 max" in reply
    assert "computed: 2026-06-25" in reply
    # Raw distance surfaced
    assert "-2.5%" in reply or "-3%" in reply


def test_cmd_regime_handles_uninitialized_engine(monkeypatch):
    """Engine = None -> 'engine not initialised yet' message."""
    import penny_commands
    import main as _main
    monkeypatch.setattr(_main, "_penny_regime_engine", None)
    reply = penny_commands.cmd_regime("ignored.db")
    assert "engine not initialised" in reply.lower()


def test_cmd_regime_handles_uncomputed_regime(monkeypatch):
    """Engine initialised but today_regime = None -> 'not yet computed' message."""
    from penny_regime import PennyRegimeEngine
    import penny_commands
    import main as _main
    fake = PennyRegimeEngine()
    # leave today_regime as default UNKNOWN; set as_of=None explicitly
    fake._today_regime = None  # type: ignore[assignment]
    monkeypatch.setattr(_main, "_penny_regime_engine", fake)
    reply = penny_commands.cmd_regime("ignored.db")
    assert "not yet computed" in reply.lower()


def test_cmd_regime_message_under_telegram_limit():
    """Even with full reasons, message stays under Telegram's 4096 char limit."""
    from penny_regime import PennyRegimeEngine
    import penny_commands
    import main as _main
    fake = PennyRegimeEngine()
    fake._vol_rank = 0.85
    fake._vix_proxy = 0.45
    fake._vix_distance = -0.034
    fake._breadth = 0.5
    fake._as_of = "2026-06-25"
    fake._today_regime = fake.classify(fake._vol_rank, fake._vix_proxy)
    penny_commands._main = _main  # ensure import works
    reply = penny_commands.cmd_regime("ignored.db")
    assert len(reply) < 4096
