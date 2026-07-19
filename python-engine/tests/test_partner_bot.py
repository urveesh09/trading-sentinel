"""
[PARTNER-TIPS-TESTS 2026-07-18] Partner sender transport (plan WS4):
disabled-by-default means ZERO network bytes; retry ladder + Telegram
429 retry_after honored; failures log loudly and return False without
raising; oversize messages truncate instead of 400ing.
"""
import asyncio

import pytest

import partner_bot
from config import Settings, settings


class _Resp:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body if body is not None else {"ok": True}

    def json(self):
        return self._body


class _FakeClient:
    """Stands in for httpx.AsyncClient; scripted responses per attempt."""
    script = []          # list of _Resp or Exception, consumed per call
    posts = []           # recorded (url, json) tuples

    def __init__(self, *a, **kw):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, timeout=None):
        _FakeClient.posts.append((url, json))
        item = _FakeClient.script.pop(0) if _FakeClient.script else _Resp()
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "PARTNER_BOT_ENABLED", True)
    monkeypatch.setattr(settings, "PARTNER_TELEGRAM_BOT_TOKEN", "test-token")
    monkeypatch.setattr(settings, "PARTNER_TELEGRAM_CHAT_ID", "12345678")
    monkeypatch.setattr(partner_bot.httpx, "AsyncClient", _FakeClient)
    monkeypatch.setattr(partner_bot, "RETRY_DELAYS_SEC", (0, 0, 0))
    _FakeClient.script = []
    _FakeClient.posts = []
    return _FakeClient


def test_disabled_by_default(monkeypatch):
    # Shipped CODE default is off. Assert the DECLARED field default, not the
    # loaded singleton -- the singleton reflects whatever the local/prod .env
    # sets (dev .env enables it), so reading it here would test the machine,
    # not the code.
    assert Settings.model_fields["PARTNER_BOT_ENABLED"].default is False
    # And with the flag off + no creds, the feature is a total no-op.
    monkeypatch.setattr(settings, "PARTNER_BOT_ENABLED", False)
    monkeypatch.setattr(settings, "PARTNER_TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(settings, "PARTNER_TELEGRAM_CHAT_ID", "")
    assert partner_bot.partner_enabled() is False


@pytest.mark.asyncio
async def test_disabled_sends_zero_bytes(monkeypatch):
    # Pin the disabled state explicitly rather than relying on ambient .env.
    monkeypatch.setattr(settings, "PARTNER_BOT_ENABLED", False)

    class _MustNotConstruct:
        def __init__(self, *a, **kw):
            raise AssertionError("network client constructed while disabled")

    monkeypatch.setattr(partner_bot.httpx, "AsyncClient", _MustNotConstruct)
    assert await partner_bot.send_partner("hello") is False


@pytest.mark.asyncio
async def test_missing_creds_disable_even_when_flag_on(monkeypatch):
    monkeypatch.setattr(settings, "PARTNER_BOT_ENABLED", True)
    monkeypatch.setattr(settings, "PARTNER_TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(settings, "PARTNER_TELEGRAM_CHAT_ID", "123")
    assert partner_bot.partner_enabled() is False


@pytest.mark.asyncio
async def test_happy_path_sends_to_partner_chat(enabled):
    assert await partner_bot.send_partner("tip body", kind="signal") is True
    assert len(enabled.posts) == 1
    url, payload = enabled.posts[0]
    assert "bottest-token/sendMessage" in url
    assert payload["chat_id"] == "12345678"
    assert payload["text"] == "tip body"
    # plain text by design: a parse_mode 400 must never eat a tip
    assert "parse_mode" not in payload


@pytest.mark.asyncio
async def test_retry_ladder_recovers(enabled):
    enabled.script = [RuntimeError("net down"), _Resp(500, {"ok": False}), _Resp()]
    assert await partner_bot.send_partner("x") is True
    assert len(enabled.posts) == 3


@pytest.mark.asyncio
async def test_429_retry_after_honored(enabled, monkeypatch):
    sleeps = []
    real_sleep = asyncio.sleep

    async def _spy(sec):
        sleeps.append(sec)
        await real_sleep(0)

    monkeypatch.setattr(partner_bot.asyncio, "sleep", _spy)
    enabled.script = [
        _Resp(429, {"ok": False, "parameters": {"retry_after": 7}}),
        _Resp(),
    ]
    assert await partner_bot.send_partner("x") is True
    assert 7 in sleeps


@pytest.mark.asyncio
async def test_all_attempts_fail_returns_false_without_raising(enabled):
    enabled.script = [RuntimeError("boom")] * 4
    assert await partner_bot.send_partner("x") is False
    assert len(enabled.posts) == 4    # initial + 3-rung ladder


@pytest.mark.asyncio
async def test_oversize_message_truncates(enabled):
    big = "y" * (partner_bot.TELEGRAM_MAX_LEN + 500)
    assert await partner_bot.send_partner(big) is True
    _, payload = enabled.posts[0]
    assert len(payload["text"]) <= partner_bot.TELEGRAM_MAX_LEN
    assert payload["text"].endswith("[...truncated]")
