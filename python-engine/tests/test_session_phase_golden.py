"""[WORKFLOW-J.6 2026-09-13] Tests for the session-phase golden vector
regenerator and the parity contract.

Pins two things:

  1. The regenerator writes valid JSON with the documented
     schema_version (1) and the expected vector count. Future
     changes to the regenerator's shape fail loudly here.
  2. The regenerate script writes both source-of-truth locations:
       python-engine/tests/fixtures/session_phase_golden.json
       node-gateway/server/tests/fixtures/session_phase_golden.json
     This is the documented dual-write contract: the Python
     script is the only producer; the two consumers must be in
     lockstep.

These tests run in Dev (no broker / engine), exercising the
regenerator against the live ``classify_session_phase``.
"""
from __future__ import annotations

import json
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PY_ENGINE = REPO_ROOT / "python-engine"
NG_SERVER = REPO_ROOT / "node-gateway" / "server"
REGEN_SCRIPT = (
    PY_ENGINE / "tests" / "fixtures" / "regenerate_session_phase_golden.py"
)
PY_GOLDEN = PY_ENGINE / "tests" / "fixtures" / "session_phase_golden.json"
NODE_GOLDEN = NG_SERVER / "tests" / "fixtures" / "session_phase_golden.json"

_regen_spec = importlib.util.spec_from_file_location(
    "regenerate_session_phase_golden", REGEN_SCRIPT
)
assert _regen_spec is not None and _regen_spec.loader is not None
regen_module = importlib.util.module_from_spec(_regen_spec)
_regen_spec.loader.exec_module(regen_module)


@pytest.fixture(scope="module")
def regenerated_goldens():
    """Run the regenerator once for this module. Returns the two
    produced paths so individual tests can read them.
    """
    # On Windows the path ``PY_ENGINE`` (which is built from the
    # POSIX-form pytest rootdir, e.g. ``/c/Users/Urveesh/...``)
    # cannot be passed straight to ``subprocess.run`` -- it
    # raises ``NotADirectoryError (WinError 267)``. Resolve the
    # path against the OS native representation and verify the
    # directory exists before invoking.
    import os as _os
    import pathlib as _pathlib
    py_engine_native = _pathlib.Path(str(PY_ENGINE)).resolve()
    assert py_engine_native.is_dir(), (
        f"engine root not a directory on this OS: {py_engine_native}"
    )
    regen_native = _pathlib.Path(str(REGEN_SCRIPT)).resolve()
    assert regen_native.is_file(), (
        f"regenerator missing: {regen_native}"
    )
    env = _os.environ.copy()
    env["PYTHONPATH"] = str(py_engine_native)
    NODE_GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    # Use the same Python interpreter that pytest is running
    # under (``sys.executable``); ``python`` on PATH can be a
    # different interpreter without ``aiosqlite`` installed, which
    # breaks the import at the top of market_calendar.py.
    proc = subprocess.run(
        [sys.executable, str(regen_native)],
        cwd=str(py_engine_native), env=env,
        capture_output=True, text=True, check=True,
    )
    return {
        "py": PY_GOLDEN,
        "node": NODE_GOLDEN,
        "stdout": proc.stdout,
        "command": [sys.executable, str(regen_native)],
        "cwd": py_engine_native,
        "env": env,
    }


def test_regenerator_produces_py_golden_with_documented_schema(
    regenerated_goldens,
) -> None:
    py = regenerated_goldens["py"]
    assert py.exists(), f"expected {py} to exist after regenerate"
    doc = json.loads(py.read_text(encoding="utf-8"))
    assert doc["schema_version"] == 1
    assert doc["python_classifier"] == "market_calendar.classify_session_phase"
    assert "vectors" in doc
    # The expected count is the union of the two sweeps:
    #   - broad: 8 days * 24 hours * 4 minutes * 3 option combos = 2304
    #   - second-granularity: 17 boundary instants * 3 option combos = 51
    # Total: 2355.
    expected = 2304 + 51
    assert doc["vector_count"] == expected
    assert doc["vector_count"] == len(doc["vectors"])


def test_regenerator_writes_both_locations(regenerated_goldens) -> None:
    assert regenerated_goldens["node"].exists(), (
        f"regenerator must also write {regenerated_goldens['node']} "
        f"so the Node test consumer stays in lockstep with the Python source-of-truth"
    )
    py = json.loads(
        regenerated_goldens["py"].read_text(encoding="utf-8")
    )
    node = json.loads(
        regenerated_goldens["node"].read_text(encoding="utf-8")
    )
    # Same payload (apart from ``generated_at_utc`` which the
    # node-side consumer does not need to match).
    assert py["vectors"] == node["vectors"]
    assert py["python_classifier"] == node["python_classifier"]


def test_regenerator_is_byte_stable_when_semantics_are_unchanged(
    regenerated_goldens,
) -> None:
    """A second no-op generation must not churn timestamp metadata."""
    py_before = regenerated_goldens["py"].read_bytes()
    node_before = regenerated_goldens["node"].read_bytes()
    proc = subprocess.run(
        regenerated_goldens["command"],
        cwd=str(regenerated_goldens["cwd"]),
        env=regenerated_goldens["env"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "unchanged" in proc.stdout
    assert regenerated_goldens["py"].read_bytes() == py_before
    assert regenerated_goldens["node"].read_bytes() == node_before
    assert py_before == node_before
    assert py_before.endswith(b"\n")


def test_semantic_change_does_not_preserve_old_timestamp(tmp_path) -> None:
    """Only an identical semantic payload may reuse provenance time."""
    target = tmp_path / "golden.json"
    target.write_text(
        json.dumps({
            "generated_at_utc": "2026-01-01T00:00:00+00:00",
            "schema_version": 1,
            "vectors": [],
        }),
        encoding="utf-8",
    )
    assert regen_module._preserved_generated_at(
        target, {"schema_version": 1, "vectors": []}
    ) == "2026-01-01T00:00:00+00:00"
    assert regen_module._preserved_generated_at(
        target, {"schema_version": 1, "vectors": [{"changed": True}]}
    ) is None


def test_golden_phase_values_are_bounded(regenerated_goldens) -> None:
    """Every ``expected`` field is one of the documented phases.

    This is the user's ``_VALID_SESSION_PHASES`` invariant
    enforced on the golden itself: a future change to the
    Python classifier that starts returning a non-documented
    phase string would surface here, not at the Node consumer.
    """
    from market_calendar import _VALID_SESSION_PHASES
    valid = set(_VALID_SESSION_PHASES)
    doc = json.loads(
        regenerated_goldens["py"].read_text(encoding="utf-8")
    )
    offenders = [
        v for v in doc["vectors"] if v["expected"] not in valid
    ]
    assert offenders == [], f"unexpected phase strings in golden: {offenders[:5]}"


def test_golden_vectors_cover_all_sub_windows(regenerated_goldens) -> None:
    """The sweep must include at least one vector that produces
    each *real* documented phase (the ten ``_VALID_SESSION_PHASES``
    excluding the ``UNKNOWN`` sentinel, which is only produced
    by invalid inputs -- not by the live classifier sweep).
    A future refactor that accidentally swallowed a CAS
    sub-window would leave the golden without it; this test
    catches that.

    ``CAS_LIMIT_ENTRY_ONLY`` only fires at the second-level
    window 15:29:30 - 15:30 IST; ``CAS_POST`` only fires
    between 15:40 - 16:00 IST on derivatives. The 15-minute
    minute-granularity sweep would miss both; the
    regenerator explicitly hits those windows in a dedicated
    boundary pass.
    """
    from market_calendar import _VALID_SESSION_PHASES
    real_phases = set(_VALID_SESSION_PHASES) - {"UNKNOWN"}
    doc = json.loads(
        regenerated_goldens["py"].read_text(encoding="utf-8")
    )
    seen = {v["expected"] for v in doc["vectors"]}
    missing = real_phases - seen
    assert not missing, (
        f"golden does not exercise every documented real phase; "
        f"missing: {missing}; "
        f"sweep saw: {sorted(seen)}"
    )
