"""[O25M 2026-10-25] The partner's once-a-day messages (the brief, the wrap, the coach note, the review prompt):
a send that provably never left is sent again from its stored text, bounded; one that may have arrived never is.

The O25L review's R3 note: these wrote their day's row whatever became of the send, so one failed connection
meant no message that day (the same pattern as the 07:00 reminder, fixed with the same ledger)."""
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
import pytz

import partner_bot
import partner_orchestrator as po
from config import settings

IST = pytz.timezone("Asia/Kolkata")
BRIEF_AT = IST.localize(datetime(2026, 10, 26, 9, 50))
DAY = BRIEF_AT.date().isoformat()
UNSENT = ("unsent_connect", "ConnectError")


@pytest_asyncio.fixture
async def chat(tmp_path, monkeypatch):
    """A fresh partner database and a fake Telegram whose next answers are ``outcomes``."""
    monkeypatch.setattr(settings, "DB_PATH", str(tmp_path / "cache.db"))
    await po.init_partner_db(settings.DB_PATH)
    sent, outcomes = [], []

    async def send(text, *, kind="partner_msg", reply_markup=None):
        sent.append({"kind": kind, "text": text, "markup": reply_markup})
        state, error = outcomes.pop(0) if outcomes else ("acknowledged", None)
        return partner_bot.PartnerSendResult(state == "acknowledged", message_id=len(sent), state=state,
                                             error=error)

    monkeypatch.setattr(partner_bot, "send_partner_result", send)
    monkeypatch.setattr(po, "partner_enabled", lambda: True)
    return sent, outcomes


def _at(**delta):
    return BRIEF_AT + timedelta(**delta)


@pytest.mark.asyncio
async def test_a_brief_that_never_left_is_sent_again_with_when_it_was_written(chat):
    sent, outcomes = chat
    outcomes.append(UNSENT)
    db = settings.DB_PATH
    assert await po.send_daily(db, "brief", DAY, "☀️ Buyer plan · Mon 26 Oct", BRIEF_AT) == {"status": "failed",
                                                                                          "attempts": 1}
    assert not await po._seen(db, "brief", DAY)                  # not "already sent" after a send that never left
    assert (await po.daily_retry_tick(_at(minutes=4)))["brief"] == "retry_later"
    assert (await po.daily_retry_tick(_at(minutes=5)))["brief"] == "sent"
    assert (await po.daily_retry_tick(_at(minutes=10)))["brief"] == "already_sent"
    assert [m["text"] for m in sent] == ["☀️ Buyer plan · Mon 26 Oct",
                                         "☀️ Buyer plan · Mon 26 Oct\n\n⏱ Written at 09:50; it could not be sent then."]
    assert await po.send_daily(db, "brief", DAY, "a second brief", _at(minutes=11)) == {"status": "already_sent"}
    assert len(sent) == 2


@pytest.mark.asyncio
async def test_a_message_that_may_have_arrived_or_was_refused_is_never_sent_again(chat):
    sent, outcomes = chat
    db = settings.DB_PATH
    outcomes += [("ambiguous_timeout", "ReadTimeout"), ("rejected", "telegram_http_400"),
                 ("rejected", "telegram_http_503")]
    assert (await po.send_daily(db, "eod", DAY, "🌙 Wrap", BRIEF_AT))["status"] == "uncertain"
    assert (await po.send_daily(db, "coach", DAY, "📒 Lesson", BRIEF_AT))["status"] == "refused"
    assert (await po.send_daily(db, "zerodha_prompt", DAY, "📒 Review", BRIEF_AT))["status"] == "failed"   # a 5xx
    out = await po.daily_retry_tick(_at(minutes=5))
    assert (out["eod"], out["coach"], out["zerodha_prompt"], out["brief"]) == ("already_sent", "already_sent",
                                                                               "sent", "never_sent")
    assert [m["kind"] for m in sent] == ["eod", "coach", "zerodha_prompt", "zerodha_prompt"]


@pytest.mark.asyncio
async def test_retries_stop_after_four_sends_or_an_hour_after_the_first(chat):
    sent, outcomes = chat
    db = settings.DB_PATH
    outcomes += [UNSENT] * 4
    await po.send_daily(db, "eod", DAY, "🌙 Wrap", BRIEF_AT)
    statuses = [(await po.retry_daily(db, "eod", DAY, _at(minutes=m)))["status"] for m in (5, 15, 35, 40)]
    assert statuses == ["failed", "failed", "undelivered", "already_sent"]
    assert len(sent) == 4                                               # 09:50, 09:55, 10:05, 10:25
    outcomes += [UNSENT, UNSENT]
    await po.send_daily(db, "brief", DAY, "☀️ Brief", BRIEF_AT)
    assert (await po.retry_daily(db, "brief", DAY, _at(minutes=5)))["status"] == "failed"
    assert await po.retry_daily(db, "brief", DAY, _at(minutes=61)) == {"status": "undelivered", "attempts": 2}
    assert len(sent) == 6


@pytest.mark.asyncio
async def test_the_retry_keeps_the_button_and_two_runs_never_send_twice(chat):
    import asyncio
    sent, outcomes = chat
    db = settings.DB_PATH
    button = {"inline_keyboard": [[{"text": "📒 Open full review", "url": "https://kite.zerodha.com/connect/login"}]]}
    outcomes.append(UNSENT)
    await po.send_daily(db, "coach", DAY, "📒 Lesson", BRIEF_AT, reply_markup=button)
    first, second = await asyncio.gather(po.retry_daily(db, "coach", DAY, _at(minutes=5)),
                                         po.retry_daily(db, "coach", DAY, _at(minutes=5)))
    # Whichever run comes second finds the send claimed (in_progress) or already done: one resend either way.
    assert {first["status"], second["status"]} in ({"sent", "in_progress"}, {"sent", "already_sent"})
    assert [m["markup"] for m in sent] == [button, button]


@pytest.mark.asyncio
async def test_a_send_cut_off_by_a_restart_is_never_repeated(chat):
    sent, _ = chat
    db = settings.DB_PATH
    assert await po._claim_daily(db, "brief", DAY, 1, BRIEF_AT, "☀️ Brief", None)       # then the engine stopped
    assert (await po.retry_daily(db, "brief", DAY, _at(seconds=30)))["status"] == "in_progress"
    assert await po.retry_daily(db, "brief", DAY, _at(minutes=5)) == {"status": "uncertain", "attempts": 1}
    assert sent == []


@pytest.mark.asyncio
async def test_the_review_prompt_waits_for_its_retry_instead_of_a_second_send(chat, monkeypatch):
    import partner_broker_sync as zerodha
    sent, outcomes = chat
    monkeypatch.setattr(partner_bot, "partner_enabled", lambda: True)
    monkeypatch.setattr(zerodha, "review_keyboard", lambda label="📒 Review my day": {"inline_keyboard": []})
    outcomes.append(UNSENT)
    assert (await zerodha._send_prompt(IST.localize(datetime(2026, 10, 26, 15, 50))))["status"] == "prompt_failed"
    # The wrap's last step asks again a second later: the retry is due in 5 minutes, not now.
    assert (await zerodha._send_prompt(IST.localize(datetime(2026, 10, 26, 15, 50, 1))))["status"] == "retry_later"
    assert (await po.daily_retry_tick(IST.localize(datetime(2026, 10, 26, 15, 55))))["zerodha_prompt"] == "sent"
    assert (await zerodha._send_prompt(IST.localize(datetime(2026, 10, 26, 15, 56))))["status"] == "already_prompted"
    assert len(sent) == 2 and sent[1]["markup"] == {"inline_keyboard": []}


@pytest.mark.asyncio
async def test_the_tick_is_quiet_without_the_partner_bot_and_one_failure_never_stops_the_others(chat, monkeypatch):
    sent, outcomes = chat
    monkeypatch.setattr(po, "partner_enabled", lambda: False)
    assert await po.daily_retry_tick(_at(minutes=5)) == {}
    monkeypatch.setattr(po, "partner_enabled", lambda: True)
    outcomes.append(UNSENT)
    await po.send_daily(settings.DB_PATH, "eod", DAY, "🌙 Wrap", BRIEF_AT)
    real = po.retry_daily

    async def broken(db_path, kind, day, now):
        if kind == "brief":
            raise RuntimeError("database locked")
        return await real(db_path, kind, day, now)

    monkeypatch.setattr(po, "retry_daily", broken)
    out = await po.daily_retry_tick(_at(minutes=5))
    assert out["brief"] == "error" and out["eod"] == "sent"


def test_the_retry_tick_is_scheduled_every_five_minutes():
    import inspect

    import scheduler_setup
    source = inspect.getsource(scheduler_setup)
    assert ('_run_partner_daily_retry_safe, "cron",\n        minute="*/5", second=40,\n'
            '        id="partner_daily_retry"') in source
    assert po.DAILY_RETRIED == ("brief", "eod", "coach", "zerodha_prompt")
    assert (po.DAILY_ATTEMPTS, po.DAILY_RETRY_MIN, po.DAILY_RETRY_WINDOW) == (4, 5, timedelta(minutes=60))
