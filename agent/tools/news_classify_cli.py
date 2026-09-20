"""[WORKFLOW-I.4.D 2026-09-14] Operator CLI for the news classifier.

This CLI runs the bounded classifier on a ticker or on a
pre-fetched JSON file of news items. It does NOT touch the
verdict pipeline; it is a stand-alone operator tool for
ad-hoc classification runs (e.g. debugging the classifier,
inspecting what categories a ticker gets, or auditing the
classifier's behaviour against a known input set).

The CLI is intentionally structured so the heavy agent.py
imports (which open network sockets at import time and run a
Telegram heartbeat) are NOT loaded just to run --input. For
--input the CLI uses a lightweight stand-in item class with
the source attributes the classifier reads (title, age label, source URL/name
and parsed publication clock). For --ticker the CLI loads
agent.py to use its fetch_news_items; if that load fails the
CLI exits 3 with a diagnostic.

Subcommands (mutually exclusive):

  --ticker TICKER
      Fetch the live Yahoo + Google news for ``TICKER`` and
      classify each item. Reuses the same URLs and limits as
      ``scrape_sentiment``.

  --input PATH
      Read a JSON file of news items and classify each.
      Expected schema:
        [{"title": "...", "source_url": "https://...",
          "published_at": "2026-09-20T09:00:00Z",
          "age_label": "...", "source_name": "..."}, ...]
      ``pubDate`` / ``published_at_raw`` RFC timestamps are also accepted.
      Missing/invalid URL or aware timestamp remains a fail-closed UNKNOWN.

  --dry-run
      Do not call the model; instead, parse a fixed
      ``--input`` payload and render the empty-classification
      result (``UNKNOWN`` for every item) so operators can
      verify the JSON-rendering path without hitting MiniMax.

  --json
      Emit machine-readable JSON to stdout instead of the
      human-readable table.

Exit codes:
  0  classifier ran (with or without results)
  1  invalid arguments
  2  network / fetch failure (only on --ticker when both
     feeds fail)
  3  classifier module not available OR agent.py import failed
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import news_classifier
from news_classifier import (
    ClassificationResult,
    NewsCategory,
)


# ---------------------------------------------------------------------------
# Lightweight stand-in item
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Item:
    """[WORKFLOW-I.4.D 2026-09-14] Lightweight stand-in for
    agent.NewsItem. We don't import
    ``agent.NewsItem`` (which transitively pulls in the
    heavy module) so the CLI module loads in <100ms without
    touching the network or Telegram.
    """

    title: str
    source_url: str = ""
    published_at_raw: str = ""
    published_at_parsed: Optional[Any] = None
    source_name: str = ""
    age_label: str = "unknown"


def _parse_publication_clock(raw: object) -> Optional[datetime]:
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        parsed = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except (TypeError, ValueError, OverflowError):
            return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _make_item(raw: Dict[str, Any]) -> _Item:
    """[WORKFLOW-I.4.D 2026-09-14] Build a stand-in _Item from
    a JSON dict (--input mode). Tolerates missing optional
    fields with field aliases (``url`` -> ``source_url``,
    ``pubDate`` -> ``published_at_raw``).
    """
    publication_raw = raw.get(
        "published_at",
        raw.get("published_at_raw", raw.get("pubDate", "")),
    )
    return _Item(
        title=str(raw.get("title", "")),
        source_url=str(raw.get("source_url", raw.get("url", ""))),
        published_at_raw=str(publication_raw),
        published_at_parsed=_parse_publication_clock(publication_raw),
        source_name=str(raw.get("source_name", "")),
        age_label=str(raw.get("age_label", "unknown")),
    )


def _fetch_items_for_ticker(ticker: str) -> List:
    """[WORKFLOW-I.4.D 2026-09-14] Fetch news items for
    ``ticker`` using the same URLs as ``agent.scrape_sentiment``.

    Imports ``fetch_news_items`` from ``agent`` lazily so the
    --input path doesn't load agent.py. If agent.py import
    fails (e.g. missing TELEGRAM env vars in a sandbox), the
    CLI exits 3 with a diagnostic -- the --input path is
    still usable.
    """
    import urllib.parse
    try:
        from agent import fetch_news_items
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"news_classify_cli: cannot load agent.fetch_news_items: "
            f"{type(exc).__name__}: {exc}\n"
            "  (--input mode does not need agent.py)\n"
        )
        sys.exit(3)
    yahoo_url = (
        f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}"
        "&region=US&lang=en-US"
    )
    encoded = urllib.parse.quote(f"{ticker} stock")
    google_url = (
        f"https://news.google.com/rss/search?q={encoded}&hl=en-US"
        "&gl=US&ceid=US:en"
    )
    items: List = []
    for url in (yahoo_url, google_url):
        try:
            items.extend(fetch_news_items(url, limit=4))
        except Exception:  # noqa: BLE001
            pass
    return items


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def _render_human_table(results: List[ClassificationResult]) -> str:
    """[WORKFLOW-I.4.D 2026-09-14] Render the classification
    results as a human-readable ASCII table.
    """
    if not results:
        return "(no items classified)\n"
    rows: List[str] = []
    rows.append(f"{'TITLE_HASH':<14}  {'CATEGORY':<12}  {'CONF':>6}  {'RATIONALE'}")
    rows.append("-" * 72)
    for r in results:
        rationale = (r.rationale or "")[:40]
        rows.append(
            f"{r.title_hash:<14}  "
            f"{r.category.value:<12}  "
            f"{r.confidence:>6.2f}  "
            f"{rationale}"
        )
    return "\n".join(rows) + "\n"


def _render_dry_run_table(items: List) -> str:
    """[WORKFLOW-I.4.D 2026-09-14] In dry-run mode, show what
    would have been classified (titles + UNKNOWN marker).
    """
    if not items:
        return "(dry-run: no items)\n"
    rows: List[str] = []
    rows.append(f"DRY RUN: {len(items)} item(s) would be classified as UNKNOWN")
    rows.append("-" * 72)
    for item in items:
        title = (getattr(item, "title", "") or "")[:60]
        rows.append(f"  - {title}")
    return "\n".join(rows) + "\n"


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="news_classify_cli",
        description=(
            "I.4.D news classifier CLI. Classifies a ticker's "
            "news (or a pre-fetched JSON list) against the "
            "8-category bounded taxonomy."
        ),
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--ticker",
        type=str,
        default=None,
        help="Fetch and classify live news for this NSE ticker.",
    )
    src.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Path to a JSON file of news items to classify.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip the model call; render what would have been "
             "classified. Useful for verifying the JSON-rendering "
             "path. Requires --input.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON to stdout.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=4,
        help="Per-feed item limit (default 4).",
    )
    return parser


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)

    # --- Step 1: build the item list ---
    items: List = []
    if args.ticker is not None:
        items = _fetch_items_for_ticker(args.ticker)
        if not items:
            sys.stderr.write(
                f"news_classify_cli: no items fetched for {args.ticker!r}\n"
            )
            return 2
    else:
        if not args.input.exists():
            sys.stderr.write(
                f"news_classify_cli: input file not found: {args.input}\n"
            )
            return 1
        try:
            raw = json.loads(args.input.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            sys.stderr.write(
                f"news_classify_cli: invalid JSON in {args.input}: {exc}\n"
            )
            return 1
        if not isinstance(raw, list):
            sys.stderr.write(
                f"news_classify_cli: --input must be a JSON array of items\n"
            )
            return 1
        items = [_make_item(r) for r in raw if isinstance(r, dict)]

    if not items:
        sys.stderr.write(
            "news_classify_cli: 0 valid items after parsing input\n"
        )
        return 1

    # --- Step 2: classify (or dry-run) ---
    if args.dry_run:
        if args.json:
            sys.stdout.write(json.dumps({
                "dry_run": True,
                "item_count": len(items),
                "titles": [getattr(it, "title", "") for it in items],
            }, indent=2) + "\n")
        else:
            sys.stdout.write(_render_dry_run_table(items))
        return 0

    results = news_classifier.classify_news_items(
        items, ticker=args.ticker or "UNKNOWN",
    )

    # --- Step 3: render ---
    if args.json:
        sys.stdout.write(json.dumps(
            news_classifier.to_dict(results), indent=2,
        ) + "\n")
    else:
        sys.stdout.write(_render_human_table(results))

    captured = sum(
        1 for r in results if r.category != NewsCategory.UNKNOWN
    )
    sys.stderr.write(
        f"news_classify_cli: classified {len(results)} items, "
        f"{captured} non-UNKNOWN\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
