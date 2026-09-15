"""[WORKFLOW-J.10.FRESHNESS 2026-09-14] Capture-freshness tests.

The gate's per-branch count is now driven by three filters:
  - bounded phase (existing)
  - unique observation per branch (J.10.DEDUP)
  - age within the freshness window (J.10.FRESHNESS, this slice)

These tests pin the freshness contract at two layers:
  1. ``cas_reachability_freshness`` -- the pure helpers
     (``capture_age_days``, ``is_within_max_age``).
  2. ``cas_reachability_gate`` -- the integration: stale
     captures increment ``captures_skipped_stale`` and do
     NOT contribute to the per-branch count.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Imports under test


from cas_reachability_freshness import (  # noqa: E402
    capture_age_days,
    is_within_max_age,
)
from cas_reachability_gate import (  # noqa: E402
    CAS_BRANCHES_REQUIRING_EVIDENCE,
    cas_reachability_report,
    format_report,
    update_summary,
)


# ---------------------------------------------------------------------------
# Helpers


def _make_capture(
    phase: str,
    *,
    generated_at_utc: str | None = None,
    symbol: str = "RELIANCE",
    observation_at_ist: str = "2026-09-14T15:17:00+05:30",
) -> dict[str, Any]:
    """Build a minimal J.3-shaped capture dict with an optional
    ``generated_at_utc`` (defaults to "right now")."""
    if generated_at_utc is None:
        generated_at_utc = datetime.now(timezone.utc).isoformat()
    return {
        "tool": "j2_cas_probe",
        "schema_version": 2,
        "generated_at_utc": generated_at_utc,
        "dry_run": True,
        "observation_at_utc": "2026-09-14T09:47:00+00:00",
        "observation_at_ist": observation_at_ist,
        "symbol_count": 1,
        "rows": [
            {
                "symbol": symbol,
                "classifier_phase": phase,
                "classifier_observation_at_utc": "2026-09-14T09:47:00+00:00",
            }
        ],
    }


def _write_capture(
    captures_dir: Path, name: str, capture: dict[str, Any]
) -> Path:
    captures_dir.mkdir(parents=True, exist_ok=True)
    path = captures_dir / name
    path.write_text(
        json.dumps(capture, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# 1. capture_age_days -- the pure helper


class TestCaptureAgeDays:
    """The age-in-days helper."""

    def test_returns_zero_for_just_written_capture(self, tmp_path: Path):
        p = _write_capture(
            tmp_path,
            "now.json",
            _make_capture("CAS_MATCHING"),
        )
        age = capture_age_days(p)
        assert age is not None
        # Just written -> very close to zero.
        assert age < 0.01

    def test_returns_positive_for_old_capture(self, tmp_path: Path):
        # 5 days old.
        old_ts = (
            datetime.now(timezone.utc) - timedelta(days=5)
        ).isoformat()
        p = _write_capture(
            tmp_path,
            "old.json",
            _make_capture("CAS_MATCHING", generated_at_utc=old_ts),
        )
        age = capture_age_days(p)
        assert age is not None
        # Allow a small fudge factor for the time the test takes.
        assert 4.99 < age < 5.01

    def test_uses_explicit_now_utc(self, tmp_path: Path):
        p = _write_capture(
            tmp_path,
            "fixed.json",
            _make_capture(
                "CAS_MATCHING",
                generated_at_utc="2026-01-01T00:00:00+00:00",
            ),
        )
        # Pick a "now" that's exactly 30 days later.
        now = datetime(2026, 1, 31, tzinfo=timezone.utc)
        age = capture_age_days(p, now_utc=now)
        assert age is not None
        assert age == pytest.approx(30.0, abs=0.01)

    def test_unreadable_file_returns_none(self, tmp_path: Path):
        assert capture_age_days(tmp_path / "missing.json") is None

    def test_missing_field_returns_none(self, tmp_path: Path):
        # Capture without ``generated_at_utc`` -- the helper
        # cannot determine age.
        cap = _make_capture("CAS_MATCHING")
        del cap["generated_at_utc"]
        p = _write_capture(tmp_path, "no_ts.json", cap)
        assert capture_age_days(p) is None

    def test_naive_timestamp_returns_none(self, tmp_path: Path):
        # The J.3 probe always writes aware timestamps; a naive
        # timestamp is a schema violation and the helper
        # treats it as unreadable.
        cap = _make_capture(
            "CAS_MATCHING",
            generated_at_utc="2026-09-14T15:17:00",  # no tzinfo
        )
        p = _write_capture(tmp_path, "naive.json", cap)
        assert capture_age_days(p) is None

    def test_unparseable_timestamp_returns_none(self, tmp_path: Path):
        cap = _make_capture(
            "CAS_MATCHING",
            generated_at_utc="yesterday",
        )
        p = _write_capture(tmp_path, "bad.json", cap)
        assert capture_age_days(p) is None

    def test_garbage_json_returns_none(self, tmp_path: Path):
        p = tmp_path / "broken.json"
        p.write_text("{not json", encoding="utf-8")
        assert capture_age_days(p) is None

    def test_non_string_timestamp_returns_none(self, tmp_path: Path):
        cap = _make_capture("CAS_MATCHING")
        cap["generated_at_utc"] = 12345  # int, not string
        p = _write_capture(tmp_path, "int_ts.json", cap)
        assert capture_age_days(p) is None

    def test_never_raises(self, tmp_path: Path):
        # Every error path returns None; nothing escapes.
        for path in [
            tmp_path / "missing.json",
        ]:
            try:
                capture_age_days(path)
            except Exception as exc:  # pragma: no cover - defensive
                pytest.fail(f"unexpected raise: {exc}")
        # A directory where the file is expected -> the read
        # raises OSError, the helper returns None.
        dir_path = tmp_path / "dir-as-file.json"
        dir_path.mkdir()
        try:
            capture_age_days(dir_path)
        except Exception as exc:  # pragma: no cover - defensive
            pytest.fail(f"unexpected raise: {exc}")


class TestIsWithinMaxAge:
    """The bounded comparison helper."""

    def test_within_returns_true(self):
        assert is_within_max_age(2.0, 7.0) is True

    def test_at_boundary_returns_true(self):
        assert is_within_max_age(7.0, 7.0) is True

    def test_over_returns_false(self):
        assert is_within_max_age(8.0, 7.0) is False

    def test_none_age_returns_false(self):
        # Unreadable captures are never within any max age.
        assert is_within_max_age(None, 7.0) is False


# ---------------------------------------------------------------------------
# 2. cas_reachability_gate -- integration


class TestGateFreshness:
    """The gate honours ``max_age_days``."""

    def test_no_filter_means_no_stale_count(self, tmp_path: Path):
        # Default: even ancient captures count toward coverage.
        old_ts = (
            datetime.now(timezone.utc) - timedelta(days=365)
        ).isoformat()
        for phase in CAS_BRANCHES_REQUIRING_EVIDENCE:
            _write_capture(
                tmp_path,
                f"{phase}.json",
                _make_capture(phase, generated_at_utc=old_ts),
            )
        report = cas_reachability_report(tmp_path)
        assert report["verdict"] == "REACHABLE"
        assert report["captures_skipped_stale"] == 0

    def test_filter_drops_stale_captures(self, tmp_path: Path):
        # One capture is "fresh" (just now), one is "ancient"
        # (a year old). With max_age_days=7, only the fresh
        # one counts.
        fresh = _make_capture("CAS_REFERENCE_PRICE_WINDOW")
        ancient_ts = (
            datetime.now(timezone.utc) - timedelta(days=400)
        ).isoformat()
        ancient = _make_capture(
            "CAS_REFERENCE_PRICE_WINDOW",
            generated_at_utc=ancient_ts,
            symbol="TCS",
        )
        _write_capture(tmp_path, "fresh.json", fresh)
        _write_capture(tmp_path, "ancient.json", ancient)
        report = cas_reachability_report(tmp_path, max_age_days=7.0)
        # The fresh one counts; the ancient one is filtered.
        assert (
            report["captured_phases"]["CAS_REFERENCE_PRICE_WINDOW"]
            == 1
        )
        assert report["captures_scanned"] == 2
        assert report["captures_skipped_stale"] == 1
        # Captures_skipped is still 0 -- the ancient capture
        # was malformed-free, just old.
        assert report["captures_skipped"] == 0

    def test_filter_drops_stale_to_unreachable(self, tmp_path: Path):
        """The defensive invariant: an UNREACHABLE gate that
        was previously REACHABLE on stale evidence must FLIP
        to UNREACHABLE when the operator applies a freshness
        filter."""
        ancient_ts = (
            datetime.now(timezone.utc) - timedelta(days=90)
        ).isoformat()
        for phase in CAS_BRANCHES_REQUIRING_EVIDENCE:
            _write_capture(
                tmp_path,
                f"{phase}.json",
                _make_capture(phase, generated_at_utc=ancient_ts),
            )
        # Without filter: REACHABLE.
        assert cas_reachability_report(tmp_path)["verdict"] == "REACHABLE"
        # With a 30-day filter: every capture is now stale,
        # the gate flips to UNREACHABLE.
        report = cas_reachability_report(tmp_path, max_age_days=30.0)
        assert report["verdict"] == "UNREACHABLE"
        assert report["captures_skipped_stale"] == len(
            CAS_BRANCHES_REQUIRING_EVIDENCE
        )

    def test_filter_with_malformed_distinguishes_skip_categories(
        self, tmp_path: Path
    ):
        # Stale captures go to ``captures_skipped_stale``;
        # malformed captures go to ``captures_skipped``.
        # The two categories are distinct.
        old_ts = (
            datetime.now(timezone.utc) - timedelta(days=400)
        ).isoformat()
        # One stale-but-valid capture (has generated_at_utc,
        # passes schema, but is ancient).
        _write_capture(
            tmp_path,
            "stale.json",
            _make_capture("CAS_MATCHING", generated_at_utc=old_ts),
        )
        # One fresh-but-malformed capture: HAS generated_at_utc
        # (so the freshness filter passes it through), but the
        # schema parse fails -- the rows array has a row whose
        # classifier_phase is not in the bounded set.
        malformed_capture = _make_capture("CAS_MATCHING")
        malformed_capture["rows"][0]["classifier_phase"] = (
            "NOT_A_BOUNDED_PHASE"
        )
        _write_capture(tmp_path, "malformed.json", malformed_capture)
        report = cas_reachability_report(tmp_path, max_age_days=7.0)
        assert report["captures_scanned"] == 2
        assert report["captures_skipped"] == 1  # malformed
        assert report["captures_skipped_stale"] == 1  # stale

    def test_captures_skipped_stale_always_present_in_report(
        self, tmp_path: Path
    ):
        # Even when the filter is unused, the field is present
        # with the documented shape (0).
        report = cas_reachability_report(tmp_path)
        assert "captures_skipped_stale" in report
        assert report["captures_skipped_stale"] == 0

    def test_captures_skipped_stale_present_when_dir_missing(
        self, tmp_path: Path
    ):
        report = cas_reachability_report(
            tmp_path / "no-such-dir", max_age_days=7.0
        )
        assert "captures_skipped_stale" in report
        assert report["captures_skipped_stale"] == 0

    def test_filter_skips_before_fingerprint_work(
        self, tmp_path: Path
    ):
        """[WORKFLOW-J.10.FRESHNESS 2026-09-14] The freshness
        filter runs BEFORE the dedup logic. A stale capture
        doesn't burn cycles on fingerprint computation AND
        doesn't appear in ``duplicates_by_branch``.
        """
        old_ts = (
            datetime.now(timezone.utc) - timedelta(days=400)
        ).isoformat()
        cap = _make_capture(
            "CAS_MATCHING", generated_at_utc=old_ts
        )
        _write_capture(tmp_path, "a.json", cap)
        _write_capture(tmp_path, "b.json", cap)
        report = cas_reachability_report(tmp_path, max_age_days=7.0)
        # Both stale -> both skipped (not duplicates, not counted).
        assert report["captures_scanned"] == 2
        assert report["captures_skipped_stale"] == 2
        assert report["captures_skipped"] == 0
        # No duplicates surfaced because the fingerprint path
        # never ran for stale captures.
        assert report["duplicates_by_branch"]["CAS_MATCHING"] == 0


# ---------------------------------------------------------------------------
# 3. format_report + update_summary surfaces


class TestFormatReportFreshness:
    """The human-readable CLI output surfaces stale info."""

    def test_format_report_includes_stale_when_present(self, tmp_path: Path):
        old_ts = (
            datetime.now(timezone.utc) - timedelta(days=400)
        ).isoformat()
        _write_capture(
            tmp_path,
            "stale.json",
            _make_capture("CAS_MATCHING", generated_at_utc=old_ts),
        )
        report = cas_reachability_report(tmp_path, max_age_days=7.0)
        rendered = format_report(report)
        assert "captures skipped (stale)" in rendered
        assert "1" in rendered  # the count

    def test_format_report_omits_stale_line_when_zero(self, tmp_path: Path):
        # No filter, no stale captures -> the human-readable
        # output doesn't mention the stale line at all.
        for phase in CAS_BRANCHES_REQUIRING_EVIDENCE:
            _write_capture(tmp_path, f"{phase}.json", _make_capture(phase))
        report = cas_reachability_report(tmp_path)
        rendered = format_report(report)
        assert "captures skipped (stale)" not in rendered


class TestSummaryFreshness:
    """The persistent SUMMARY surfaces the freshness filter."""

    def test_summary_with_stale_count(self, tmp_path: Path):
        old_ts = (
            datetime.now(timezone.utc) - timedelta(days=400)
        ).isoformat()
        for phase in CAS_BRANCHES_REQUIRING_EVIDENCE:
            _write_capture(
                tmp_path,
                f"{phase}.json",
                _make_capture(phase, generated_at_utc=old_ts),
            )
        report = cas_reachability_report(tmp_path, max_age_days=30.0)
        summary_path = tmp_path / "SUMMARY.md"
        update_summary(
            report, summary_path, captures_dir=tmp_path
        )
        body = summary_path.read_text(encoding="utf-8")
        # The verdict paragraph mentions the stale count.
        assert "stale" in body
        assert str(len(CAS_BRANCHES_REQUIRING_EVIDENCE)) in body

    def test_summary_without_stale_count(self, tmp_path: Path):
        # No filter -> the SUMMARY shows the original phrasing.
        for phase in CAS_BRANCHES_REQUIRING_EVIDENCE:
            _write_capture(tmp_path, f"{phase}.json", _make_capture(phase))
        report = cas_reachability_report(tmp_path)
        summary_path = tmp_path / "SUMMARY.md"
        update_summary(
            report, summary_path, captures_dir=tmp_path
        )
        body = summary_path.read_text(encoding="utf-8")
        # The verdict paragraph doesn't mention "stale" when
        # no filter was applied -- backwards-compatible phrasing.
        assert "skipped as stale" not in body
