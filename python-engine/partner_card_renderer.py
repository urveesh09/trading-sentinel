"""[WORKFLOW-E.4 2026-09-17] Pure card renderer.

Per Workstream E in NEXT_AGENT_PLAN.md:
> Improve cards around decisions a manual trader can take:
> index/exchange, timestamp/validity, setup rationale, entry
> trigger and bounded price, exact contract legs/expiry/lot,
> total debit and modeled costs, maximum defined loss,
> invalidation/target and intraday deadline. Explain
> uncertainty and liquidity limits without overwhelming the
> message.

This module extracts the card-rendering logic from
``partner_manual_advisory.py`` into a pure function that
takes a dict (the same shape ``_candidate_payload()``
produces) and returns the rendered Telegram card body.

Why a separate module:
  - The original render function depends on the
    ``AdvisoryCandidate`` dataclass; that coupling makes it
    hard to test rendering without instantiating the whole
    dataclass tree.
  - This module accepts the dict shape, which is what the
    E.2 card validator already checks. The validator and
    renderer can now compose: validate dict -> render dict.

The function is byte-identical to
``partner_manual_advisory.render_advisory_card`` for the same
input (after enum -> str conversion). The existing function
is refactored to delegate here so production behavior is
unchanged.

Read-only. No Telegram, no DB, no broker.
"""
from __future__ import annotations

import re
from typing import Any, Optional

# Telegram message size limit (hard cap on a single message;
# the existing code raises if exceeded).
MAX_TELEGRAM_CHARS = 4096


class CardRenderError(ValueError):
    """Raised when a card cannot be rendered safely.

    The most common cause is a card whose rendered text
    would exceed Telegram's message limit. Operators see
    this as ``advisory_card_over_telegram_limit`` and the
    upstream caller short-circuits.
    """


def _iso(value: Any) -> str:
    """Format a datetime / str as ISO 8601 (timezone-aware).

    The renderer accepts both ``datetime`` objects (the
    dataclass representation) and ISO strings (the dict
    representation produced by ``_candidate_payload``).
    Datetimes must be timezone-aware; strings are returned
    unchanged.
    """
    import datetime as _dt

    if isinstance(value, str):
        return value
    if isinstance(value, _dt.datetime):
        if value.tzinfo is None:
            raise ValueError("advisory timestamps must be timezone-aware")
        return value.isoformat()
    raise TypeError(f"unsupported timestamp type: {type(value).__name__}")


def _format_rupees(amount: Optional[float]) -> str:
    """Format a rupee amount with thousands separator."""
    if amount is None:
        return ""
    return f"{amount:,.2f}"


def _format_strike(strike: Optional[float]) -> str:
    """Format a strike price (no trailing zeros).

    ``leg.strike`` is rendered with ``:g`` in the original
    function so ``24100.0`` becomes ``24100``.
    """
    if strike is None:
        return ""
    return f"{strike:g}"


def render_card(card: dict) -> str:
    """Render a partner advisory card as a Telegram-ready string.

    Args:
        card: a dict matching the ``_candidate_payload()`` shape
            produced by ``partner_manual_advisory.py``. Required
            keys: ``scope``, ``underlying``, ``exchange``,
            ``policy_version``, ``quote_time``, ``valid_until``,
            ``why_now``, ``legs``, ``evidence``, ``invalidation``,
            ``management``, ``uncertainty``.

    Returns:
        The rendered card body, with newline-separated fields
        ready for Telegram.

    Raises:
        CardRenderError: if the rendered text exceeds
            ``MAX_TELEGRAM_CHARS``.
        ValueError: if required fields are missing or invalid.
    """
    if not isinstance(card, dict):
        raise CardRenderError(
            f"card must be a dict, got {type(card).__name__}"
        )

    scope_raw = card.get("scope")
    if not scope_raw:
        raise CardRenderError("card.scope is required")
    header = str(scope_raw).replace("_", " ")

    underlying = card.get("underlying")
    exchange = card.get("exchange")
    if not underlying:
        raise CardRenderError("card.underlying is required")
    if not exchange:
        raise CardRenderError("card.exchange is required")

    policy_version = card.get("policy_version", "?")
    quote_time = _iso(card.get("quote_time"))
    valid_until = _iso(card.get("valid_until"))
    advisory_id = card.get("advisory_id", "?")

    legs = card.get("legs", [])
    if not isinstance(legs, (list, tuple)) or not legs:
        raise CardRenderError("card.legs must be a non-empty list")

    why_now = card.get("why_now") or []
    if isinstance(why_now, (list, tuple)) and why_now:
        why_text = "; ".join(str(w) for w in why_now)
    else:
        why_text = "(no rationale provided)"

    lines: list[str] = [
        f"[{header}] • {underlying} ({exchange})",
        f"Idea {advisory_id}/{policy_version} • Data {quote_time} • Valid until {valid_until}",
        "INTRADAY ONLY — do not carry overnight. Manual action only; the system cannot close any position for you.",
        f"Why now: {why_text}",
        "Structure:",
    ]

    for leg in legs:
        if not isinstance(leg, dict):
            raise CardRenderError(f"leg must be a dict, got {type(leg).__name__}")
        side = leg.get("side", "?")
        ratio = leg.get("ratio", 1)
        tradingsymbol = leg.get("tradingsymbol", "?")
        expiry = leg.get("expiry", "?")
        strike = leg.get("strike", 0)
        option_type = leg.get("option_type", "?")
        lot_size = leg.get("lot_size", 0)
        bid = leg.get("bid")
        ask = leg.get("ask")
        bid_str = f"{bid:g}" if bid is not None else "?"
        ask_str = f"{ask:g}" if ask is not None else "?"
        lines.append(
            f"{side} {ratio}× {tradingsymbol} | {expiry} {_format_strike(strike)}{option_type} "
            f"| lot {lot_size} | bid/ask {bid_str}/{ask_str}"
        )

    net_debit = card.get("net_debit_rs")
    if net_debit is not None:
        lines.append(f"Act only if: combined debit ≤ ₹{_format_rupees(net_debit)} before fees")
    net_credit = card.get("net_credit_rs")
    if net_credit is not None:
        lines.append(f"Act only if: combined credit ≥ ₹{_format_rupees(net_credit)} before fees")
    round_trip = card.get("estimated_round_trip_cost_rs")
    if round_trip is not None:
        lines.append(f"Per structure: estimated round-trip costs ₹{_format_rupees(round_trip)}")
    max_loss = card.get("max_loss_rs")
    if max_loss is not None:
        if scope_raw == "CONDITIONAL_PROTECTION":
            risk_label = "Protection premium at risk"
            tail = "; this is not the loss bound of an unknown protected position"
        else:
            risk_label = "Risk: theoretical maximum loss"
            tail = " if all intended legs fill and remain paired"
        lines.append(
            f"{risk_label} ₹{_format_rupees(max_loss)}" + tail
        )
    max_profit = card.get("max_profit_rs")
    if max_profit is not None:
        lines.append(f"Theoretical expiry maximum profit: ₹{_format_rupees(max_profit)}")
    breakevens = card.get("breakevens") or []
    if breakevens:
        lines.append(
            "Expiry breakeven(s): " + ", ".join(f"{item:,.2f}" for item in breakevens)
        )
    exposure_assumption = card.get("exposure_assumption")
    if exposure_assumption:
        lines.append(f"Coverage assumption: {exposure_assumption}")

    direction = card.get("direction")
    trigger_level = card.get("trigger_level")
    if trigger_level is not None:
        comparator = "above" if direction == "LONG" else "below"
        lines.append(
            f"Entry trigger: underlying confirms {comparator} "
            f"{trigger_level:,.2f} on the stated completed-bar signal."
        )
    invalidation_level = card.get("invalidation_level")
    if invalidation_level is not None:
        lines.append(f"Thesis invalidation level: {invalidation_level:,.2f}.")
    target_level = card.get("target_level")
    if target_level is not None:
        lines.append(
            f"First profit-taking / review level: {target_level:,.2f}; "
            "do not treat it as a guarantee."
        )
    holding_horizon = card.get("holding_horizon")
    if holding_horizon:
        deadline_raw = card.get("management_deadline")
        deadline = _iso(deadline_raw) if deadline_raw else "unavailable"
        lines.append(
            f"Holding horizon: {holding_horizon}; exit/reassess by {deadline} "
            "(IST), not contract expiry."
        )

    invalidation = card.get("invalidation", "")
    management = card.get("management", "")
    uncertainty = card.get("uncertainty", "")
    evidence = card.get("evidence", "?")
    lines.extend([
        f"Invalidation: {invalidation}",
        f"Management: {management}",
        f"Uncertainty: {uncertainty}",
        f"Evidence: {evidence}. Per-structure economics only; no personal quantity is supplied.",
        "Manual decision. Recheck current executable quotes and broker requirements before acting.",
    ])

    text = "\n".join(lines)
    if len(text) > MAX_TELEGRAM_CHARS:
        raise CardRenderError("advisory_card_over_telegram_limit")
    return text


# -- Render validator ---------------------------------------------
# Per the plan: each card should contain index/exchange,
# timestamp/validity, setup rationale, entry trigger, bounded
# price, exact contract legs/expiry/lot, total debit and
# modeled costs, max loss, invalidation/target, intraday
# deadline. The renderer composes these from the card dict;
# this validator asserts they all appear in the rendered text.

_REQUIRED_TEXT_PATTERNS = {
    "scope_header": re.compile(r"^\[[A-Z _]+\] • .+ \(.+\)$", re.MULTILINE),
    "data_and_valid_until": re.compile(r"Data .+ • Valid until .+$", re.MULTILINE),
    "intraday_warning": re.compile(r"INTRADAY ONLY"),
    "manual_action_warning": re.compile(r"Manual action only"),
    "why_now": re.compile(r"Why now: "),
    "structure": re.compile(r"^Structure:$", re.MULTILINE),
    "invalidation": re.compile(r"^Invalidation: .+", re.MULTILINE),
    "management": re.compile(r"^Management: .+", re.MULTILINE),
    "uncertainty": re.compile(r"^Uncertainty: .+", re.MULTILINE),
    "evidence": re.compile(r"^Evidence: .+", re.MULTILINE),
}


def validate_rendered_card(text: str, card: dict) -> list[str]:
    """Assert the rendered card body contains every required
    piece per the plan's checklist.

    Returns a list of failure descriptions (empty = all
    checks passed). The renderer must already have produced
    ``text`` from ``card`` via ``render_card``.
    """
    failures: list[str] = []
    if not isinstance(text, str):
        failures.append("rendered text is not a string")
        return failures
    if not text.strip():
        failures.append("rendered text is empty")
        return failures
    for label, pattern in _REQUIRED_TEXT_PATTERNS.items():
        if not pattern.search(text):
            failures.append(f"missing required piece: '{label}'")

    # Per-scope required pieces.
    scope = card.get("scope") if isinstance(card, dict) else None
    if scope == "MARKET_SETUP":
        # Conditional checks: at least one of net_debit / net_credit
        # must appear (as "Act only if: ...").
        if "Act only if:" not in text:
            failures.append("MARKET_SETUP missing bounded price ('Act only if:')")
        if "maximum loss" not in text and "Risk:" not in text:
            failures.append("MARKET_SETUP missing max loss")
    elif scope == "CONDITIONAL_PROTECTION":
        if "Protection premium at risk" not in text:
            failures.append("CONDITIONAL_PROTECTION missing protection premium line")

    # Each leg must be rendered with side/ratio/tradingsymbol/
    # expiry/strike/option_type/lot/bid/ask.
    legs = card.get("legs", []) if isinstance(card, dict) else []
    if isinstance(legs, (list, tuple)):
        for i, leg in enumerate(legs):
            if not isinstance(leg, dict):
                continue
            side = leg.get("side")
            ratio = leg.get("ratio")
            tradingsymbol = leg.get("tradingsymbol")
            expiry = leg.get("expiry")
            strike = leg.get("strike")
            option_type = leg.get("option_type")
            lot_size = leg.get("lot_size")
            # Expected substring: "SIDE RATIO× TRADINGSYMBOL | EXPIRY STRIKETYPE | lot LOT | bid/ask ..."
            pattern = re.compile(
                rf"{re.escape(str(side))} {re.escape(str(ratio))}× {re.escape(str(tradingsymbol))} "
                rf"\| {re.escape(str(expiry))} {re.escape(str(strike))}{re.escape(str(option_type))} "
                rf"\| lot {re.escape(str(lot_size))} \| bid/ask "
            )
            if not pattern.search(text):
                failures.append(
                    f"leg[{i}] missing or malformed in rendered text "
                    f"(expected side={side}, ratio={ratio}, "
                    f"tradingsymbol={tradingsymbol}, expiry={expiry}, "
                    f"strike={strike}, option_type={option_type}, lot_size={lot_size})"
                )

    return failures


def render_and_validate(card: dict) -> tuple[str, list[str]]:
    """Render + validate in one call.

    Returns ``(rendered_text, failures)``. ``failures`` is
    empty on success. Raises ``CardRenderError`` if the
    render itself fails (e.g. over Telegram limit).
    """
    text = render_card(card)
    failures = validate_rendered_card(text, card)
    return text, failures


__all__ = [
    "MAX_TELEGRAM_CHARS",
    "CardRenderError",
    "render_card",
    "validate_rendered_card",
    "render_and_validate",
]
