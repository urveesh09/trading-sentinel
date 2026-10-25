"""[O25k 2026-10-25] The 07:00 login reminder: the owner and the partner, each with their own Kite login link."""
from datetime import datetime
from types import SimpleNamespace

import pytest
import pytest_asyncio
import pytz

import daily_bootstrap as boot
import partner_broker_sync as pbs
from config import settings

IST = pytz.timezone("Asia/Kolkata")
MONDAY_7 = IST.localize(datetime(2026, 10, 26, 7, 0))


@pytest_asyncio.fixture
async def morning(tmp_path, monkeypatch):
    """A trading-day 07:00 with no logins; records what reaches the owner and the partner."""
    import main
    import operator_alert
    import partner_bot

    from partner_orchestrator import init_partner_db
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "cache.db"))
    await init_partner_db(settings.DB_PATH)
    monkeypatch.setattr(settings, "PARTNER_KITE_API_KEY", "partnerkey")
    monkeypatch.setattr(settings, "PARTNER_KITE_API_SECRET", "partnersecret")
    monkeypatch.setattr(settings, "PARTNER_KITE_USER_ID", "PA1234")
    monkeypatch.setattr(settings, "PARTNER_ZERODHA_SYNC_ENABLED", True)
    monkeypatch.setenv("ZERODHA_API_KEY", "ownerkey")
    monkeypatch.setattr(boot, "datetime", SimpleNamespace(now=lambda tz=None: MONDAY_7,
                                                          fromisoformat=datetime.fromisoformat))
    trading = {"day": True}

    async def is_trading_day(day, db_path):
        return trading["day"]

    monkeypatch.setattr(main, "is_trading_day", is_trading_day)
    monkeypatch.setattr(boot, "token_is_fresh_today", lambda: False)
    monkeypatch.setattr(boot, "pending_tasks", lambda: ["penny_universe", "fno_instruments"])
    monkeypatch.setattr(pbs, "_session", None)
    sent = {"owner": [], "partner": []}

    async def notify(text, event="operator_alert"):
        sent["owner"].append((text, event))
        return True

    async def partner(text, *, kind="partner_msg", reply_markup=None):
        sent["partner"].append((text, kind, reply_markup))
        return SimpleNamespace(delivered=True)

    monkeypatch.setattr(operator_alert, "notify_operator", notify)
    monkeypatch.setattr(partner_bot, "send_partner_result", partner)
    monkeypatch.setattr(partner_bot, "partner_enabled", lambda: True)
    return sent, trading


@pytest.mark.asyncio
async def test_both_get_their_own_login_link_at_seven(morning):
    sent, _ = morning
    await boot.premarket_login_nudge()
    [(owner_text, event)] = sent["owner"]
    assert event == "premarket_login_nudge"
    assert "Log in here: https://kite.zerodha.com/connect/login?v=3&api_key=ownerkey" in owner_text
    assert owner_text.endswith("Pending: penny_universe, fno_instruments.") and "10 minutes out" not in owner_text
    [(partner_text, kind, keyboard)] = sent["partner"]
    assert kind == "login_reminder" and partner_text.startswith("🔑 Good morning! Please log in to Zerodha for today")
    assert "never place a trade" in partner_text and "ownerkey" not in partner_text
    [[button]] = keyboard["inline_keyboard"]
    assert button == {"text": "🔑 Log in to Zerodha",
                      "url": "https://kite.zerodha.com/connect/login?v=3&api_key=partnerkey"}


@pytest.mark.asyncio
async def test_the_partner_is_reminded_once_a_day_and_never_when_already_logged_in(morning, monkeypatch):
    sent, _ = morning
    await boot.premarket_login_nudge()
    await boot.premarket_login_nudge()                                   # a second run the same morning
    assert len(sent["partner"]) == 1 and len(sent["owner"]) == 2      # the owner's nudge has no once-a-day key
    monkeypatch.setattr(pbs, "connected", lambda now=None: True)
    assert (await pbs.morning_login_reminder(MONDAY_7.replace(day=27)))["status"] == "already_logged_in"
    assert len(sent["partner"]) == 1


@pytest.mark.asyncio
async def test_an_owner_already_logged_in_still_has_the_partner_reminded(morning, monkeypatch):
    sent, _ = morning
    monkeypatch.setattr(boot, "token_is_fresh_today", lambda: True)
    await boot.premarket_login_nudge()
    assert sent["owner"] == [] and len(sent["partner"]) == 1


@pytest.mark.asyncio
async def test_nothing_on_a_closed_day_and_a_partner_failure_never_stops_the_owners(morning, monkeypatch):
    sent, trading = morning
    trading["day"] = False
    await boot.premarket_login_nudge()
    assert sent == {"owner": [], "partner": []}
    trading["day"] = True

    async def broken(now=None):
        raise RuntimeError("partner database locked")

    monkeypatch.setattr(pbs, "morning_login_reminder", broken)
    await boot.premarket_login_nudge()
    assert len(sent["owner"]) == 1 and sent["partner"] == []


def test_the_reminder_is_scheduled_at_seven_on_the_login_settings():
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    import scheduler_setup
    assert (settings.LOGIN_REMINDER_HOUR, settings.LOGIN_REMINDER_MINUTE) == (7, 0)
    source = __import__("inspect").getsource(scheduler_setup)
    assert "hour=settings.LOGIN_REMINDER_HOUR, minute=settings.LOGIN_REMINDER_MINUTE" in source
    assert AsyncIOScheduler is not None
