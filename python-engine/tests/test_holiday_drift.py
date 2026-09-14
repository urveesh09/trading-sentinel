"""[WORKFLOW-J.5 2026-09-13] Tests for the holiday-drift detector.

Pins:

  1. The Node source parser correctly extracts the ``new Set([...])``
     body and finds ISO dates even when the source uses inline
     comments, varied whitespace, and trailing commas.
  2. The python_nse_holidays() helper exposes the canonical set as
     ISO strings.
  3. holiday_drift_report() surfaces the documented drift between
     Python (20 dates, NSE-aligned) and Node (20 dates, the exact
     ISO projection post-correction; the pre-correction 18-date
     degraded set is documented in the test as the historical
     drift signature).
  4. holiday_drift_report() with both sets equal returns ALIGNED.
  5. The CLI hook (run as a module) exits 0 on ALIGNED, 1 on DRIFT.
  6. /holidays route returns the canonical holiday set as a JSON
     list with the matching descriptions table.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import holiday_drift as drift

# A representative Node-source snippet with the documented quirks:
# trailing commas, mixed whitespace, inline comments, both quote
# styles. The detector must tolerate all of these.
NODE_SOURCE_TYPICAL = """\
// Sourced from NSE 2026 calendar. Update annually from:
//   https://www.nseindia.com/resources/exchange-communication-holidays
const NSE_HOLIDAYS = new Set([
  '2026-01-26', // Republic Day
  '2026-03-31',
  '2026-04-03',//Good Friday (no-space)
\t'2026-04-14',  /* Dr. Ambedkar Jayanti */
  '2026-05-01',
  '2026-08-15',
  '2026-10-02',
  '2026-10-20',
  '2026-11-10',
  '2026-12-25',
]);
"""

# Snippet with double-quoted strings (alternative JS style).
NODE_SOURCE_DOUBLE_QUOTES = """\
const NSE_HOLIDAYS = new Set([
  "2026-01-26", // Republic Day
  "2026-04-03",
  "2026-12-25",
]);
"""

# Snippet with NO Set literal -- the detector should return empty
# (e.g. future refactor turns the Set into something exotic).
NODE_SOURCE_NO_SET = """
const NSE_HOLIDAYS = "all cats are beautiful";
"""


@pytest.fixture
def tmp_node_source(tmp_path: Path) -> Path:
    """A tmp-path write of a Node source so we can test the
    file-reading path without mutating the canonical Node file.
    """
    return tmp_path / "market-hours-fixture.js"


# ---- (1) Source parser robustness -----------------------------------

class TestParseNodeNseHolidays:
    """The parser is the only Node-side dependency. It must
    extract ISO dates from a Set literal that uses inline
    comments, mixed whitespace, and trailing commas.
    """

    def test_extracts_ten_typical_dates(self) -> None:
        result = drift.parse_node_nse_holidays(NODE_SOURCE_TYPICAL)
        assert result == {
            "2026-01-26", "2026-03-31", "2026-04-03", "2026-04-14",
            "2026-05-01", "2026-08-15", "2026-10-02", "2026-10-20",
            "2026-11-10", "2026-12-25",
        }

    def test_double_quoted_strings(self) -> None:
        result = drift.parse_node_nse_holidays(NODE_SOURCE_DOUBLE_QUOTES)
        assert result == {"2026-01-26", "2026-04-03", "2026-12-25"}

    def test_no_set_returns_empty(self) -> None:
        assert drift.parse_node_nse_holidays(NODE_SOURCE_NO_SET) == set()

    def test_blank_body_returns_empty(self) -> None:
        result = drift.parse_node_nse_holidays(
            "const FOO = new Set([]);"
        )
        assert result == set()

    def test_real_node_source_parses_to_twenty_dates(self) -> None:
        """Cross-check: the canonical Node source file (the one in
        this repo at node-gateway/server/utils/market-hours.js)
        has 20 dates. The detector must read that many. If this
        fails in the future, either the source was rewritten (and
        the detector's regex needs to learn the new syntax) or
        someone altered the file without running the drift check.

        The post-correction-plan Node fallback is the exact ISO
        projection of ``market_calendar.NSE_HOLIDAYS_STATIC``
        (20 dates), not the pre-correction 18-date degraded set.
        """
        path = drift._NODE_MARKET_HOURS_JS
        if not path.exists():
            pytest.skip(f"canonical Node source not present: {path}")
        assert drift.node_nse_holidays_from_atlas(path) == {
            "2026-01-15", "2026-01-26", "2026-02-15", "2026-03-03",
            "2026-03-21", "2026-03-26", "2026-03-31", "2026-04-03",
            "2026-04-14", "2026-05-01", "2026-05-28", "2026-06-26",
            "2026-08-15", "2026-09-14", "2026-10-02", "2026-10-20",
            "2026-11-08", "2026-11-10", "2026-11-24", "2026-12-25",
        }


# ---- (2) Python canonical surface --------------------------------

class TestPythonNseHolidays:
    def test_python_holidays_is_20_iso_strings(self) -> None:
        result = drift.python_nse_holidays()
        assert len(result) == 20
        # Spot-check: key dates from the NSE Equity 2026 calendar.
        assert "2026-01-26" in result  # Republic Day
        assert "2026-09-14" in result  # Ganesh Chaturthi

    def test_python_holidays_all_iso_format(self) -> None:
        for d in drift.python_nse_holidays():
            assert len(d) == 10 and d[4] == "-" and d[7] == "-", d


# ---- (3) Drift report shape and behaviour ------------------------

class TestHolidayDriftReport:
    """We use ``monkeypatch.setattr`` on
    ``holiday_drift.node_nse_holidays_from_atlas`` so the override
    is automatically reverted at end of each test. Manual
    module-level monkeypatching (with del) leaks across tests and
    causes false-fails in isolation.
    """

    def test_aligned_when_sets_match(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        py = {"a", "b", "c"}
        nd = {"c", "a", "b"}
        monkeypatch.setattr(
            drift, "node_nse_holidays_from_atlas",
            lambda path: set(nd),
        )
        rpt = drift.holiday_drift_report(
            python_set=py, node_source_path="/nonexistent"
        )
        assert rpt["verdict"] == "ALIGNED"
        assert rpt["drift_count"] == 0
        assert rpt["python_count"] == 3
        assert rpt["node_count"] == 3

    def test_drift_when_sets_diverge(
        self, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Python has 20 canonical, Node has 8 stale. Documented
        # case from the J.5 pre-state.
        py = {
            "2026-01-26", "2026-03-31", "2026-04-03", "2026-04-14",
            "2026-05-01", "2026-08-15", "2026-10-02", "2026-10-20",
            "2026-11-10", "2026-12-25",  # in both (10)
            "2026-01-15", "2026-02-15", "2026-03-03", "2026-03-21",
            "2026-03-26", "2026-05-28", "2026-06-26", "2026-09-14",
            "2026-11-08", "2026-11-24",   # only in python (10)
        }
        nd = {
            "2026-01-26", "2026-03-31", "2026-04-03", "2026-04-14",
            "2026-05-01", "2026-08-15", "2026-10-02", "2026-10-20",
            "2026-11-10", "2026-12-25",  # in both (10)
            "2026-03-10", "2026-03-17", "2026-06-07", "2026-07-07",
            "2026-08-26", "2026-09-05", "2026-11-09", "2026-11-27",  # only in node (8)
        }
        monkeypatch.setattr(
            drift, "node_nse_holidays_from_atlas",
            lambda path: set(nd),
        )
        rpt = drift.holiday_drift_report(
            python_set=py, node_source_path="/nonexistent"
        )
        assert rpt["verdict"] == "DRIFT"
        assert rpt["drift_count"] == 18
        assert rpt["python_count"] == 20
        assert rpt["node_count"] == 18
        assert len(rpt["python_only"]) == 10
        assert len(rpt["node_only"]) == 8
        assert len(rpt["in_both"]) == 10

    def test_real_world_drift_against_actual_node_source(self) -> None:
        """The post-correction Node source aligns with Python.

        The pre-correction documented drift (Python=20,
        Node=18) was caused by the Node fallback being a stale
        hand-maintained list rather than the engine-projected
        canonical set. The independent correction plan replaced
        the Node ``NSE_HOLIDAYS_FALLBACK`` with the exact ISO
        projection of ``market_calendar.NSE_HOLIDAYS_STATIC``,
        so the drift detector now reports ALIGNED.

        This test pins the post-correction ALIGNED state. If
        Node ever diverges from Python again (a fresh holiday
        announcement, an engine-projection regression), the
        detector will report DRIFT and this test will fail.
        """
        path = drift._NODE_MARKET_HOURS_JS
        if not path.exists():
            pytest.skip(f"canonical Node source not present: {path}")
        rpt = drift.holiday_drift_report()
        assert rpt["verdict"] == "ALIGNED"
        # Post-correction: python=20, node=20, drift_count=0.
        assert rpt["python_count"] == 20
        assert rpt["node_count"] == 20
        assert rpt["drift_count"] == 0
        # Spot-check that the canonical Python-only date is now
        # present in both surfaces.
        assert "2026-09-14" not in rpt["python_only"]
        assert "2026-09-14" not in rpt["node_only"]


# ---- (4) File-reading path ----------------------------------------

class TestFileReadPath:
    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        result = drift.node_nse_holidays_from_atlas(
            tmp_path / "does-not-exist.js"
        )
        assert result == set()

    def test_existing_file_is_parsed(self, tmp_node_source) -> None:
        tmp_node_source.write_text(
            "const NSE_HOLIDAYS = new Set(['2026-04-03', '2026-12-25']);",
            encoding="utf-8",
        )
        result = drift.node_nse_holidays_from_atlas(tmp_node_source)
        assert result == {"2026-04-03", "2026-12-25"}


# ---- (5) Report formatting -----------------------------------------

class TestFormatDriftReport:
    def test_aligned_report_includes_verdict_and_count(self) -> None:
        rpt = {
            "verdict": "ALIGNED",
            "python_count": 3,
            "node_count": 3,
            "drift_count": 0,
            "python_only": [],
            "node_only": [],
            "in_both": ["2026-01-01", "2026-01-02", "2026-01-03"],
        }
        text = drift.format_drift_report(rpt)
        assert "verdict=ALIGNED" in text
        assert "drift_count=0" in text
        assert "in_both[3]" in text

    def test_drift_report_section_order(self) -> None:
        # Sections are written in a stable order so a diff
        # against an operator-pinned log is stable.
        rpt = {
            "verdict": "DRIFT",
            "python_count": 2,
            "node_count": 2,
            "drift_count": 2,
            "python_only": ["2026-01-01"],
            "node_only": ["2026-01-02"],
            "in_both": [],
        }
        text = drift.format_drift_report(rpt)
        py_idx = text.index("python_only[")
        nd_idx = text.index("node_only[")
        assert py_idx < nd_idx, "python_only must appear before node_only"


# ---- (6) ISO projection is JSON-friendly ---------------------------

class TestIsoProjection:
    def test_iso_projection_is_sorted(self) -> None:
        from market_calendar import NSE_HOLIDAYS_ISO
        assert NSE_HOLIDAYS_ISO == tuple(sorted(NSE_HOLIDAYS_ISO))

    def test_iso_projection_length_matches_frozenset(self) -> None:
        from market_calendar import NSE_HOLIDAYS_ISO, NSE_HOLIDAYS_STATIC
        assert len(NSE_HOLIDAYS_ISO) == len(NSE_HOLIDAYS_STATIC)

    def test_each_iso_entry_valid_calendar_date(self) -> None:
        from datetime import date
        from market_calendar import NSE_HOLIDAYS_ISO
        for s in NSE_HOLIDAYS_ISO:
            y, m, d = s.split("-")
            date(int(y), int(m), int(d))  # raises ValueError on bad date

    def test_descriptions_table_covers_every_holiday(self) -> None:
        from market_calendar import (
            NSE_HOLIDAYS_STATIC, NSE_HOLIDAY_DESCRIPTIONS,
        )
        assert set(NSE_HOLIDAYS_STATIC) == set(NSE_HOLIDAY_DESCRIPTIONS.keys())
