"""[O24i] fno_risk_alert: the owner hears when the F&O paper book's size tier or entry halts change (the rules
themselves are unchanged)."""
from datetime import datetime
from types import SimpleNamespace

import pytest
import pytz

import fno_adaptive_risk
import fno_risk_alert as alert
import fno_shared_risk
from config import settings

IST = pytz.timezone("Asia/Kolkata")
NOW = IST.localize(datetime(2026, 10, 27, 10, 0))


def test_the_messages_say_what_changed_and_how_far_the_halt_is():
    first = alert.risk_text(None, {"tier": "drawdown_cut2", "halts": []}, equity=226798.0, allocation=250000.0,
                            drawdown_pct=0.0928)
    assert first == ("F&O paper risk: quarter size (0.25x), 9.3% under its peak; no entry halt. Paper equity "
                     "₹226,798: ₹14,298 above the 15% halt line (₹212,500). You will hear when this changes.")
    halted = alert.risk_text({"tier": "drawdown_cut2", "halts": []},
                             {"tier": "drawdown_cut2", "halts": ["drawdown_halt"]}, equity=212300.0,
                             allocation=250000.0, drawdown_pct=0.1508)
    assert halted.startswith("⚠️ F&O paper: entries halted by the 15% drawdown halt. Paper equity ₹212,300: under "
                             "the 15% halt line (₹212,500).")
    assert halted.endswith("Keeping, re-anchoring or ending the halt is your decision.")
    cleared = alert.risk_text({"tier": "drawdown_cut1", "halts": ["daily_loss_halt"]},
                              {"tier": "drawdown_cut1", "halts": []}, equity=230000.0, allocation=250000.0,
                              drawdown_pct=0.08)
    assert cleared.startswith("ℹ️ F&O paper: the daily loss brake cleared: entries open again.")
    sized = alert.risk_text({"tier": "drawdown_cut1", "halts": []}, {"tier": "drawdown_cut2", "halts": []},
                            equity=220000.0, allocation=250000.0, drawdown_pct=0.12)
    assert sized.startswith("⚠️ F&O paper: size now quarter size (0.25x), 12.0% under its peak.")


@pytest.fixture
def book(monkeypatch, tmp_path):
    """The paper book's risk as the shared policy and the adaptive stance report it (set by the test)."""
    state = {"halts": (), "equity": 226798.0, "tier": "drawdown_cut2", "drawdown": 0.0928, "two_strike": False,
             "available": True}

    async def policy(db_path, *, source, pool_rs, today_ist, policy):
        assert source == "FNO_PAPER" and pool_rs == float(settings.FNO_PAPER_BANKROLL)
        return SimpleNamespace(active_halts=state["halts"],
                               view=SimpleNamespace(available=state["available"], equity_rs=state["equity"]))

    async def closes(db_path, source):
        return []

    def stance(closes, *, allocation, now, policy):
        return SimpleNamespace(reason=state["tier"], drawdown_pct=state["drawdown"],
                               single_leg_halted_today=state["two_strike"])

    monkeypatch.setattr(fno_shared_risk, "shared_fno_entry_policy", policy)
    monkeypatch.setattr(fno_adaptive_risk, "read_book_closes", closes)
    monkeypatch.setattr(fno_adaptive_risk, "risk_stance", stance)
    sent, answers = [], []

    async def notify(text, *, event):
        sent.append((text, event))
        return answers.pop(0) if answers else True

    return state, sent, answers, notify, str(tmp_path / "cache.db")


@pytest.mark.asyncio
async def test_each_change_is_told_once_and_a_failed_send_is_tried_again(book):
    state, sent, answers, notify, db = book
    first = await alert.check_paper(db, NOW, notify=notify)
    assert first.startswith("F&O paper risk: quarter size (0.25x)") and sent[-1][1] == "fno_paper_risk_state"
    assert await alert.check_paper(db, NOW, notify=notify) is None             # nothing changed: nothing said
    state["halts"] = ("drawdown_halt equity=212300", "daily_loss_halt pnl=-7600")
    state["equity"] = 212300.0
    answers.append(False)                                                       # Telegram did not take it
    assert await alert.check_paper(db, NOW, notify=notify) is None
    again = await alert.check_paper(db, NOW, notify=notify)                    # tried again on the next tick
    assert again.startswith("⚠️ F&O paper: entries halted by the 15% drawdown halt, the daily loss brake.")
    assert len(sent) == 3
    state["two_strike"] = True
    assert "two losses today" in await alert.check_paper(db, NOW, notify=notify)
    state["available"] = False                                                  # the ledger could not be read
    state["halts"] = ()
    assert await alert.check_paper(db, NOW, notify=notify) is None and len(sent) == 4


@pytest.mark.asyncio
async def test_a_calm_book_is_only_remembered_and_a_failure_never_raises(book, monkeypatch):
    state, sent, _answers, notify, db = book
    state.update(tier="base", drawdown=0.0)
    assert await alert.check_paper(db, NOW, notify=notify) is None and sent == []
    state["tier"] = "drawdown_cut1"
    assert (await alert.check_paper(db, NOW, notify=notify)).startswith("⚠️ F&O paper: size now half size (0.5x)")

    async def broken(*args, **kwargs):
        raise RuntimeError("ledger locked")

    monkeypatch.setattr(fno_shared_risk, "shared_fno_entry_policy", broken)
    assert await alert.check_paper(db, NOW, notify=notify) is None             # the F&O tick is never disturbed
