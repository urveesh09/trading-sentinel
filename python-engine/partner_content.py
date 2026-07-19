"""
[PARTNER-TIPS 2026-07-18] Partner-facing message formatters (WS5).

Pure string builders: dicts/dataclasses in, plain-text Telegram messages
out (no parse_mode -- see partner_bot). Audience: an INTRADAY OPTION
BUYER on NIFTY/BANKNIFTY/SENSEX, so every message leads with direction,
trigger levels and what premium costs to hold, not with our internals.

Every actionable message carries DISCLAIMER verbatim: the ORB strategy
is paper-validated only and the partner owns their trades.
"""
from __future__ import annotations

from typing import Dict, List, Optional

DISCLAIMER = "System view — paper-validated only. Not advice; you own the trade."


def _fmt(v: Optional[float], nd: int = 0, suffix: str = "") -> str:
    if v is None:
        return "n/a"
    return f"{v:,.{nd}f}{suffix}"


def _fmt_pct(v: Optional[float], nd: int = 1) -> str:
    if v is None:
        return "n/a"
    return f"{v * 100:.{nd}f}%"


# ---------------------------------------------------------------------------
# buyer-friendliness verdict ([PARTNER-ENRICH 2026-07-19])
# ---------------------------------------------------------------------------

def buyer_verdict(
    iv_read: str, regime: str, dte: Optional[int],
) -> str:
    """One synthesized line per index: is TODAY a day to be a premium
    buyer at all? The brief already carries every ingredient; this is
    the conclusion the partner actually trades on. Red flags win over
    everything; green needs cheap premium AND no expiry-day theta."""
    if regime == "REGIME_3_CRISIS":
        return ("🔴 crisis regime — our system takes no new entries; "
                "skip fresh long premium")
    if iv_read == "RICH" and dte is not None and dte <= 1:
        return ("🔴 rich IV into expiry — theta and IV crush both against "
                "the buyer; stay out or scalp tiny")
    parts = []
    if iv_read == "CHEAP":
        parts.append("cheap premium")
    elif iv_read == "RICH":
        parts.append("premiums rich — quick exits only")
    elif iv_read == "FAIR":
        parts.append("fair premium")
    else:
        parts.append("IV read unavailable")
    if dte == 0:
        parts.append("expiry today — intraday scalps only")
    elif dte == 1:
        parts.append("expiry tomorrow — avoid overnight holds")
    if iv_read == "CHEAP" and dte != 0:
        return "🟢 " + " · ".join(parts)
    return "🟡 " + " · ".join(parts)


def _or_quality(ratio: Optional[float]) -> str:
    """OR-width vs ATR: tight ranges break out cleanly, wide ranges chop.
    Empty string in the unremarkable middle band."""
    if ratio is None or ratio <= 0:
        return ""
    if ratio <= 0.6:
        return f" | OR {ratio:.1f}×ATR (tight — clean-breakout profile)"
    if ratio >= 1.2:
        return f" | OR {ratio:.1f}×ATR (wide — chop risk, breakouts fail more)"
    return ""


def _skew_line(ce_iv: Optional[float], pe_iv: Optional[float]) -> str:
    if ce_iv is None or pe_iv is None:
        return ""
    diff = pe_iv - ce_iv
    if diff >= 0.01:
        read = "puts bid — downside fear being paid for"
    elif diff <= -0.01:
        read = "calls bid — upside chase in premiums"
    else:
        read = "balanced"
    return f"  Skew: CE {_fmt_pct(ce_iv)} / PE {_fmt_pct(pe_iv)} — {read}"


# ---------------------------------------------------------------------------
# morning brief
# ---------------------------------------------------------------------------

def format_morning_brief(
    date_str: str,
    regime: str,
    regime_score: Optional[float],
    per_underlying: List[Dict],
    events_note: str = "",
) -> str:
    """per_underlying rows (all keys optional except name):
    name, fut, expiry_note, or_high, or_low, atr, long_level, short_level,
    or_atr_ratio, iv, rv, iv_read, skew_ce, skew_pe, pcr, max_pain,
    support, resistance, dte, error
    """
    score = f" (score {regime_score:.0f})" if regime_score is not None else ""
    lines = [f"Partner brief — {date_str} | Regime: {regime}{score}"]
    if events_note:
        lines.append(f"🗓 {events_note}")
    lines.append("")
    for u in per_underlying:
        name = u["name"]
        if u.get("error"):
            lines.append(f"{name}: data unavailable ({u['error']})")
            lines.append("")
            continue
        head = f"{name}  fut {_fmt(u.get('fut'))}"
        if u.get("expiry_note"):
            head += f" | {u['expiry_note']}"
        lines.append(head)
        if u.get("or_high"):
            lines.append(
                f"  OR {_fmt(u.get('or_low'))}–{_fmt(u.get('or_high'))}"
                f" | ATR {_fmt(u.get('atr'))}"
                f" | Long > {_fmt(u.get('long_level'))}"
                f" | Short < {_fmt(u.get('short_level'))}"
                + _or_quality(u.get("or_atr_ratio"))
            )
        else:
            lines.append("  Opening range not formed yet")
        iv_read = u.get("iv_read", "UNKNOWN")
        iv_line = (
            f"  IV {_fmt_pct(u.get('iv'))} vs RV {_fmt_pct(u.get('rv'))}"
            f" -> {iv_read}"
        )
        if iv_read == "CHEAP":
            iv_line += " (buyer-friendly)"
        elif iv_read == "RICH":
            iv_line += " — premiums fat, prefer quick exits"
        lines.append(iv_line)
        skew = _skew_line(u.get("skew_ce"), u.get("skew_pe"))
        if skew:
            lines.append(skew)
        lines.append(
            f"  PCR {_fmt(u.get('pcr'), 2)} | Max pain {_fmt(u.get('max_pain'))}"
            f" | Support {_fmt(u.get('support'))} (PE OI)"
            f" / Resistance {_fmt(u.get('resistance'))} (CE OI)"
        )
        lines.append(
            f"  Buyer's day: {buyer_verdict(iv_read, regime, u.get('dte'))}"
        )
        lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# signal tip
# ---------------------------------------------------------------------------

def format_signal_tip(
    name: str,
    direction: str,               # "LONG" | "SHORT"
    bar_time: str,                # "HH:MM"
    close: float,
    broken_level: float,
    stop: float,
    target: float,
    regime: str,
    rvol: float,
    expiry_note: str,
    option: Optional[Dict] = None,   # tradingsymbol, premium, iv, delta, theta_day,
                                     # spread_pct, oi, prem_at_target, prem_at_stop,
                                     # rr_premium, lot_size, risk_per_lot, lots_per_lakh,
                                     # sizing_risk_pct
    thin_reasons: Optional[List[str]] = None,
    or_atr_ratio: Optional[float] = None,
    track_line: str = "",
) -> str:
    side = "buy CE" if direction == "LONG" else "buy PE"
    edge = "OR-high" if direction == "LONG" else "OR-low"
    verb = "broke above" if direction == "LONG" else "broke below"
    stop_pts = abs(close - stop)
    tgt_pts = abs(target - close)
    lines = [
        f"🔔 {name} ORB {direction} ({side}) — {bar_time} IST bar",
        f"Fut {close:,.0f} {verb} {edge} trigger {broken_level:,.0f}",
        f"Underlying: stop {stop:,.0f} ({stop_pts:,.0f} pts) | "
        f"target {target:,.0f} ({tgt_pts:,.0f} pts, 1.5R)",
    ]
    if option:
        lines.append(
            f"Option idea (~0.55Δ, ATM/ITM): {option['tradingsymbol']}"
        )
        lines.append(
            f"  premium ~{option['premium']:,.1f}"
            f" | IV {_fmt_pct(option.get('iv'))}"
            f" | Δ{option.get('delta', 0):+.2f}"
            f" | Θ{option.get('theta_day', 0):,.0f}/day"
            f" | spread {_fmt_pct(option.get('spread_pct'))}"
            f" | OI {option.get('oi', 0):,}"
        )
        # [PARTNER-ENRICH 2026-07-19] premium-terms scenarios: what the
        # OPTION does at the underlying stop/target, and the resulting
        # premium RR (the honest one — usually worse than 1.5).
        if option.get("prem_at_target") is not None and option.get("prem_at_stop") is not None:
            paid = option["premium"]
            up = option["prem_at_target"] - paid
            dn = paid - option["prem_at_stop"]
            rr = option.get("rr_premium")
            rr_txt = f" → option RR ≈ {rr:.1f} before theta" if rr else ""
            lines.append(
                f"  at target ≈ {option['prem_at_target']:,.0f} (+{up:,.0f})"
                f" | at stop ≈ {option['prem_at_stop']:,.0f} (−{dn:,.0f})"
                f"{rr_txt}"
            )
        if option.get("risk_per_lot"):
            risk_pct = option.get("sizing_risk_pct", 0.02)
            lots = option.get("lots_per_lakh")
            sizing = (
                f"  1 lot ({option.get('lot_size', 0)} qty)"
                f" ≈ ₹{option['risk_per_lot']:,.0f} risk to stop"
            )
            if lots is not None:
                if lots >= 1:
                    sizing += (
                        f" → ~{lots} lot{'s' if lots > 1 else ''} per ₹1L"
                        f" at {risk_pct * 100:.0f}% risk"
                    )
                else:
                    sizing += (
                        f" — ⚠ even 1 lot risks > {risk_pct * 100:.0f}%"
                        " of ₹1L; size accordingly"
                    )
            lines.append(sizing)
        if thin_reasons:
            lines.append(
                "  ⚠ thin market at this strike ("
                + "; ".join(thin_reasons)
                + ") — premium/spread unreliable, size down or skip"
            )
    else:
        lines.append(
            "⚠ chain thin at ATM — no healthy strike to suggest; "
            "if you trade the view, size down"
        )
    ctx = f"Regime {regime} | RVOL {rvol:.1f}"
    if expiry_note:
        ctx += f" | {expiry_note}"
    ctx += _or_quality(or_atr_ratio)
    lines.append(ctx)
    if track_line:
        lines.append(track_line)
    lines.append(DISCLAIMER)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# intraday events
# ---------------------------------------------------------------------------

def format_event(kind: str, name: str, detail: str) -> str:
    icons = {
        "pcr_shift": "⚖️",
        "iv_move": "💨",
        "oi_walls": "🧱",
        "wall_flow": "🧱",
        "pin": "🧲",
        "regime_change": "🌡️",
        "halt": "⛔",
        "mom_cue": "📈",
    }
    icon = icons.get(kind, "ℹ️")
    prefix = f"{icon} {name}: " if name else f"{icon} "
    return f"{prefix}{detail}"


# ---------------------------------------------------------------------------
# EOD wrap
# ---------------------------------------------------------------------------

def format_eod(
    date_str: str, per_underlying: List[Dict], record_line: str = "",
) -> str:
    """per_underlying rows: name, day_high, day_low, close, or_high,
    or_low, signals ([{time, direction, outcome, option_line}]), pcr,
    max_pain, tomorrow_note, error"""
    lines = [f"Partner EOD wrap — {date_str}", ""]
    for u in per_underlying:
        name = u["name"]
        if u.get("error"):
            lines.append(f"{name}: data unavailable ({u['error']})")
            lines.append("")
            continue
        lines.append(
            f"{name}  close {_fmt(u.get('close'))}"
            f" | day {_fmt(u.get('day_low'))}–{_fmt(u.get('day_high'))}"
            f" | OR was {_fmt(u.get('or_low'))}–{_fmt(u.get('or_high'))}"
        )
        sigs = u.get("signals") or []
        if sigs:
            for s in sigs:
                lines.append(
                    f"  signal {s['time']} {s['direction']} -> {s['outcome']}"
                )
                # [PARTNER-ENRICH 2026-07-19] what the SUGGESTED OPTION's
                # premium actually did — the partner's real P&L axis.
                if s.get("option_line"):
                    lines.append(f"    {s['option_line']}")
        else:
            lines.append("  no ORB signals today")
        lines.append(
            f"  closing PCR {_fmt(u.get('pcr'), 2)}"
            f" | max pain {_fmt(u.get('max_pain'))}"
        )
        if u.get("tomorrow_note"):
            lines.append(f"  ⏳ {u['tomorrow_note']}")
        lines.append("")
    if record_line:
        lines.append(record_line)
        lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)
