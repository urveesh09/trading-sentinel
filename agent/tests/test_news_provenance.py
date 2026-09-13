"""[WORKFLOW-I I2 2026-09-13] News-provenance acceptance.

Closes I2 of workstream I per ``docs/NEXT_AGENT_PLAN.md`` section 13.
Satisfies the §13 mandate: *"News must have publication/event
timestamps and a reliable source; an unsupported model statement
is not a market fact."*

Coverage
--------
1. NewsItem dataclass shape.
2. ``fetch_news_items`` returns ``List[NewsItem]`` (not strings).
3. ``<pubDate>`` parsing for both Yahoo Finance and Google News
   RFC 822 / RFC 1123 formats.
4. Missing ``<pubDate>`` is preserved with
   ``published_at_parsed=None`` and ``age_label="stale_or_unknown"``.
5. ``<source>`` element captured; falls back to URL hostname.
6. ``<link>`` captured; absent link -> empty source_url.
7. ``_age_label`` rendering: ``fresh``, ``N hours ago``,
   ``N days ago``, ``stale_aged_Nd``, ``stale_or_unknown``,
   ``future_dated`` (clock skew).
8. ``scrape_sentiment`` output includes age labels + source URLs.
9. Backwards compatibility: ``fetch_rss_feed`` still returns the
   legacy string format.
10. Network failure is graceful: empty list, no crash.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch, MagicMock

import pytest


# ---- (1) NewsItem shape ---------------------------------------------------

class TestNewsItemShape:
    def test_newsitem_carries_required_fields(self) -> None:
        from agent import NewsItem
        now = datetime.now(timezone.utc)
        item = NewsItem(
            title="XYZ reports Q2 beat",
            source_url="https://news.example.com/x",
            published_at_raw="Tue, 13 Sep 2026 14:25:00 +0530",
            published_at_parsed=now,
            source_name="example.com",
            age_label="fresh",
        )
        assert item.title == "XYZ reports Q2 beat"
        assert item.source_url == "https://news.example.com/x"
        assert item.published_at_raw == "Tue, 13 Sep 2026 14:25:00 +0530"
        assert item.published_at_parsed == now
        assert item.source_name == "example.com"
        assert item.age_label == "fresh"
        assert item.has_publication_timestamp is True

    def test_newsitem_frozen(self) -> None:
        """NewsItem is frozen; mutating an attribute raises."""
        from agent import NewsItem
        item = NewsItem(
            title="x", source_url="", published_at_raw="",
            published_at_parsed=None, source_name="",
            age_label="stale_or_unknown",
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            item.title = "y"  # type: ignore[misc]


# ---- (2) fetch_news_items return shape ------------------------------------

class TestFetchNewsItems:
    def _mock_response(self, xml_text: str) -> MagicMock:
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.content = xml_text.encode("utf-8")
        return resp

    def test_returns_list_of_newsitem(self) -> None:
        from agent import fetch_news_items, NewsItem
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>Sample headline one</title>
              <link>https://example.com/news/1</link>
              <pubDate>Tue, 13 Sep 2026 14:25:00 +0530</pubDate>
              <source url="https://example.com">Example News</source>
            </item>
            <item>
              <title>Sample headline two</title>
              <link>https://example.com/news/2</link>
              <pubDate>Tue, 13 Sep 2026 15:00:00 GMT</pubDate>
            </item>
          </channel>
        </rss>"""
        with patch("agent.requests.get", return_value=self._mock_response(xml)):
            items = fetch_news_items(
                "https://feeds.finance.yahoo.com/test", limit=4,
            )
        assert len(items) == 2
        assert all(isinstance(it, NewsItem) for it in items)
        assert items[0].title == "Sample headline one"
        assert items[0].source_url == "https://example.com/news/1"
        assert items[0].source_name == "Example News"
        assert items[0].published_at_parsed is not None
        assert items[1].source_url == "https://example.com/news/2"
        # No <source> element -> fallback to hostname.
        assert items[1].source_name == "feeds.finance.yahoo.com"

    def test_yahoo_pubdate_format_parses(self) -> None:
        """Yahoo Finance uses RFC 822 with numeric timezone offset.
        The parsed datetime is normalised to UTC, so 14:25:00+0530
        equals 08:55:00 UTC.
        """
        from agent import _parse_rss_pubdate
        dt = _parse_rss_pubdate("Tue, 13 Sep 2026 14:25:00 +0530")
        assert dt is not None
        assert dt.tzinfo is not None
        # 14:25:00 +0530 == 08:55:00 UTC.
        assert dt.hour == 8
        assert dt.minute == 55
        assert dt.utcoffset() == timedelta(0)  # normalised to UTC

    def test_google_pubdate_format_parses(self) -> None:
        """Google News uses RFC 1123 with 'GMT' timezone name."""
        from agent import _parse_rss_pubdate
        dt = _parse_rss_pubdate("Tue, 13 Sep 2026 08:55:00 GMT")
        assert dt is not None
        assert dt.tzinfo is not None
        assert dt.utcoffset() == timedelta(0)

    def test_missing_pubdate_keeps_item_with_stale_label(self) -> None:
        """Items without a parseable pubDate are preserved with
        age_label="stale_or_unknown". Per §13, the producer must
        surface feed quality issues, not silently drop them.
        """
        from agent import fetch_news_items
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>Headline with no timestamp</title>
              <link>https://example.com/x</link>
            </item>
          </channel>
        </rss>"""
        with patch("agent.requests.get",
                   return_value=self._mock_response(xml)):
            items = fetch_news_items("https://example.com/feed", limit=4)
        assert len(items) == 1
        assert items[0].published_at_parsed is None
        assert items[0].age_label == "stale_or_unknown"
        assert items[0].has_publication_timestamp is False

    def test_empty_pubdate_string_keeps_item(self) -> None:
        from agent import fetch_news_items
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>Empty pubDate</title>
              <link>https://example.com/y</link>
              <pubDate></pubDate>
            </item>
          </channel>
        </rss>"""
        with patch("agent.requests.get",
                   return_value=self._mock_response(xml)):
            items = fetch_news_items("https://example.com/feed", limit=4)
        assert len(items) == 1
        assert items[0].age_label == "stale_or_unknown"

    def test_missing_link_keeps_item_with_empty_source_url(self) -> None:
        from agent import fetch_news_items
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <item>
              <title>No link</title>
              <pubDate>Tue, 13 Sep 2026 14:25:00 +0530</pubDate>
            </item>
          </channel>
        </rss>"""
        with patch("agent.requests.get",
                   return_value=self._mock_response(xml)):
            items = fetch_news_items("https://example.com/feed", limit=4)
        assert len(items) == 1
        assert items[0].source_url == ""

    def test_network_failure_returns_empty_list(self) -> None:
        from agent import fetch_news_items
        with patch("agent.requests.get", side_effect=Exception("timeout")):
            items = fetch_news_items("https://example.com/feed", limit=4)
        assert items == []


# ---- (3) _age_label rendering ---------------------------------------------

class TestAgeLabel:
    def test_none_returns_stale_or_unknown(self) -> None:
        from agent import _age_label
        assert _age_label(None) == "stale_or_unknown"

    def test_less_than_one_hour_returns_fresh(self) -> None:
        from agent import _age_label
        now = datetime(2026, 9, 13, 14, 0, 0, tzinfo=timezone.utc)
        # 30 minutes ago -> fresh.
        pub = now - timedelta(minutes=30)
        assert _age_label(pub, now=now) == "fresh"

    def test_hours_ago_label(self) -> None:
        from agent import _age_label
        now = datetime(2026, 9, 13, 14, 0, 0, tzinfo=timezone.utc)
        pub = now - timedelta(hours=3)
        assert _age_label(pub, now=now) == "3 hours ago"

    def test_days_ago_label(self) -> None:
        from agent import _age_label
        now = datetime(2026, 9, 13, 14, 0, 0, tzinfo=timezone.utc)
        pub = now - timedelta(days=2)
        assert _age_label(pub, now=now) == "2 days ago"

    def test_stale_aged_label_over_seven_days(self) -> None:
        from agent import _age_label
        now = datetime(2026, 9, 13, 14, 0, 0, tzinfo=timezone.utc)
        pub = now - timedelta(days=14)
        assert _age_label(pub, now=now) == "stale_aged_14d"

    def test_future_dated_label_on_clock_skew(self) -> None:
        from agent import _age_label
        now = datetime(2026, 9, 13, 14, 0, 0, tzinfo=timezone.utc)
        pub = now + timedelta(minutes=5)  # future-dated
        assert _age_label(pub, now=now) == "future_dated"


# ---- (4) scrape_sentiment output -----------------------------------------

class TestScrapeSentiment:
    def _empty_response(self) -> MagicMock:
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.content = b"<?xml version='1.0'?><rss version='2.0'><channel></channel></rss>"
        return resp

    def _stub_news(self, xml: str) -> MagicMock:
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.content = xml.encode("utf-8")
        return resp

    def test_output_includes_age_label(self) -> None:
        from agent import scrape_sentiment
        now = datetime.now(timezone.utc)
        # Construct an item with a recent pubDate.
        iso_now = now.strftime("%a, %d %b %Y %H:%M:%S +0000")
        xml = f"""<?xml version="1.0"?>
        <rss version="2.0"><channel>
          <item>
            <title>Fresh headline</title>
            <link>https://example.com/x</link>
            <pubDate>{iso_now}</pubDate>
          </item>
        </channel></rss>"""
        with patch("agent.requests.get",
                   return_value=self._stub_news(xml)):
            prompt = scrape_sentiment("TCS")
        assert "[fresh]" in prompt
        assert "Fresh headline" in prompt
        assert "url: https://example.com/x" in prompt
        assert "YAHOO FINANCE FEED:" in prompt
        assert "BROADER MARKET FEED:" in prompt

    def test_output_flags_stale_items(self) -> None:
        """An item older than 7 days is labelled stale_aged_Nd so
        the model cannot mistake it for fresh news.
        """
        from agent import scrape_sentiment
        # Use a date 30 days ago.
        old = datetime.now(timezone.utc) - timedelta(days=30)
        iso_old = old.strftime("%a, %d %b %Y %H:%M:%S +0000")
        xml = f"""<?xml version="1.0"?>
        <rss version="2.0"><channel>
          <item>
            <title>Stale headline</title>
            <link>https://example.com/old</link>
            <pubDate>{iso_old}</pubDate>
          </item>
        </channel></rss>"""
        with patch("agent.requests.get",
                   return_value=self._stub_news(xml)):
            prompt = scrape_sentiment("TCS")
        assert "[stale_aged_30d]" in prompt
        assert "Stale headline" in prompt

    def test_output_flags_missing_timestamp(self) -> None:
        from agent import scrape_sentiment
        xml = """<?xml version="1.0"?>
        <rss version="2.0"><channel>
          <item>
            <title>No timestamp here</title>
            <link>https://example.com/y</link>
          </item>
        </channel></rss>"""
        with patch("agent.requests.get",
                   return_value=self._stub_news(xml)):
            prompt = scrape_sentiment("TCS")
        assert "[stale_or_unknown]" in prompt
        assert "No timestamp here" in prompt


# ---- (5) Backwards compatibility -----------------------------------------

class TestBackwardsCompatibility:
    def _stub_news(self, xml: str) -> MagicMock:
        resp = MagicMock()
        resp.status_code = 200
        resp.raise_for_status = MagicMock()
        resp.content = xml.encode("utf-8")
        return resp

    def test_fetch_rss_feed_returns_string_legacy_format(self) -> None:
        from agent import fetch_rss_feed
        xml = """<?xml version="1.0"?>
        <rss version="2.0"><channel>
          <item><title>One</title><link>x</link></item>
          <item><title>Two</title><link>y</link></item>
        </channel></rss>"""
        with patch("agent.requests.get",
                   return_value=self._stub_news(xml)):
            result = fetch_rss_feed("https://example.com/feed", limit=4)
        assert isinstance(result, str)
        assert "- One | - Two" == result

    def test_fetch_rss_feed_empty_on_network_failure(self) -> None:
        from agent import fetch_rss_feed
        with patch("agent.requests.get", side_effect=Exception("down")):
            result = fetch_rss_feed("https://example.com/feed", limit=4)
        assert result == ""

    def test_scrape_sentiment_empty_on_both_failure(self) -> None:
        from agent import scrape_sentiment
        with patch("agent.requests.get", side_effect=Exception("down")):
            result = scrape_sentiment("TCS")
        assert result == ""
