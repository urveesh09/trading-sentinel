"""[O25k 2026-10-25] The 07:00 login reminder: the owner and the partner, each with their own Kite login link.
[O25M] The partner's reminder after a failed send: retried only when it provably never left, bounded."""
import asyncio
from datetime import datetime, timedelta
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
    trading = {"day": True, "outcomes": [], "calendar_reads": 0}      # outcomes: the next partner sends' states

    async def is_trading_day(day, db_path):
        trading["calendar_reads"] += 1
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
        state, error = trading["outcomes"].pop(0) if trading["outcomes"] else ("acknowledged", None)
        return partner_bot.PartnerSendResult(state == "acknowledged", message_id=len(sent["partner"]),
                                             state=state, error=error)

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
    assert len(sent["partner"]) == 1 and len(sent["owner"]) == 1      # [N11] the owner's nudge is once a day too
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


# ---------------------------------------------------------------------------
# [O25M, O25L R3] A failed reminder is retried only when it provably never left
# ---------------------------------------------------------------------------

UNSENT = ("unsent_connect", "ConnectError")


def _at(**delta):
    return MONDAY_7 + timedelta(**delta)


@pytest.mark.asyncio
async def test_a_reminder_that_never_left_is_sent_again_after_its_wait(morning):
    """[O25M, O25L R3] Reproduced: a send that never left (no connection) was recorded as reminded; a run 20 s later said
    already_reminded and nothing more was sent that day. Now it is sent again 5 minutes later, then not again."""
    sent, trading = morning
    trading["outcomes"].append(UNSENT)
    assert await pbs.morning_login_reminder(MONDAY_7) == {"status": "reminder_failed", "attempts": 1}
    assert await pbs.morning_login_reminder(_at(seconds=20)) == {"status": "retry_later", "attempts": 1}
    assert await pbs.morning_login_reminder(_at(minutes=5)) == {"status": "reminded", "attempts": 2}
    assert await pbs.morning_login_reminder(_at(minutes=10)) == {"status": "already_reminded"}
    [(first, *_), (second, *_)] = sent["partner"]
    assert first == second and first.startswith("🔑 Good morning! Please log in to Zerodha")


@pytest.mark.asyncio
async def test_a_reminder_that_may_have_arrived_or_was_refused_is_never_sent_again(morning):
    """A timeout after the request left may have arrived; Telegram's 400 would refuse the same text again."""
    sent, trading = morning
    trading["outcomes"].append(("ambiguous_timeout", "ReadTimeout"))
    assert await pbs.morning_login_reminder(MONDAY_7) == {"status": "reminder_uncertain", "attempts": 1}
    for minutes in (5, 15, 35):
        assert await pbs.morning_login_reminder(_at(minutes=minutes)) == {"status": "already_reminded"}
    assert len(sent["partner"]) == 1
    tuesday = _at(days=1)
    trading["outcomes"] += [("rejected", "telegram_http_502"), ("rejected", "telegram_http_400")]
    assert await pbs.morning_login_reminder(tuesday) == {"status": "reminder_failed", "attempts": 1}    # a 5xx
    assert await pbs.morning_login_reminder(tuesday + timedelta(minutes=5)) == {"status": "reminder_refused",
                                                                                  "attempts": 2}
    assert await pbs.morning_login_reminder(tuesday + timedelta(minutes=30)) == {"status": "already_reminded"}
    assert len(sent["partner"]) == 3


@pytest.mark.asyncio
async def test_retries_stop_after_four_sends_and_at_the_windows_end(morning):
    sent, trading = morning
    trading["outcomes"] += [UNSENT] * 4
    statuses = [(await pbs.morning_login_reminder(_at(minutes=m)))["status"] for m in (0, 4, 5, 14, 15, 35, 75)]
    assert statuses == ["reminder_failed", "retry_later", "reminder_failed", "retry_later", "reminder_failed",
                        "reminder_undelivered", "already_reminded"]
    assert len(sent["partner"]) == 4                                     # 07:00, 07:05, 07:15, 07:35
    tuesday = _at(days=1)
    trading["outcomes"].append(UNSENT)
    await pbs.morning_login_reminder(tuesday)
    assert await pbs.morning_login_reminder(tuesday + timedelta(minutes=91)) == {"status": "outside_window"}
    assert await pbs.morning_login_reminder(tuesday - timedelta(minutes=1)) == {"status": "outside_window"}
    assert len(sent["partner"]) == 5


@pytest.mark.asyncio
async def test_a_login_before_the_retry_stops_it(morning, monkeypatch):
    sent, trading = morning
    trading["outcomes"].append(UNSENT)
    await pbs.morning_login_reminder(MONDAY_7)
    monkeypatch.setattr(pbs, "connected", lambda now=None: True)
    assert await pbs.morning_login_reminder(_at(minutes=5)) == {"status": "already_logged_in"}
    assert len(sent["partner"]) == 1


@pytest.mark.asyncio
async def test_two_runs_at_once_send_it_once_and_a_send_cut_off_by_a_restart_is_not_repeated(morning, monkeypatch):
    import partner_bot
    sent, _ = morning
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow(text, *, kind="partner_msg", reply_markup=None):
        sent["partner"].append((text, kind, reply_markup))
        entered.set()
        await release.wait()
        return partner_bot.PartnerSendResult(True, message_id=1, state="acknowledged")

    monkeypatch.setattr(partner_bot, "send_partner_result", slow)
    first = asyncio.create_task(pbs.morning_login_reminder(MONDAY_7))      # the 07:00 job
    await entered.wait()
    assert await pbs.morning_login_reminder(_at(seconds=1)) == {"status": "in_progress", "attempts": 1}  # the tick
    release.set()
    assert await first == {"status": "reminded", "attempts": 1}
    assert len(sent["partner"]) == 1
    # Tuesday the engine stops mid-send: the send was claimed, its outcome never written. It may have arrived.
    tuesday = _at(days=1)
    import partner_orchestrator as po
    assert await po._claim_daily(settings.DB_PATH, "login_reminder", tuesday.date().isoformat(), 1, tuesday,
                                 "🔑 Good morning!", None)
    assert await pbs.morning_login_reminder(tuesday + timedelta(seconds=30)) == {"status": "in_progress",
                                                                              "attempts": 1}
    assert await pbs.morning_login_reminder(tuesday + timedelta(minutes=5)) == {"status": "reminder_uncertain",
                                                                                  "attempts": 1}
    assert len(sent["partner"]) == 1


@pytest.mark.asyncio
async def test_the_retry_tick_sends_a_reminder_a_restart_missed_and_reads_nothing_outside_its_window(morning,
                                                                                                       monkeypatch):
    sent, trading = morning

    def at(moment):
        monkeypatch.setattr(boot, "datetime", SimpleNamespace(now=lambda tz=None: moment,
                                                              fromisoformat=datetime.fromisoformat))

    monkeypatch.setattr(boot, "_reminder_sent_for", None)
    at(_at(minutes=10))                     # the engine restarted at 07:00: the 07:00 run never happened
    await boot.login_reminder_retry_tick()
    assert len(sent["partner"]) == 1 and len(sent["owner"]) == 1      # [N11] the owner's missed nudge goes too
    reads = trading["calendar_reads"]
    at(_at(minutes=110))                    # 08:50: past the 08:00 reminder's window as well
    await boot.login_reminder_retry_tick()
    assert trading["calendar_reads"] == reads and len(sent["partner"]) == 1
    trading["day"] = False
    at(_at(days=1, minutes=10))
    await boot.login_reminder_retry_tick()
    assert len(sent["partner"]) == 1


def test_the_retry_tick_is_scheduled_every_five_minutes_in_the_window():
    import inspect

    import scheduler_setup
    source = inspect.getsource(scheduler_setup)
    assert ('login_reminder_retry_tick, "cron",\n'
            '        hour=f"{settings.LOGIN_REMINDER_HOUR}-{min(settings.LOGIN_REMINDER_HOUR + 2, 23)}", minute="*/5",\n'
            '        id="partner_login_reminder_retry"') in source
    import partner_orchestrator as po
    assert (po.DAILY_ATTEMPTS, po.DAILY_RETRY_MIN, pbs.LOGIN_REMINDER_WINDOW_MIN) == (4, 5, 90)


def test_the_owners_alert_log_says_whether_telegram_took_it_on_the_first_try():
    import operator_alert

    class Answer:
        def __init__(self, body):
            self.body = body

        def json(self):
            if isinstance(self.body, Exception):
                raise self.body
            return self.body

    assert operator_alert._first_try(Answer({"success": True, "delivered": True})) is True
    assert operator_alert._first_try(Answer({"success": True, "delivered": False})) is False
    assert operator_alert._first_try(Answer({"success": True})) is None
    assert operator_alert._first_try(Answer(ValueError("not json"))) is None


# ---------------------------------------------------------------------------
# [N11 2026-11-11] The 08:00 second reminder, and the owner's nudge after a late start
# ---------------------------------------------------------------------------

def _clock_at(monkeypatch, moment):
    monkeypatch.setattr(boot, "datetime", SimpleNamespace(now=lambda tz=None: moment,
                                                          fromisoformat=datetime.fromisoformat))


@pytest.mark.asyncio
async def test_the_partner_still_not_logged_in_at_eight_is_reminded_again_once(morning, monkeypatch):
    sent, _ = morning
    monkeypatch.setattr(boot, "_reminder_sent_for", None)
    await boot.premarket_login_nudge()                                   # 07:00: owner + partner
    for minutes in (5, 30, 55):                                          # 07:05 .. 07:55: nothing more
        _clock_at(monkeypatch, _at(minutes=minutes))
        await boot.login_reminder_retry_tick()
    assert [k for _, k, _ in sent["partner"]] == ["login_reminder"] and len(sent["owner"]) == 1
    for minutes in (60, 65, 90, 105):                                    # 08:00, 08:05, 08:30, 08:45
        _clock_at(monkeypatch, _at(minutes=minutes))
        await boot.login_reminder_retry_tick()
    assert [k for _, k, _ in sent["partner"]] == ["login_reminder", "login_reminder_2"] and len(sent["owner"]) == 1
    text, _, keyboard = sent["partner"][1]
    assert text == ("🔑 You are not logged in to Zerodha yet today (Mon 26 Oct).\n"
                    "Until you log in, the trade watch is off: no buy plans, stop checks or loss warnings. "
                    "Tap the button below.")
    [[button]] = keyboard["inline_keyboard"]
    assert button == {"text": "🔑 Log in to Zerodha",
                      "url": "https://kite.zerodha.com/connect/login?v=3&api_key=partnerkey"}


@pytest.mark.asyncio
async def test_no_second_reminder_after_a_login_outside_its_window_or_on_a_closed_day(morning, monkeypatch):
    sent, trading = morning
    eight = _at(minutes=60)
    assert (await pbs.second_login_reminder(eight - timedelta(minutes=1)))["status"] == "outside_window"
    assert (await pbs.second_login_reminder(eight + timedelta(minutes=46)))["status"] == "outside_window"
    monkeypatch.setattr(pbs, "connected", lambda now=None: True)
    assert (await pbs.second_login_reminder(eight))["status"] == "already_logged_in"
    monkeypatch.setattr(pbs, "connected", lambda now=None: False)
    trading["day"] = False
    _clock_at(monkeypatch, eight)
    await boot.login_reminder_retry_tick()
    assert sent["partner"] == [] and sent["owner"] == []


@pytest.mark.asyncio
async def test_a_late_first_reminder_holds_the_second_back_for_thirty_minutes(morning, monkeypatch):
    """A PC that boots at 07:40 sends the 07:00 reminder at 07:40: the 08:00 one waits until 08:10."""
    sent, _ = morning
    assert (await pbs.morning_login_reminder(_at(minutes=40)))["status"] == "reminded"
    assert await pbs.second_login_reminder(_at(minutes=60)) == {"status": "too_soon"}
    assert await pbs.second_login_reminder(_at(minutes=69)) == {"status": "too_soon"}
    assert (await pbs.second_login_reminder(_at(minutes=70)))["status"] == "reminded"
    assert await pbs.second_login_reminder(_at(minutes=75)) == {"status": "already_reminded"}
    assert [k for _, k, _ in sent["partner"]] == ["login_reminder", "login_reminder_2"]


@pytest.mark.asyncio
async def test_nov11_a_pc_booted_at_0718_still_gives_the_owner_one_nudge_and_the_partner_two(morning, monkeypatch):
    """[N11] Reproduced: Nov 11 the PC booted at 07:18 and the engine at 07:19, after the 07:00 job (the scheduler's
    jobs are in memory, so a missed run is never made up). The partner's reminder went at 07:20 from the retry tick;
    the owner had no nudge, and the partner never logged in. Now: the owner's nudge at 07:20, once, a restart and a
    second tick included; the partner's second reminder at 08:00."""
    sent, _ = morning
    monkeypatch.setattr(boot, "_reminder_sent_for", None)
    for minutes in range(20, 110, 5):                                    # every tick from 07:20 to 08:45
        _clock_at(monkeypatch, _at(minutes=minutes))
        if minutes == 30:
            monkeypatch.setattr(boot, "_nudge_lock", asyncio.Lock())     # an engine restart at 07:30
        await boot.login_reminder_retry_tick()
    [(owner_text, event)] = sent["owner"]
    assert event == "premarket_login_nudge" and owner_text.startswith("🔑 Good morning. Kite login needed for today")
    assert [k for _, k, _ in sent["partner"]] == ["login_reminder", "login_reminder_2"]


@pytest.mark.asyncio
async def test_the_owners_catch_up_is_silent_with_todays_token_after_the_0800_alert_and_retries_a_refused_alert(
        morning, monkeypatch):
    sent, _ = morning
    _clock_at(monkeypatch, _at(minutes=20))
    monkeypatch.setattr(boot, "token_is_fresh_today", lambda: True)
    await boot.login_reminder_retry_tick()
    assert sent["owner"] == []
    monkeypatch.setattr(boot, "token_is_fresh_today", lambda: False)
    monkeypatch.setattr(boot, "_reminder_sent_for", _at(minutes=20).date().isoformat())   # 08:00 alert already out
    await boot.login_reminder_retry_tick()
    assert sent["owner"] == []
    monkeypatch.setattr(boot, "_reminder_sent_for", None)
    import operator_alert
    answers = [False, True]

    async def gateway(text, event="operator_alert"):
        sent["owner"].append((text, event))
        return answers.pop(0)

    monkeypatch.setattr(operator_alert, "notify_operator", gateway)
    for minutes in (25, 30, 35):
        _clock_at(monkeypatch, _at(minutes=minutes))
        await boot.login_reminder_retry_tick()
    assert len(sent["owner"]) == 2                                       # refused at 07:25, accepted at 07:30, then none
