"""[SN477] Paper books pin the exact contract they hold in the research collector's selected-leg store."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

import fno_n11
import research_pins
import research_quote_collector as rqc
import sn_gold
from config import settings
from fno_models import Contract
from research_leg_subscriptions import ResearchLegSubscriptionStore
from tests.test_sn_gold import _bars, _paper, _row, at, db, run, sig, snapshot  # noqa: F401  (db is a fixture)


@pytest.fixture
def archive(tmp_path, monkeypatch):
    root = tmp_path / "research"
    root.mkdir()
    monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_PATH", str(root))
    monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_ENABLED", True)
    monkeypatch.setattr(settings, "RESEARCH_PIN_PAPER_LEGS", True)
    return root


def _active(root, when):
    legs, short = ResearchLegSubscriptionStore(str(root)).active(underlying="NIFTY", now=when, capacity=50)
    return [(leg.decision_id, leg.contract.token) for leg in legs], short


def test_gold_entry_pins_its_exact_contract_until_1520(db, archive):
    _bars(db.path)
    run(_paper(db.path))
    pid = run(sn_gold.on_paper_signal(db.path, sig(), snapshot(), at("10:05")))
    assert pid is not None
    legs, short = _active(archive, at("10:06"))
    assert legs == [(f"sn_gold:{pid}", 112)] and short == []           # the 1-ITM 23950 CE Gold bought, not N11's 24000
    assert _active(archive, at("15:19"))[0] == legs
    assert _active(archive, at("15:21"))[0] == []                        # released after the day's flat times


def test_the_pin_survives_a_restart(db, archive):
    _bars(db.path)
    run(_paper(db.path))
    run(sn_gold.on_paper_signal(db.path, sig(), snapshot(), at("10:05")))
    first = _active(archive, at("11:00"))[0]
    assert first and _active(archive, at("11:00"))[0] == first          # a fresh store object reads the same durable rows


def test_a_broken_store_never_blocks_the_entry(db, archive, monkeypatch):
    def boom(self, **kw):
        raise RuntimeError("disk")
    monkeypatch.setattr(ResearchLegSubscriptionStore, "register", boom)
    _bars(db.path)
    run(_paper(db.path))
    assert run(sn_gold.on_paper_signal(db.path, sig(), snapshot(), at("10:05"))) is not None
    assert len(run(_row(db.path))) == 1


def test_switched_off_registers_nothing(db, archive, monkeypatch):
    monkeypatch.setattr(settings, "RESEARCH_PIN_PAPER_LEGS", False)
    _bars(db.path)
    run(_paper(db.path))
    run(sn_gold.on_paper_signal(db.path, sig(), snapshot(), at("10:05")))
    assert _active(archive, at("10:06"))[0] == []


def test_no_archive_folder_no_pin(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "RESEARCH_ARCHIVE_PATH", str(tmp_path / "absent"))
    monkeypatch.setattr(settings, "RESEARCH_PIN_PAPER_LEGS", True)
    c = Contract(token=777, tradingsymbol="NIFTY26N1722600PE", name="NIFTY", expiry=date(2026, 11, 17), strike=22600.0,
                 instrument_type="PE", lot_size=65, tick_size=0.05)
    assert run(research_pins.pin([c], "z", at("10:05"))) == {"state": "no_archive"} and not (tmp_path / "absent").exists()


def test_pin_helper_rejects_nothing_silently_and_maps_the_exchange(archive):
    c = Contract(token=777, tradingsymbol="NIFTY26N1722600PE", name="NIFTY", expiry=date(2026, 11, 17), strike=22600.0,
                 instrument_type="PE", lot_size=65, tick_size=0.05)
    assert run(research_pins.pin([c], "n11_paper:2026-11-13 10:00:00", at("10:05"))) == {"state": "registered", "legs": 1}
    assert run(research_pins.pin([], "x", at("10:05")))["state"] == "nothing"
    bad = Contract(token=0, tradingsymbol="", name="NIFTY", expiry=date(2026, 11, 17), strike=1.0, instrument_type="PE", lot_size=65, tick_size=0.05)
    assert run(research_pins.pin([bad], "y", at("10:05")))["state"] == "unavailable"


def test_the_collector_keeps_a_pinned_contract_the_rolling_window_dropped(archive):
    """SN464's case: a deep-ITM put eight strikes from the future at the exit minute is outside the +-5 window."""
    held = Contract(token=777, tradingsymbol="NIFTY26N1722600PE", name="NIFTY", expiry=date(2026, 11, 17), strike=22600.0,
                    instrument_type="PE", lot_size=65, tick_size=0.05)
    run(research_pins.pin([held], "sn_gold:9", at("10:05")))
    window = [(Contract(token=1000 + k, tradingsymbol=f"W{k}", name="NIFTY", expiry=date(2026, 11, 17), strike=22200.0 + 50 * k,
                        instrument_type="PE", lot_size=65, tick_size=0.05), "atm_window_expiry=2026-11-17") for k in range(-5, 6)]
    assert 777 not in {c.token for c, _r in window}
    legs, _short = ResearchLegSubscriptionStore(str(archive)).active(underlying="NIFTY", now=at("14:30"), capacity=50)
    merged = rqc._with_active_legs(window, legs)
    assert 777 in {c.token for c, _r in merged} and any("active_selected_leg decision=sn_gold:9" in r for _c, r in merged)


def test_n11_paper_record_pins_its_lot_contract():
    src = Path(fno_n11.__file__).read_text(encoding="utf-8")
    assert 'research_pins.pin([quote.contract], f"n11_paper:{sig.bar_ts}", now)' in src


def test_pins_never_reach_an_order_path():
    src = Path(research_pins.__file__).read_text(encoding="utf-8")
    for word in ("place_order", "fno_live", "executor", "kite.place", "order_execution"):
        assert word not in src, word
