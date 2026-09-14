"""[WORKFLOW-I.4.D 2026-09-14] Tests for the operator CLI.

The CLI runs without touching the verdict pipeline. It is
testable end-to-end via ``main(argv)`` and a mock
classifier + mock fetch path.

Exit code contract:
  0  success
  1  invalid arguments
  2  no items (--ticker with both feeds down)
  3  classifier module not available
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import news_classifier
from news_classifier import ClassificationResult, NewsCategory

from tools.news_classify_cli import (
    _Item,
    _make_item,
    _render_human_table,
    _render_dry_run_table,
    main,
)


def _stub_result(
    title_hash: str,
    category: NewsCategory,
    confidence: float,
    rationale: str = "",
) -> ClassificationResult:
    return ClassificationResult(
        ticker="Example", title_hash=title_hash,
        category=category, confidence=confidence,
        rationale=rationale, prompt_version="v1",
        classified_at=None,
    )


# ---------------------------------------------------------------------------
# _make_item
# ---------------------------------------------------------------------------


def test_make_item_minimal_dict():
    """A dict with only ``title`` produces an _Item with
    sensible defaults for the rest.
    """
    item = _make_item({"title": "Some headline"})
    assert isinstance(item, _Item)
    assert item.title == "Some headline"
    assert item.age_label == "unknown"
    assert item.source_name == ""


def test_make_item_full_dict():
    """All fields populated from the dict (with field aliases
    like ``url`` -> ``source_url``).
    """
    raw = {
        "title": "RELIANCE Q3 results",
        "url": "https://example.com/reliance-q3",
        "pubDate": "Thu, 14 Sep 2026 09:00:00 GMT",
        "source_name": "Reuters",
        "age_label": "fresh",
    }
    item = _make_item(raw)
    assert item.title == "RELIANCE Q3 results"
    assert item.source_url == "https://example.com/reliance-q3"
    assert item.source_name == "Reuters"
    assert item.age_label == "fresh"


# ---------------------------------------------------------------------------
# Human-table renderer
# ---------------------------------------------------------------------------


def test_render_human_table_empty_returns_placeholder():
    text = _render_human_table([])
    assert "no items classified" in text


def test_render_human_table_includes_title_hash_category_conf():
    results = [
        _stub_result("abc123def456", NewsCategory.EARNINGS, 0.92, "Q3 beat."),
        _stub_result("def789abc012", NewsCategory.REGULATORY, 0.85, "SEBI order."),
    ]
    text = _render_human_table(results)
    assert "abc123def456" in text
    assert "earnings" in text
    assert "0.92" in text
    assert "def789abc012" in text
    assert "regulatory" in text


def test_render_human_table_truncates_long_rationale():
    """A 200-char rationale is truncated to keep the table
    readable.
    """
    results = [
        _stub_result("h", NewsCategory.EARNINGS, 0.9, "x" * 200),
    ]
    text = _render_human_table(results)
    # The rationale column is bounded.
    assert "x" * 200 not in text


# ---------------------------------------------------------------------------
# Dry-run renderer
# ---------------------------------------------------------------------------


def test_render_dry_run_table_empty_returns_placeholder():
    text = _render_dry_run_table([])
    assert "no items" in text


def test_render_dry_run_table_lists_titles():
    """Dry-run mode shows what would have been classified."""
    items = [
        type("X", (), {"title": "RELIANCE Q3 results", "age_label": "fresh"}),
        type("X", (), {"title": "INFY guidance update", "age_label": "1h"}),
    ]
    text = _render_dry_run_table(items)
    assert "DRY RUN" in text
    assert "RELIANCE Q3 results" in text
    assert "INFY guidance update" in text


# ---------------------------------------------------------------------------
# main() — happy path
# ---------------------------------------------------------------------------


def test_main_input_mode_json(tmp_path):
    """--input PATH with --json: emits machine-readable JSON
    via the news_classifier.to_dict path.
    """
    input_path = tmp_path / "news.json"
    input_path.write_text(json.dumps([
        {"title": "headline A"},
        {"title": "headline B"},
    ]), encoding="utf-8")

    results = [
        _stub_result("aaaa1111bbbb", NewsCategory.EARNINGS, 0.9, "ok"),
        _stub_result("cccc2222dddd", NewsCategory.UNKNOWN, 0.0, ""),
    ]
    with patch.object(
        news_classifier, "classify_news_items", return_value=results,
    ):
        rc = main(["--input", str(input_path), "--json"])

    assert rc == 0
    # The CLI returned successfully (we don't capture stdout here,
    # but the test would have crashed on any exception).


def test_main_input_mode_human_table(tmp_path):
    """--input PATH without --json: emits the human-readable
    table.
    """
    input_path = tmp_path / "news.json"
    input_path.write_text(json.dumps([{"title": "headline"}]),
                          encoding="utf-8")

    with patch.object(
        news_classifier, "classify_news_items",
        return_value=[_stub_result("h", NewsCategory.EARNINGS, 0.8, "ok")],
    ):
        rc = main(["--input", str(input_path)])

    assert rc == 0


def test_main_dry_run_mode(tmp_path):
    """--dry-run skips the model call and renders the titles
    in a placeholder block.
    """
    input_path = tmp_path / "news.json"
    input_path.write_text(json.dumps([
        {"title": "headline 1"}, {"title": "headline 2"},
    ]), encoding="utf-8")

    # Patch classify_news_items; if it's called, the test fails
    # because dry-run must NOT hit the model.
    with patch.object(
        news_classifier, "classify_news_items",
        side_effect=AssertionError("dry-run must not classify"),
    ) as classify_mock:
        rc = main(["--input", str(input_path), "--dry-run"])
    assert rc == 0
    classify_mock.assert_not_called()


def test_main_dry_run_json(tmp_path):
    """--dry-run --json emits a JSON payload with dry_run=True
    and a list of titles.
    """
    input_path = tmp_path / "news.json"
    input_path.write_text(json.dumps([{"title": "x"}]), encoding="utf-8")
    with patch.object(
        news_classifier, "classify_news_items",
        return_value=[],
    ):
        rc = main(["--input", str(input_path), "--dry-run", "--json"])
    assert rc == 0


def test_main_input_file_not_found(tmp_path):
    """A non-existent --input file exits 1 with a stderr error."""
    missing = tmp_path / "does-not-exist.json"
    rc = main(["--input", str(missing)])
    assert rc == 1


def test_main_input_invalid_json(tmp_path):
    """An --input file with non-JSON content exits 1."""
    bad = tmp_path / "bad.json"
    bad.write_text("not json {", encoding="utf-8")
    rc = main(["--input", str(bad)])
    assert rc == 1


def test_main_input_not_a_list(tmp_path):
    """An --input file whose root is not a JSON list exits 1."""
    wrong = tmp_path / "wrong.json"
    wrong.write_text('{"not": "a list"}', encoding="utf-8")
    rc = main(["--input", str(wrong)])
    assert rc == 1


def test_main_input_empty_list_returns_error(tmp_path):
    """An --input file with an empty list (or all-invalid
    items) exits 1 -- there is nothing to classify.
    """
    empty = tmp_path / "empty.json"
    empty.write_text("[]", encoding="utf-8")
    rc = main(["--input", str(empty)])
    assert rc == 1


def test_main_input_with_invalid_items_only(tmp_path):
    """Items that are not dicts are silently dropped; if no
    valid items remain, exit 1.
    """
    only_invalid = tmp_path / "invalid.json"
    only_invalid.write_text(json.dumps(["not a dict", 42, None]),
                            encoding="utf-8")
    rc = main(["--input", str(only_invalid)])
    assert rc == 1


# ---------------------------------------------------------------------------
# main() — ticker mode
# ---------------------------------------------------------------------------


def test_main_ticker_no_items_returns_2():
    """When --ticker is supplied but both feeds return no items,
    exit 2 (operational fetch failure).
    """
    with patch(
        "tools.news_classify_cli._fetch_items_for_ticker",
        return_value=[],
    ):
        rc = main(["--ticker", "RELIANCE"])
    assert rc == 2


def test_main_ticker_with_items_calls_classifier():
    """--ticker with items: the CLI calls news_classifier
    .classify_news_items on the fetched items and renders.
    """
    items = [type("X", (), {"title": "h", "age_label": "fresh"})()]
    results = [_stub_result("h", NewsCategory.EARNINGS, 0.9, "ok")]

    with patch(
        "tools.news_classify_cli._fetch_items_for_ticker",
        return_value=items,
    ), patch.object(
        news_classifier, "classify_news_items", return_value=results,
    ) as classify_mock:
        rc = main(["--ticker", "RELIANCE"])
    assert rc == 0
    classify_mock.assert_called_once_with(items)


# ---------------------------------------------------------------------------
# CLI argument validation
# ---------------------------------------------------------------------------


def test_main_no_source_returns_error():
    """No --ticker and no --input: argparse error -> SystemExit(2)."""
    with pytest.raises(SystemExit):
        main([])


def test_main_both_ticker_and_input_returns_error():
    """--ticker and --input are mutually exclusive."""
    with pytest.raises(SystemExit):
        main(["--ticker", "RELIANCE", "--input", "x.json"])


# ---------------------------------------------------------------------------
# Output rendering integration
# ---------------------------------------------------------------------------


def test_human_table_output_format_includes_capture_summary(tmp_path, capsys):
    """After successful classification the CLI prints a stderr
    summary line: 'classified N items, M non-UNKNOWN'.
    """
    input_path = tmp_path / "news.json"
    input_path.write_text(json.dumps([{"title": "h"}]), encoding="utf-8")
    results = [
        _stub_result("h", NewsCategory.EARNINGS, 0.9, "ok"),
        _stub_result("h2", NewsCategory.UNKNOWN, 0.0, ""),
    ]
    with patch.object(
        news_classifier, "classify_news_items", return_value=results,
    ):
        main(["--input", str(input_path)])
    captured = capsys.readouterr()
    assert "classified 2 items" in captured.err
    assert "1 non-UNKNOWN" in captured.err
