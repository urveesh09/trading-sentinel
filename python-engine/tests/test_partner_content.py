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


# ---------------------------------------------------------------------------
# [PARTNER-ENRICH 2026-07-19] buyer verdict (T1b)
# ---------------------------------------------------------------------------

def test_verdict_crisis_is_red_regardless():
    v = pc.buyer_verdict("CHEAP", "REGIME_3_CRISIS", 5)
    assert v.startswith("🔴") and "no new entries" in v


def test_verdict_rich_into_expiry_is_red():
    v = pc.buyer_verdict("RICH", "REGIME_1_NORMAL", 1)
    assert v.startswith("🔴") and "crush" in v


def test_verdict_cheap_is_green_unless_expiry_today():
    assert pc.buyer_verdict("CHEAP", "REGIME_1_NORMAL", 3).startswith("🟢")
    assert pc.buyer_verdict("CHEAP", "REGIME_1_NORMAL", 0).startswith("🟡")


def test_verdict_fair_is_amber_with_parts():
    v = pc.buyer_verdict("FAIR", "REGIME_2_ELEVATED", 1)
    assert v.startswith("🟡")
    assert "fair premium" in v and "expiry tomorrow" in v


def test_brief_carries_verdict_and_skew():
    row = dict(FULL_ROW)
    row.update(dte=3, skew_ce=0.109, skew_pe=0.121, or_atr_ratio=0.4)
    msg = pc.format_morning_brief(
        "2026-07-20 09:50 IST", "REGIME_1_NORMAL", 34.0, [row],
        events_note="RBI MPC decision TODAY — IV is bid into the event",
    )
    assert "Buyer's day: 🟢 cheap premium" in msg
    assert "Skew: CE 10.9% / PE 12.1% — puts bid" in msg
    assert "OR 0.4×ATR (tight" in msg
    assert "🗓 RBI MPC decision TODAY" in msg
    assert len(msg) < 4096


# ---------------------------------------------------------------------------
# [PARTNER-ENRICH 2026-07-19] tip: premium RR + sizing + track (T1a/T1d/T1c)
# ---------------------------------------------------------------------------

RICH_OPTION = {
    "tradingsymbol": "NIFTY25JUL25000CE", "premium": 112.0,
    "iv": 0.12, "delta": 0.55, "theta_day": -9.0,
    "spread_pct": 0.004, "oi": 150000,
    "prem_at_target": 152.0, "prem_at_stop": 83.0, "rr_premium": 1.4,
    "lot_size": 75, "risk_per_lot": 2175.0, "lots_per_lakh": 0,
    "sizing_risk_pct": 0.02,
}


def test_tip_premium_scenarios_and_sizing_zero_lots():
    msg = pc.format_signal_tip(
        name="NIFTY", direction="LONG", bar_time="09:55",
        close=25100.0, broken_level=25017.5, stop=25055.0, target=25167.5,
        regime="REGIME_1_NORMAL", rvol=2.1, expiry_note="3d to expiry",
        option=RICH_OPTION, or_atr_ratio=0.5,
        track_line="Record (NIFTY LONG, 30d): 9/20 target-first, avg +0.2R on the underlying",
    )
    assert "at target ≈ 152 (+40) | at stop ≈ 83 (−29) → option RR ≈ 1.4 before theta" in msg
    assert "1 lot (75 qty) ≈ ₹2,175 risk to stop" in msg
    assert "⚠ even 1 lot risks > 2% of ₹1L" in msg
    assert "OR 0.5×ATR (tight" in msg
    assert "Record (NIFTY LONG, 30d): 9/20 target-first" in msg
    assert pc.DISCLAIMER in msg
    assert len(msg) < 4096


def test_tip_sizing_with_lots():
    option = dict(RICH_OPTION, risk_per_lot=950.0, lots_per_lakh=2)
    msg = pc.format_signal_tip(
        name="NIFTY", direction="SHORT", bar_time="10:15",
        close=25000.0, broken_level=25080.0, stop=25055.0, target=24917.5,
        regime="REGIME_1_NORMAL", rvol=1.8, expiry_note="",
        option=option,
    )
    assert "~2 lots per ₹1L at 2% risk" in msg


def test_tip_without_scenarios_has_no_scenario_lines():
    option = {
        "tradingsymbol": "NIFTY25JUL25000CE", "premium": 112.0,
        "iv": 0.12, "delta": 0.55, "theta_day": -9.0,
        "spread_pct": 0.004, "oi": 150000,
    }
    msg = pc.format_signal_tip(
        name="NIFTY", direction="LONG", bar_time="09:55",
        close=25100.0, broken_level=25017.5, stop=25055.0, target=25167.5,
        regime="REGIME_1_NORMAL", rvol=2.1, expiry_note="",
        option=option,
    )
    assert "at target ≈" not in msg
    assert "risk to stop" not in msg
    assert "Record (" not in msg


# ---------------------------------------------------------------------------
# [PARTNER-ENRICH 2026-07-19] EOD: option line + record line (T2b/T1c)
# ---------------------------------------------------------------------------

def test_eod_option_line_and_record():
    rows = [{
        "name": "NIFTY", "close": 25150.0, "day_low": 25010.0,
        "day_high": 25180.0, "or_low": 24990.0, "or_high": 25010.0,
        "signals": [{
            "time": "09:55", "direction": "LONG",
            "outcome": "target 25,168 hit",
            "option_line": "option NIFTY25JUL25000CE: paid ~112.0, peak 156.0 (+39%), last 140.0 (+25%)",
        }],
        "pcr": 1.02, "max_pain": 25000.0,
    }]
    msg = pc.format_eod(
        "2026-07-20", rows,
        record_line="📊 Rolling 30d ORB record: 9/20 target-first, avg +0.2R on the underlying",
    )
    assert "signal 09:55 LONG -> target 25,168 hit" in msg
    assert "option NIFTY25JUL25000CE: paid ~112.0, peak 156.0 (+39%)" in msg
    assert "📊 Rolling 30d ORB record" in msg
    assert pc.DISCLAIMER in msg


def test_event_icons_for_new_kinds():
    assert pc.format_event("wall_flow", "NIFTY", "x").startswith("🧱")
    assert pc.format_event("pin", "NIFTY", "x").startswith("🧲")
