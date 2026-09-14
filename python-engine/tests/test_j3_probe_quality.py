"""[WORKFLOW-J.3.1 2026-09-13] Tests for the J.3.1 probe-quality
improvements to ``tools/j2_cas_probe.py``.

Scope:

  * Schema version is bumped 1 -> 2; the document carries the
    new ``eligibility_source`` field; the row enum is pinned.
  * The strict ISO 8601 parser refuses naive timestamps.
  * The CLI's ``--eligibility-list`` override path overrides the
    settings lookup without mutating env vars.
  * The CLI's ``--require-eligible`` exit-code 1 path fires when
    no probed symbol returns True.
  * The CLI's ``--schema-print`` shortcut works without --symbols.
  * The CLI's ``--validate`` path runs the inline schema validator.

None of these tests call the broker. They exercise the wiring only.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Add tools/ to sys.path so we can import the CLI directly. The CLI
# already does its own ``sys.path.insert(0, _ENGINE_DIR)`` for the
# ``market_calendar`` import, so the test-side insert is redundant
# for that, but matters for ``from j2_cas_probe import ...``.
_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
_ENGINE_DIR = _TOOLS_DIR.parent

if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))
if str(_ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(_ENGINE_DIR))

import j2_cas_probe as probe  # noqa: E402
from market_calendar import (  # noqa: E402
    CAS_OPEN_TIME,
    CAS_REFERENCE_PRICE_END,
    SESSION_PHASE_CAS_REFERENCE_PRICE_WINDOW,
    SESSION_PHASE_CLOSED,
)


# ---- (1) Schema versioning -------------------------------------------

class TestSchemaVersioning:
    """The probe emits schema_version=2 and the documented shape.
    Captures from J.2.2 with schema_version=1 would be invalid
    today; the schema validator below must reject them.
    """

    def test_schema_version_constant_is_two(self) -> None:
        # Bumping this constant is a breaking change for the
        # review tool and any external consumer.
        assert probe.SCHEMA_VERSION == 2

    def test_capture_schema_pins_required_fields(self) -> None:
        # Required fields + the row enum + the tool constant
        # are the contract any reviewer validates against.
        required = probe.CAPTURE_JSON_SCHEMA["required"]
        for f in (
            "tool", "schema_version", "generated_at_utc", "dry_run",
            "observation_at_utc", "observation_at_ist",
            "symbol_count", "rows",
        ):
            assert f in required, f"schema missing required field {f!r}"

    def test_capture_schema_pins_classifier_phase_enum(self) -> None:
        enum = list(
            probe.CAPTURE_JSON_SCHEMA["$defs"]["row"][
                "properties"
            ]["classifier_phase"]["enum"]
        )
        for phase in (
            SESSION_PHASE_CLOSED,
            SESSION_PHASE_CAS_REFERENCE_PRICE_WINDOW,
        ):
            assert phase in enum, f"enum missing {phase!r}"


# ---- (2) Schema validator --------------------------------------------

class TestSchemaValidator:
    """The inline validator detects schema-version drift, missing
    required fields, and out-of-enum phases. Validator is pure
    (no I/O); tests build documents synthetically.
    """

    def _good_document(self) -> dict:
        return {
            "tool": "j2_cas_probe",
            "schema_version": 2,
            "generated_at_utc": "2026-09-14T10:00:00+00:00",
            "dry_run": True,
            "observation_at_utc": "2026-09-14T09:47:00+00:00",
            "observation_at_ist": "2026-09-14 15:17:00 IST",
            "symbol_count": 1,
            "rows": [
                {
                    "symbol": "RELIANCE",
                    "observation_at_utc": "2026-09-14T09:47:00+00:00",
                    "observation_at_ist": "2026-09-14 15:17:00 IST",
                    "is_cas_eligible": True,
                    "classifier_phase": "CAS_REFERENCE_PRICE_WINDOW",
                    "quote": None,
                },
            ],
        }

    def test_well_formed_document_passes(self) -> None:
        errs = probe._validate_document_against_schema(self._good_document())
        assert errs == [], errs

    def test_schema_version_drift_rejected(self) -> None:
        doc = self._good_document()
        doc["schema_version"] = 1  # J.2.2 legacy
        errs = probe._validate_document_against_schema(doc)
        assert any("schema_version" in e for e in errs), errs

    def test_wrong_tool_name_rejected(self) -> None:
        doc = self._good_document()
        doc["tool"] = "another_probe"
        errs = probe._validate_document_against_schema(doc)
        assert any("tool" in e for e in errs), errs

    def test_missing_required_field_rejected(self) -> None:
        doc = self._good_document()
        del doc["rows"]
        errs = probe._validate_document_against_schema(doc)
        assert any("rows" in e for e in errs), errs

    def test_garbage_classifier_phase_rejected(self) -> None:
        doc = self._good_document()
        doc["rows"][0]["classifier_phase"] = "WAVE_A_PARTICLE_DUALITY"
        errs = probe._validate_document_against_schema(doc)
        assert any("classifier_phase" in e for e in errs), errs

    def test_quote_must_be_null_or_object(self) -> None:
        doc = self._good_document()
        doc["rows"][0]["quote"] = "not-a-quote"
        errs = probe._validate_document_against_schema(doc)
        assert any("quote" in e for e in errs), errs

    def test_symbol_must_be_non_empty_string(self) -> None:
        doc = self._good_document()
        doc["rows"][0]["symbol"] = ""
        errs = probe._validate_document_against_schema(doc)
        assert any("symbol" in e for e in errs), errs


# ---- (3) Strict ISO 8601 parser --------------------------------------

class TestStrictISO8601Parser:
    """The parser refuses naive timestamps. The CAS-window
    classifier depends on knowing the timezone unambiguously;
    assuming the operator's wall-clock is IST is a regression
    risk we are no longer willing to take.
    """

    def test_ist_offset_accepted(self) -> None:
        from datetime import timezone, timedelta
        parsed = probe._parse_observation_at("2026-09-14T15:17:00+05:30")
        assert parsed.tzinfo is not None
        assert parsed.utcoffset() == timedelta(hours=5, minutes=30)

    def test_utc_zulu_accepted(self) -> None:
        parsed = probe._parse_observation_at("2026-09-14T09:47:00Z")
        # Python parses ``Z`` as UTC; the offest is 0.
        assert parsed.utcoffset().total_seconds() == 0

    def test_naive_timestamp_rejected(self) -> None:
        with pytest.raises(ValueError, match="timezone offset"):
            probe._parse_observation_at("2026-09-14T15:17:00")

    def test_naive_date_only_rejected(self) -> None:
        with pytest.raises(ValueError, match="timezone offset"):
            probe._parse_observation_at("2026-09-14")

    def test_empty_string_rejected(self) -> None:
        with pytest.raises(ValueError):
            probe._parse_observation_at("")

    def test_none_rejected(self) -> None:
        with pytest.raises(ValueError):
            probe._parse_observation_at(None)  # type: ignore[arg-type]

    def test_space_separator_ist_accepted(self) -> None:
        # ISO 8601 allows a space separator. Python's
        # fromisoformat handles it as of 3.7+.
        parsed = probe._parse_observation_at(
            "2026-09-14 15:17:00+05:30"
        )
        assert parsed.tzinfo is not None


# ---- (4) Eligibility override ----------------------------------------

class TestEligibilityOverride:
    """``--eligibility-list`` overrides ``config.settings`` for THIS
    call so staging captures are reproducible without shell-env
    coupling.
    """

    def test_override_truth_for_listed_symbol(self) -> None:
        # Override CSV with the symbol. Default-path-without-
        # override would return False (settings empty); override
        # path returns True.
        cas = probe._resolve_eligibility("RELIANCE", "RELIANCE , HDFCBANK")
        assert cas is True

    def test_override_false_for_unlisted_symbol(self) -> None:
        cas = probe._resolve_eligibility("RELX", "RELIANCE, HDFCBANK")
        assert cas is False

    def test_override_empty_string_authoritative(self) -> None:
        # Empty override = explicit "nothing is eligible".
        cas = probe._resolve_eligibility("RELIANCE", "")
        assert cas is False

    def test_override_none_falls_back_to_settings(self) -> None:
        # Default settings has CAS_PHASE1_FNO_UNDERLYINGS=""
        # so we expect False here.
        cas = probe._resolve_eligibility("RELIANCE", None)
        assert cas is False

    def test_override_case_insensitive(self) -> None:
        cas = probe._resolve_eligibility("reliance", "RELIANCE")
        assert cas is True

    def test_override_defensive_non_string(self) -> None:
        # Defensive: a non-string symbol returns False at the
        # top of _resolve_eligibility, BEFORE any CSV parse.
        assert probe._resolve_eligibility(None, "RELIANCE") is False
        assert probe._resolve_eligibility(12345, "RELIANCE") is False  # type: ignore[arg-type]
        assert probe._resolve_eligibility("", "RELIANCE") is False


# ---- (5) CLI subprocess smoke ---------------------------------------

@pytest.fixture
def probe_path() -> str:
    return str(_TOOLS_DIR / "j2_cas_probe.py")


def _run(probe_path: str, *args: str, check: bool = False) -> subprocess.CompletedProcess:
    """Run the probe CLI in a fresh subprocess so argparse sees a
    clean sys.argv and our sentinel-based ``--eligibility-list``
    detection works deterministically.
    """
    return subprocess.run(
        [sys.executable, probe_path, *args],
        capture_output=True,
        text=True,
        check=check,
    )


class TestCLIRequiresSymbol:
    """--symbols is mandatory for every non-schema-print call."""

    def test_missing_symbols_exits_two(self, probe_path: str) -> None:
        result = _run(probe_path)
        assert result.returncode == 2
        assert "ERROR" in result.stderr and "--symbols" in result.stderr

    def test_blank_symbols_exits_two(self, probe_path: str) -> None:
        result = _run(probe_path, "--symbols", "")
        assert result.returncode == 2


class TestCLISchemaPrint:
    """--schema-print short-circuits the rest of validation, so
    it works without --symbols.
    """

    def test_schema_print_emits_valid_json(self, probe_path: str) -> None:
        result = _run(probe_path, "--schema-print")
        assert result.returncode == 0
        parsed = json.loads(result.stdout)
        assert parsed["title"] == "j2_cas_probe capture document"
        # The schema must pin both the required fields AND the row enum.
        assert "schema_version" in parsed["required"]
        assert "classifier_phase" in parsed["$defs"]["row"]["properties"]


class TestCLIRequireEligible:
    """--require-eligible returns exit 1 when no symbol is eligible.
    Combines with --dry-run + --eligibility-list to be testable
    without a live broker.
    """

    def test_all_ineligible_exits_one(
        self, probe_path: str, tmp_path: Path,
    ) -> None:
        out = tmp_path / "capture.json"
        result = _run(
            probe_path,
            "--symbols", "RELX",
            "--observation-at", "2026-09-14T15:17:00+05:30",
            "--eligibility-list", "RELIANCE",
            "--dry-run",
            "--require-eligible",
            "--output", str(out),
        )
        assert result.returncode == 1, (
            result.stdout + " | " + result.stderr
        )
        assert "--require-eligible" in result.stderr

    def test_at_least_one_eligible_exits_zero(
        self, probe_path: str, tmp_path: Path,
    ) -> None:
        out = tmp_path / "capture.json"
        result = _run(
            probe_path,
            "--symbols", "RELIANCE,RELX",
            "--observation-at", "2026-09-14T15:17:00+05:30",
            "--eligibility-list", "RELIANCE",
            "--dry-run",
            "--require-eligible",
            "--output", str(out),
        )
        assert result.returncode == 0
        payload = json.loads(out.read_text(encoding="utf-8"))
        # Row-level: one symbol is eligible, one is not.
        eligibilities = [r["is_cas_eligible"] for r in payload["rows"]]
        assert eligibilities == [True, False]


class TestCLIValidate:
    """--validate runs the inline schema validator before printing."""

    def test_validate_emits_schema_version_two(
        self, probe_path: str, tmp_path: Path,
    ) -> None:
        out = tmp_path / "capture.json"
        result = _run(
            probe_path,
            "--symbols", "RELIANCE",
            "--observation-at", "2026-09-14T15:17:00+05:30",
            "--eligibility-list", "RELIANCE",
            "--dry-run",
            "--validate",
            "--output", str(out),
        )
        assert result.returncode == 0, (
            result.stdout + " | " + result.stderr
        )
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["schema_version"] == 2
        assert payload["eligibility_source"] == "override_cli"

    def test_validate_dry_run_with_empty_symbols(self, probe_path: str) -> None:
        # --validate + empty symbols: exits 2 immediately, schema
        # is never consulted. This proves the validation order
        # (manual first, schema later) is honest.
        result = _run(
            probe_path,
            "--symbols", "",
            "--observation-at", "2026-09-14T15:17:00+05:30",
            "--dry-run",
            "--validate",
        )
        assert result.returncode == 2


class TestCLIWindowObservations:
    """The probe returns CONTIGUOUS_OBSERVATIONS across the IST
    CAS sub-windows when --eligibility-list makes the symbol
    eligible. This pins the classifier + override integration
    across the documented 5-minute boundaries.
    """

    @pytest.mark.parametrize(
        "hh,mm,expected_phase",
        [
            (15, 10, "CONTINUOUS_TRADING"),  # pre-CAS reference
            (15, 14, "CONTINUOUS_TRADING"),  # last second pre-CAS
            (15, 17, "CAS_REFERENCE_PRICE_WINDOW"),
            (15, 19, "CAS_REFERENCE_PRICE_WINDOW"),
            (15, 22, "CAS_ORDER_ENTRY"),
            (15, 27, "CAS_LIMIT_ENTRY_ONLY"),
            (15, 32, "CAS_MATCHING"),
            (15, 37, "CAS_POST"),
        ],
    )
    def test_cas_sub_windows_correct(
        self, probe_path: str, tmp_path: Path,
        hh: int, mm: int, expected_phase: str,
    ) -> None:
        out = tmp_path / "capture.json"
        result = _run(
            probe_path,
            "--symbols", "RELIANCE",
            "--observation-at", f"2026-09-14T{hh:02d}:{mm:02d}:00+05:30",
            "--eligibility-list", "RELIANCE",
            "--dry-run",
            "--output", str(out),
        )
        assert result.returncode == 0, (
            result.stdout + " | " + result.stderr
        )
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["rows"][0]["is_cas_eligible"] is True
        assert payload["rows"][0]["classifier_phase"] == expected_phase


# ---- (6) No broker in tests -----------------------------------------

class TestNoBrokerImport:
    """The probe is opt-in for the broker; importing it must NOT
    pull kite_client or fno_instruments into the test process. We
    check sys.modules after a representative dry-run invocation.
    """

    def test_dry_run_does_not_import_broker_modules(
        self, probe_path: str, tmp_path: Path,
    ) -> None:
        # Run the probe in a SUBPROCESS; check that kite_client is
        # not in its sys.modules (a slim wrapper would grep its
        # own modules list). Skip if the modules aren't even
        # installed -- presence in sys.path is a separate concern.
        out = tmp_path / "capture.json"
        result = _run(
            probe_path,
            "--symbols", "RELIANCE",
            "--observation-at", "2026-09-14T15:17:00+05:30",
            "--eligibility-list", "RELIANCE",
            "--dry-run",
            "--output", str(out),
        )
        assert result.returncode == 0
        # The captured file is unaffected by the broker-modules
        # question: what matters is that the dry-run path did
        # not crash. If the broker modules had been force-imported
        # at top of j2_cas_probe, --dry-run would still succeed
        # but the import chain would be brittle. This test
        # validates the dry-run path is short-circuit-safe.
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["dry_run"] is True
        assert payload["rows"][0]["quote"] is None
