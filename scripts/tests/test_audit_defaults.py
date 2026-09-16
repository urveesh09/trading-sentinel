"""[WORKFLOW-D.2.a-flags 2026-09-16] Tests for the
defaults + runtime config-flags audit tool.

Per Workstream D item 2 in NEXT_AGENT_PLAN.md:
> 2. Review migrations, defaults, flags and Docker volumes.

The audit script walks the ``Settings`` class and
classifies every default into SAFE / RISKY / INFRASTRUCTURE
tiers. These tests pin the classifier contract and the
CLI behaviour.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")
ENGINE_DIR_STR = os.path.join(REPO_ROOT, "python-engine")
ENGINE_DIR = Path(ENGINE_DIR_STR)  # Path object for path operations.

# Import audit_defaults via importlib (same pattern as
# test_audit_migrations.py -- the scripts/ tree has no
# __init__.py, so direct import breaks pytest's collector).
# We must register the module in sys.modules BEFORE exec --
# dataclass decorator needs to look up the module via
# ``sys.modules[cls.__module__].__dict__``.
_spec = importlib.util.spec_from_file_location(
    "audit_defaults", os.path.join(SCRIPTS_DIR, "audit_defaults.py"),
)
audit_defaults = importlib.util.module_from_spec(_spec)
sys.modules["audit_defaults"] = audit_defaults
_spec.loader.exec_module(audit_defaults)


# ─── Tier classification ──────────────────────────────


def test_safe_small_numeric_default():
    """A small numeric default is SAFE."""
    tier, _ = audit_defaults._classify("INITIAL_BANKROLL", 4500.0)
    assert tier == audit_defaults.RiskTier.SAFE


def test_safe_bool_default():
    """A boolean default is SAFE (it's not a numeric cap)."""
    tier, _ = audit_defaults._classify("FOO_ENABLED", True)
    assert tier == audit_defaults.RiskTier.SAFE


def test_risky_large_numeric_default():
    """A numeric default >= 100_000 is RISKY."""
    tier, _ = audit_defaults._classify("PENNY_PAPER_BANKROLL", 100000.0)
    assert tier == audit_defaults.RiskTier.RISKY


def test_risky_disable_token():
    """A name containing ``DISABLE_`` is RISKY."""
    tier, _ = audit_defaults._classify("PENNY_EDGE_DISABLE_LIVE", True)
    assert tier == audit_defaults.RiskTier.RISKY


def test_risky_allow_token():
    """A name containing ``ALLOW_`` is RISKY."""
    tier, _ = audit_defaults._classify("MOMENTUM_ALLOW_OVERNIGHT", False)
    assert tier == audit_defaults.RiskTier.RISKY


def test_risky_bypass_token():
    """A name containing ``BYPASS_`` is RISKY."""
    tier, _ = audit_defaults._classify("SAFETY_BYPASS_ENABLED", True)
    assert tier == audit_defaults.RiskTier.RISKY


def test_risky_force_token():
    """A name containing ``FORCE_`` is RISKY."""
    tier, _ = audit_defaults._classify("FORCE_TRADE", False)
    assert tier == audit_defaults.RiskTier.RISKY


def test_risky_override_token():
    """A name containing ``OVERRIDE_`` is RISKY."""
    tier, _ = audit_defaults._classify("OVERRIDE_RISK", False)
    assert tier == audit_defaults.RiskTier.RISKY


def test_infrastructure_path_token():
    """A name containing ``PATH`` is INFRASTRUCTURE."""
    tier, _ = audit_defaults._classify("DATA_PATH", "/data/cache.db")
    assert tier == audit_defaults.RiskTier.INFRASTRUCTURE


def test_infrastructure_url_token():
    """A name containing ``URL`` is INFRASTRUCTURE."""
    tier, _ = audit_defaults._classify("ENGINE_URL", "http://localhost:8000")
    assert tier == audit_defaults.RiskTier.INFRASTRUCTURE


def test_infrastructure_host_token():
    """A name containing ``HOST`` is INFRASTRUCTURE."""
    tier, _ = audit_defaults._classify("REDIS_HOST", "localhost")
    assert tier == audit_defaults.RiskTier.INFRASTRUCTURE


def test_infrastructure_log_level_token():
    """A name containing ``LOG_LEVEL`` is INFRASTRUCTURE."""
    tier, _ = audit_defaults._classify("LOG_LEVEL", "INFO")
    assert tier == audit_defaults.RiskTier.INFRASTRUCTURE


def test_classification_priority_infrastructure_wins():
    """If a name matches both PATH (infra) and DISABLE_ (risky),
    INFRASTRUCTURE wins because paths are deployment-level.
    """
    tier, _ = audit_defaults._classify("DISABLE_PATH_OVERRIDE", False)
    assert tier == audit_defaults.RiskTier.INFRASTRUCTURE


# ─── Value formatting ────────────────────────────────────


def test_format_value_bool():
    """Booleans render as 'true'/'false'."""
    assert audit_defaults._format_value(True) == "true"
    assert audit_defaults._format_value(False) == "false"


def test_format_value_int():
    """Integers render via repr."""
    assert audit_defaults._format_value(42) == "42"


def test_format_value_float():
    """Floats render via repr."""
    assert audit_defaults._format_value(3.14) == "3.14"


def test_format_value_none():
    """None renders as 'None'."""
    assert audit_defaults._format_value(None) == "None"


def test_format_value_string():
    """Strings render via repr (with quotes)."""
    assert audit_defaults._format_value("hello") == "'hello'"


# ─── audit_settings() with the real engine ────────────────


def test_audit_settings_returns_rows():
    """The audit walks the real python-engine Settings and
    returns >= 50 rows. Floor invariant: the engine has
    hundreds of settings.
    """
    if not os.path.isdir(ENGINE_DIR):
        pytest.skip("python-engine not present")
    Settings = audit_defaults._load_settings(ENGINE_DIR)
    rows = audit_defaults.audit_settings(Settings)
    assert len(rows) >= 50, f"expected >= 50 rows, got {len(rows)}"


def test_audit_settings_contains_specific_known_risky():
    """The audit must surface known RISKY settings (e.g.
    ``PENNY_EDGE_DISABLE_LIVE``) so operators can review them.
    """
    if not os.path.isdir(ENGINE_DIR):
        pytest.skip("python-engine not present")
    Settings = audit_defaults._load_settings(ENGINE_DIR)
    rows = audit_defaults.audit_settings(Settings)
    risky_names = {r.name for r in rows if r.tier == "RISKY"}
    assert "PENNY_EDGE_DISABLE_LIVE" in risky_names or "FNO_DISABLE_LIVE" in risky_names


def test_audit_settings_no_duplicates():
    """Each Settings attribute appears at most once."""
    if not os.path.isdir(ENGINE_DIR):
        pytest.skip("python-engine not present")
    Settings = audit_defaults._load_settings(ENGINE_DIR)
    rows = audit_defaults.audit_settings(Settings)
    names = [r.name for r in rows]
    assert len(names) == len(set(names))


# ─── format_audit (markdown) ────────────────────────────


def test_format_audit_includes_all_tiers():
    """The human-readable format groups rows by tier."""
    Settings = audit_defaults._load_settings(ENGINE_DIR)
    rows = audit_defaults.audit_settings(Settings)
    text = audit_defaults.format_audit(rows)
    # The format includes each tier heading.
    for tier in ("RISKY", "INFRASTRUCTURE", "SAFE"):
        if any(r.tier == tier for r in rows):
            assert f"## {tier}" in text


# ─── CLI integration ────────────────────────────────────


def test_main_human_readable(tmp_path, capsys):
    """Default mode emits the markdown summary."""
    rc = audit_defaults.main(["--engine-dir", str(ENGINE_DIR)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Settings defaults audit" in out


def test_main_json_output_is_valid_json(tmp_path, capsys):
    """``--json`` flag emits parseable JSON."""
    rc = audit_defaults.main(["--engine-dir", str(ENGINE_DIR), "--json"])
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert isinstance(parsed, list)
    assert len(parsed) > 0
    assert "name" in parsed[0]
    assert "tier" in parsed[0]


def test_main_risky_only_filters_output(tmp_path, capsys):
    """``--risky-only`` flag restricts output to RISKY rows."""
    rc = audit_defaults.main([
        "--engine-dir", str(ENGINE_DIR), "--json", "--risky-only",
    ])
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert all(r["tier"] == "RISKY" for r in parsed), (
        f"--risky-only returned non-RISKY rows: {parsed}"
    )


def test_main_writes_to_file(tmp_path):
    """``--out`` writes the JSON report to the specified file."""
    out_path = tmp_path / "defaults.json"
    rc = audit_defaults.main([
        "--engine-dir", str(ENGINE_DIR), "--json",
        "--out", str(out_path),
    ])
    assert rc == 0
    assert out_path.exists()
    parsed = json.loads(out_path.read_text())
    assert len(parsed) > 0


def test_main_errors_on_missing_engine_dir(tmp_path):
    """Missing engine directory -> exit code 2."""
    rc = audit_defaults.main([
        "--engine-dir", "/nonexistent/path/never/exists",
    ])
    assert rc == 2


# ─── Floor invariants (operator review anchor) ────────────


def test_real_engine_has_documented_risky_count():
    """[WORKFLOW-D.2.a-flags] Floor invariant: the engine
    today has at least 5 RISKY-tier settings. If a future
    refactor accidentally disables one of the fail-open
    name tokens, this catches the drift.
    """
    Settings = audit_defaults._load_settings(ENGINE_DIR)
    rows = audit_defaults.audit_settings(Settings)
    risky_count = sum(1 for r in rows if r.tier == "RISKY")
    assert risky_count >= 5, (
        f"RISKY-tier count dropped to {risky_count}; "
        f"the engine historically has >= 13 RISKY rows. "
        f"Investigate why the count dropped."
    )
