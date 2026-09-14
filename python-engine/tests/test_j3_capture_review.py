"""[WORKFLOW-J.3.0 2026-09-13] Tests for ``tools/j2_capture_review.py``.

The review tool is the deterministic half of J.3: it reads a captured
JSON, runs the six-point checklist, and exits 0 only when every check
passes. These tests build synthetic captures for every PASS and FAIL
mode and confirm the review exits correctly.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
_ENGINE_DIR = _TOOLS_DIR.parent

if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))
if str(_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_ENGINE_DIR))

import j2_capture_review as review  # noqa: E402


# ---- Test fixtures --------------------------------------------------

_GOOD_ROW_SENTINEL = object()
"""Default-marker for ``_good_row(quote=...)``: when the caller
passes no quote argument (or the no-default-kwarg bare ``None``
we use as a literal, see ``_QUOTE_NONE``) the fixture builds the
default CAS-window-shaped quote. ``_QUOTE_NONE`` is the explicit
"quote must be JSON null" marker -- it bypasses the default."""

_QUOTE_NONE = object()


def _good_row(
    symbol: str = "RELIANCE",
    observation_at_utc: str = "2026-09-14T09:47:00+00:00",  # 15:17 IST
    classifier_phase: str = "CAS_REFERENCE_PRICE_WINDOW",
    is_cas_eligible: bool = True,
    quote=_GOOD_ROW_SENTINEL,
) -> dict:
    """A row that satisfies every check by default. ``quote``
    defaults (when not provided) to a CAS-window-shaped payload
    with non-zero circuit limits and at least one
    ``broker_extra_fields`` entry.

    Pass ``_QUOTE_NONE`` to explicitly request a null quote in
    failure-mode tests; passing the bare ``None`` is re-interpreted
    as "use the default" because of Python's mutable-default-value
    trap (which we sidestep via sentinel).
    """
    if quote is _GOOD_ROW_SENTINEL:
        quote = {
            "last_price": 2890.0,
            "ohlc": {"open": 2880.0, "high": 2900.0,
                     "low": 2875.0, "close": 2888.0},
            "volume": 1234567,
            "depth_available": True,
            "depth_buy_levels": 5,
            "depth_sell_levels": 5,
            "upper_circuit_limit": 2976.40,
            "lower_circuit_limit": 2799.60,
            "broker_extra_fields": {
                "auction_status": "OPEN",
            },
        }
    elif quote is _QUOTE_NONE:
        quote = None
    return {
        "symbol": symbol,
        "observation_at_utc": observation_at_utc,
        "observation_at_ist": "2026-09-14 15:17:00 IST",
        "is_cas_eligible": is_cas_eligible,
        "classifier_phase": classifier_phase,
        "quote": quote,
    }


def _good_capture(rows: list[dict] | None = None) -> dict:
    """A capture document that should pass every check."""
    if rows is None:
        rows = [_good_row()]
    return {
        "tool": "j2_cas_probe",
        "schema_version": 2,
        "generated_at_utc": "2026-09-14T10:00:00+00:00",
        "dry_run": False,
        "observation_at_utc": "2026-09-14T09:47:00+00:00",
        "observation_at_ist": "2026-09-14 15:17:00 IST",
        "symbol_count": len(rows),
        "eligibility_source": "settings",
        "rows": rows,
    }


def _write_capture(path: Path, doc: dict) -> Path:
    """Write the document to ``path`` (a complete filename, not a
    directory) and return the path. Caller controls the filename.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, default=str), encoding="utf-8")
    return path


# ---- (1) End-to-end PASS --------------------------------------------

class TestCaptureReviewPass:
    """A well-formed capture passes every check and exits 0."""

    def test_good_capture_exits_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Pin the eligibility set via cli override so the test is
        # independent of settings state.
        monkeypatch.setattr(
            review,
            "_expected_eligibility_from_settings",
            lambda: {"RELIANCE"},
        )
        p = _write_capture(tmp_path / 'cap.json', _good_capture())
        result = subprocess.run(
            [sys.executable, str(_TOOLS_DIR / "j2_capture_review.py"),
             str(p), "--expected-eligibility", "RELIANCE"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            result.stdout + " | " + result.stderr
        )
        # The emitted report encodes every check.
        report = json.loads(result.stdout)
        assert report["overall_passed"] is True
        names = [c["name"] for c in report["checks"]]
        for required in (
            "schema", "eligibility", "classifier_phase",
            "quote_present", "circuit_limits", "broker_extras",
        ):
            assert required in names


# ---- (2) End-to-end FAIL modes --------------------------------------

class TestCaptureReviewFailures:
    """Each failure mode trips exactly one check and exits 1."""

    def test_eligibility_mismatch_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            review,
            "_expected_eligibility_from_settings",
            lambda: {"RELIANCE"},
        )
        # Row says False but operator declared True.
        row = _good_row(is_cas_eligible=False)
        # Also fix classifier phase to match the ineligible case
        # so we don't trip the classifier check too.
        row["classifier_phase"] = "CONTINUOUS_TRADING"
        p = _write_capture(tmp_path / 'cap.json', _good_capture([row]))
        result = subprocess.run(
            [sys.executable, str(_TOOLS_DIR / "j2_capture_review.py"),
             str(p), "--expected-eligibility", "RELIANCE"],
            capture_output=True, text=True,
        )
        assert result.returncode == 1
        report = json.loads(result.stdout)
        assert report["overall_passed"] is False
        eligibility_check = next(
            c for c in report["checks"] if c["name"] == "eligibility"
        )
        assert eligibility_check["passed"] is False

    def test_classifier_phase_mismatch_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            review,
            "_expected_eligibility_from_settings",
            lambda: {"RELIANCE"},
        )
        # 15:17 IST but the row claims CAS_MATCHING (15:30).
        row = _good_row(classifier_phase="CAS_MATCHING")
        p = _write_capture(tmp_path / 'cap.json', _good_capture([row]))
        result = subprocess.run(
            [sys.executable, str(_TOOLS_DIR / "j2_capture_review.py"),
             str(p), "--expected-eligibility", "RELIANCE"],
            capture_output=True, text=True,
        )
        assert result.returncode == 1
        report = json.loads(result.stdout)
        phase_check = next(
            c for c in report["checks"] if c["name"] == "classifier_phase"
        )
        assert phase_check["passed"] is False

    def test_quote_null_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            review,
            "_expected_eligibility_from_settings",
            lambda: {"RELIANCE"},
        )
        row = _good_row(quote=_QUOTE_NONE)
        p = _write_capture(tmp_path / 'cap.json', _good_capture([row]))
        result = subprocess.run(
            [sys.executable, str(_TOOLS_DIR / "j2_capture_review.py"),
             str(p), "--expected-eligibility", "RELIANCE"],
            capture_output=True, text=True,
        )
        assert result.returncode == 1
        report = json.loads(result.stdout)
        assert any(
            c["name"] == "quote_present" and not c["passed"]
            for c in report["checks"]
        )

    def test_circuit_limits_zero_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            review,
            "_expected_eligibility_from_settings",
            lambda: {"RELIANCE"},
        )
        # Zero upper limit. The check fails on equality-with-zero.
        bad_quote = _good_row()["quote"].copy()
        bad_quote["upper_circuit_limit"] = 0
        row = _good_row(quote=bad_quote)
        p = _write_capture(tmp_path / 'cap.json', _good_capture([row]))
        result = subprocess.run(
            [sys.executable, str(_TOOLS_DIR / "j2_capture_review.py"),
             str(p), "--expected-eligibility", "RELIANCE"],
            capture_output=True, text=True,
        )
        assert result.returncode == 1
        report = json.loads(result.stdout)
        circuit_check = next(
            c for c in report["checks"] if c["name"] == "circuit_limits"
        )
        assert circuit_check["passed"] is False

    def test_no_broker_extras_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            review,
            "_expected_eligibility_from_settings",
            lambda: {"RELIANCE"},
        )
        bad_quote = _good_row()["quote"].copy()
        del bad_quote["broker_extra_fields"]
        row = _good_row(quote=bad_quote)
        p = _write_capture(tmp_path / 'cap.json', _good_capture([row]))
        result = subprocess.run(
            [sys.executable, str(_TOOLS_DIR / "j2_capture_review.py"),
             str(p), "--expected-eligibility", "RELIANCE"],
            capture_output=True, text=True,
        )
        assert result.returncode == 1
        report = json.loads(result.stdout)
        extras_check = next(
            c for c in report["checks"] if c["name"] == "broker_extras"
        )
        assert extras_check["passed"] is False

    def test_schema_drift_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            review,
            "_expected_eligibility_from_settings",
            lambda: {"RELIANCE"},
        )
        # Force a schema-version drift.
        doc = _good_capture()
        doc["schema_version"] = 1
        p = _write_capture(tmp_path / 'cap.json', doc)
        result = subprocess.run(
            [sys.executable, str(_TOOLS_DIR / "j2_capture_review.py"),
             str(p), "--expected-eligibility", "RELIANCE"],
            capture_output=True, text=True,
        )
        assert result.returncode == 1
        report = json.loads(result.stdout)
        schema_check = next(
            c for c in report["checks"] if c["name"] == "schema"
        )
        assert schema_check["passed"] is False


# ---- (3) Cross-window OHLC continuity ------------------------------

class TestCaptureReviewOHLCContinuity:
    """The ``--compare-with`` check validates OHLC continuity
    across two captures of the same symbol on the same trading day.
    """

    def test_ohlc_continuity_passes_on_equal_closes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            review,
            "_expected_eligibility_from_settings",
            lambda: {"RELIANCE"},
        )
        # Pre-CAS capture at 15:10.
        row_pre = _good_row(
            observation_at_utc="2026-09-14T09:40:00+00:00",  # 15:10 IST
            classifier_phase="CONTINUOUS_TRADING",
        )
        row_pre["quote"]["ohlc"]["close"] = 2888.0
        # CAS capture at 15:17. Same close.
        row_cas = _good_row(
            observation_at_utc="2026-09-14T09:47:00+00:00",
        )
        row_cas["quote"]["ohlc"]["close"] = 2888.0
        pre_path = _write_capture(tmp_path / "pre.json", _good_capture([row_pre]))
        cas_path = _write_capture(tmp_path / "cas.json", _good_capture([row_cas]))
        result = subprocess.run(
            [sys.executable, str(_TOOLS_DIR / "j2_capture_review.py"),
             str(cas_path), "--expected-eligibility", "RELIANCE",
             "--compare-with", str(pre_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            result.stdout + " | " + result.stderr
        )
        report = json.loads(result.stdout)
        assert report["overall_passed"] is True

    def test_ohlc_continuity_fails_on_diverging_closes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            review,
            "_expected_eligibility_from_settings",
            lambda: {"RELIANCE"},
        )
        row_pre = _good_row(
            observation_at_utc="2026-09-14T09:40:00+00:00",
            classifier_phase="CONTINUOUS_TRADING",
        )
        row_pre["quote"]["ohlc"]["close"] = 2888.0
        row_cas = _good_row(
            observation_at_utc="2026-09-14T09:47:00+00:00",
        )
        row_cas["quote"]["ohlc"]["close"] = 2890.0  # 2 INR difference
        pre_path = _write_capture(tmp_path / "pre.json", _good_capture([row_pre]))
        cas_path = _write_capture(tmp_path / "cas.json", _good_capture([row_cas]))
        result = subprocess.run(
            [sys.executable, str(_TOOLS_DIR / "j2_capture_review.py"),
             str(cas_path), "--expected-eligibility", "RELIANCE",
             "--compare-with", str(pre_path)],
            capture_output=True, text=True,
        )
        assert result.returncode == 1
        report = json.loads(result.stdout)
        cont_check = next(
            c for c in report["checks"] if c["name"] == "ohlc_continuity"
        )
        assert cont_check["passed"] is False


# ---- (4) Edge cases -------------------------------------------------

class TestCaptureReviewEdgeCases:

    def test_missing_file_exits_two(
        self, tmp_path: Path,
    ) -> None:
        result = subprocess.run(
            [sys.executable, str(_TOOLS_DIR / "j2_capture_review.py"),
             str(tmp_path / "missing.json")],
            capture_output=True, text=True,
        )
        assert result.returncode == 2

    def test_invalid_json_exits_two(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("not-json", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(_TOOLS_DIR / "j2_capture_review.py"),
             str(p)],
            capture_output=True, text=True,
        )
        assert result.returncode == 2

    def test_dry_run_skips_quote_present_check(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # dry_run documents legitimately have null quotes; the
        # review must NOT treat that as a failure.
        monkeypatch.setattr(
            review,
            "_expected_eligibility_from_settings",
            lambda: {"RELIANCE"},
        )
        row = _good_row(quote=_QUOTE_NONE)
        row["classifier_phase"] = "CAS_REFERENCE_PRICE_WINDOW"
        doc = _good_capture([row])
        doc["dry_run"] = True
        p = _write_capture(tmp_path / 'cap.json', doc)
        result = subprocess.run(
            [sys.executable, str(_TOOLS_DIR / "j2_capture_review.py"),
             str(p), "--expected-eligibility", "RELIANCE"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            result.stdout + " | " + result.stderr
        )
        report = json.loads(result.stdout)
        quote_check = next(
            c for c in report["checks"] if c["name"] == "quote_present"
        )
        assert quote_check["passed"] is True
        assert "skipped" in quote_check["detail"]

    def test_broker_extras_required_only_in_cas_phases(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # A symbol with NO broker_extra_fields but classified as
        # CONTINUOUS_TRADING (out of CAS) should pass the
        # broker-extras check.
        monkeypatch.setattr(
            review,
            "_expected_eligibility_from_settings",
            lambda: {"RELIANCE"},
        )
        bad_quote = _good_row()["quote"].copy()
        del bad_quote["broker_extra_fields"]
        row = _good_row(
            quote=bad_quote,
            observation_at_utc="2026-09-14T04:00:00+00:00",  # 09:30 IST
            classifier_phase="CONTINUOUS_TRADING",
        )
        row["is_cas_eligible"] = True
        p = _write_capture(tmp_path / 'cap.json', _good_capture([row]))
        result = subprocess.run(
            [sys.executable, str(_TOOLS_DIR / "j2_capture_review.py"),
             str(p), "--expected-eligibility", "RELIANCE"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, (
            result.stdout + " | " + result.stderr
        )


# ---- (5) Eligibility helper -----------------------------------------

class TestExpectedEligibilityParser:
    """The CSV parser is shared with the engine; correctness here
    is correctness everywhere.
    """

    def test_csv_with_whitespace_and_upper(self) -> None:
        s = review._expected_eligibility_from_csv(" Reliance , hdfcbank , INFY ")
        assert s == {"RELIANCE", "HDFCBANK", "INFY"}

    def test_csv_drops_empty_tokens(self) -> None:
        s = review._expected_eligibility_from_csv("RELIANCE,, HDFCBANK,")
        assert s == {"RELIANCE", "HDFCBANK"}

    def test_csv_empty_yields_empty_set(self) -> None:
        assert review._expected_eligibility_from_csv("") == set()

    def test_settings_loader_degrades_on_import_error(self) -> None:
        # The function returns an empty set if config is unavailable.
        result = review._expected_eligibility_from_settings()
        # Either an empty set (Dev, empty list) or a populated set
        # (test env). We only assert it's a set.
        assert isinstance(result, set)
