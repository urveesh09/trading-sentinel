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
# morning brief
# ---------------------------------------------------------------------------

def format_morning_brief(
    date_str: str,
    regime: str,
    regime_score: Optional[float],
    per_underlying: List[Dict],
) -> str:
    """per_underlying rows (all keys optional except name):
    name, fut, expiry_note, or_high, or_low, atr, long_level, short_level,
    iv, rv, iv_read, pcr, max_pain, support, resistance, error
    """
    score = f" (score {regime_score:.0f})" if regime_score is not None else ""
    lines = [f"Partner brief — {date_str} | Regime: {regime}{score}", ""]
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
        lines.append(
            f"  PCR {_fmt(u.get('pcr'), 2)} | Max pain {_fmt(u.get('max_pain'))}"
            f" | Support {_fmt(u.get('support'))} (PE OI)"
            f" / Resistance {_fmt(u.get('resistance'))} (CE OI)"
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
    option: Optional[Dict] = None,   # tradingsymbol, premium, iv, delta, theta_day, spread_pct, oi
    thin_reasons: Optional[List[str]] = None,
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
    lines.append(ctx)
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

def format_eod(date_str: str, per_underlying: List[Dict]) -> str:
    """per_underlying rows: name, day_high, day_low, close, or_high,
    or_low, signals ([{time, direction, outcome}]), pcr, max_pain,
    tomorrow_note, error"""
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
        else:
            lines.append("  no ORB signals today")
        lines.append(
            f"  closing PCR {_fmt(u.get('pcr'), 2)}"
            f" | max pain {_fmt(u.get('max_pain'))}"
        )
        if u.get("tomorrow_note"):
            lines.append(f"  ⏳ {u['tomorrow_note']}")
        lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)
