"""
[PARTNER-TIPS-TESTS 2026-07-18] Message formatters (plan WS5): the
disclaimer is present on every actionable message, output stays inside
Telegram's 4096-char cap, missing data degrades to "n/a" instead of
crashing, and the thin-chain variant warns instead of suggesting.
"""
import partner_content as pc


FULL_ROW = {
    "name": "NIFTY", "fut": 25140.0, "expiry_note": "3d to expiry",
    "or_high": 25180.0, "or_low": 25090.0, "atr": 38.0,
    "long_level": 25189.5, "short_level": 25080.5,
    "iv": 0.112, "rv": 0.139, "iv_read": "CHEAP",
    "pcr": 0.94, "max_pain": 25100.0, "support": 25000.0, "resistance": 25300.0,
}


def test_morning_brief_full_row():
    msg = pc.format_morning_brief(
        "2026-07-20 09:50 IST", "REGIME_1_NORMAL", 34.0, [FULL_ROW],
    )
    assert "Partner brief — 2026-07-20 09:50 IST" in msg
    assert "Regime: REGIME_1_NORMAL (score 34)" in msg
    assert "OR 25,090–25,180" in msg
    assert "Long > 25,190" in msg and "Short < 25,080" in msg
    assert "IV 11.2% vs RV 13.9% -> CHEAP (buyer-friendly)" in msg
    assert "PCR 0.94" in msg and "Max pain 25,100" in msg
    assert "Support 25,000 (PE OI) / Resistance 25,300 (CE OI)" in msg
    assert pc.DISCLAIMER in msg
    assert len(msg) < 4096


def test_morning_brief_degrades_missing_data():
    rows = [
        {"name": "SENSEX", "error": "instruments not ready"},
        {"name": "BANKNIFTY", "fut": 57420.0, "iv_read": "UNKNOWN"},
    ]
    msg = pc.format_morning_brief("2026-07-20 09:50 IST", "UNKNOWN", None, rows)
    assert "SENSEX: data unavailable (instruments not ready)" in msg
    assert "Opening range not formed yet" in msg
    assert "IV n/a vs RV n/a" in msg
    assert "(score" not in msg


def test_signal_tip_with_option():
    msg = pc.format_signal_tip(
        name="BANKNIFTY", direction="LONG", bar_time="11:35",
        close=57592.0, broken_level=57540.0, stop=57411.0, target=57864.0,
        regime="REGIME_1_NORMAL", rvol=1.6, expiry_note="8d to expiry",
        option={
            "tradingsymbol": "BANKNIFTY25JUL57500CE", "premium": 412.0,
            "iv": 0.131, "delta": 0.56, "theta_day": -31.0,
            "spread_pct": 0.004, "oi": 190000,
        },
    )
    assert "BANKNIFTY ORB LONG (buy CE) — 11:35 IST bar" in msg
    assert "broke above OR-high trigger 57,540" in msg
    assert "stop 57,411 (181 pts)" in msg
    assert "target 57,864 (272 pts, 1.5R)" in msg
    assert "BANKNIFTY25JUL57500CE" in msg
    assert "premium ~412.0" in msg and "IV 13.1%" in msg
    assert "Δ+0.56" in msg and "Θ-31/day" in msg
    assert "OI 190,000" in msg
    assert "RVOL 1.6" in msg and "8d to expiry" in msg
    assert pc.DISCLAIMER in msg


def test_signal_tip_short_direction_wording():
    msg = pc.format_signal_tip(
        name="NIFTY", direction="SHORT", bar_time="10:05",
        close=24880.0, broken_level=24905.0, stop=24960.0, target=24760.0,
        regime="REGIME_2_ELEVATED", rvol=2.1, expiry_note="",
        option=None,
    )
    assert "ORB SHORT (buy PE)" in msg
    assert "broke below OR-low trigger 24,905" in msg
    assert "chain thin at ATM" in msg     # no option -> explicit warning
    assert pc.DISCLAIMER in msg


def test_signal_tip_thin_chain_variant():
    msg = pc.format_signal_tip(
        name="SENSEX", direction="LONG", bar_time="11:00",
        close=82650.0, broken_level=82600.0, stop=82500.0, target=82875.0,
        regime="REGIME_1_NORMAL", rvol=1.4, expiry_note="1d",
        option={
            "tradingsymbol": "SENSEX25JUL82600CE", "premium": 300.0,
            "iv": 0.12, "delta": 0.55, "theta_day": -40.0,
            "spread_pct": 0.03, "oi": 200,
        },
        thin_reasons=["OI 200 < 5000", "spread 3.0% > 1.5%"],
    )
    assert "thin market at this strike" in msg
    assert "OI 200 < 5000" in msg
    assert "size down or skip" in msg


def test_event_formatting():
    msg = pc.format_event("pcr_shift", "NIFTY", "PCR 0.94 -> 1.18 since open")
    assert msg == "⚖️ NIFTY: PCR 0.94 -> 1.18 since open"
    # no-name events (regime/halt) don't dangle a colon
    msg2 = pc.format_event("regime_change", "", "Market regime changed")
    assert "Market regime changed" in msg2 and ": " not in msg2.split("changed")[0]


def test_eod_wrap():
    rows = [
        {
            "name": "NIFTY", "close": 25210.0, "day_low": 25050.0,
            "day_high": 25260.0, "or_low": 25090.0, "or_high": 25180.0,
            "signals": [
                {"time": "09:55", "direction": "LONG", "outcome": "target 25,300 hit"},
            ],
            "pcr": 1.05, "max_pain": 25200.0,
            "tomorrow_note": "NIFTY expiry TOMORROW — theta burns fast",
        },
        {"name": "SENSEX", "error": "no bars"},
    ]
    msg = pc.format_eod("2026-07-20", rows)
    assert "Partner EOD wrap — 2026-07-20" in msg
    assert "signal 09:55 LONG -> target 25,300 hit" in msg
    assert "closing PCR 1.05" in msg
    assert "expiry TOMORROW" in msg
    assert "SENSEX: data unavailable (no bars)" in msg
    assert pc.DISCLAIMER in msg


def test_eod_no_signals_line():
    msg = pc.format_eod("2026-07-20", [{
        "name": "NIFTY", "close": 25000.0, "day_low": 24900.0,
        "day_high": 25100.0, "signals": [],
    }])
    assert "no ORB signals today" in msg
