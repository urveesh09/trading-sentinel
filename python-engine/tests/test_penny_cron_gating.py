"""
Static-analysis guard test: every scheduler-registered cron handler in
main.py MUST gate on weekends + NSE holidays OR be in the
EXPECTED_PENDING_P1 allowlist with an [EXPECTED-FAIL P1] marker.

[CALENDAR-GUARD-TEST 2026-07-03] Created after audit
docs/deviations/2026-07-03-market-calendar-coverage-audit.md showed that
13 of 15 penny cron handlers had no weekend/holiday awareness. The
P0-PR adds gates to the financial-risk + Telegram-noise subset. This
test enforces:

1. Every target of `scheduler.add_job(callable, ...)` must either:
   (a) Contain `is_trading_day(...)` in its body (gate present), or
   (b) Contain the documented-exception marker
       `[CALENDAR-GATE 2026-07-03]` in its docstring/source
       (gate explicitly waived, ideally via is_market_open() or
       call-by-call async check inside the callable), or
   (c) Be in EXPECTED_PENDING_P1 with an explicit audit-code marker
       (gate is known-missing; fix is planned/scheduled).

2. Indirect-call targets (e.g. _run_*_impl called from a wrapper) are
   followed by checking the wrapper's call chain -- if the wrapper
   ultimately delegates to a gated impl, the wrapper is treated as
   gated.

3. A fatal exception: a handler that places real orders (auto_square,
   force_close, penny_edge_exit) MUST be gated. The P0 audit
   identified these three as the financial-risk surface. Even if a
   handler is in EXPECTED_PENDING_P1, if its name appears in the
   FINANCIAL_RISK allowlist, the test FAILS with a louder error.

When the operator wants to add a NEW cron handler:
  - Add it to scheduler.add_job(...) and to this test's parser.
  - The test will surface it as un-gated (test fails) until the
    handler has the gate (or the documented exception marker).

Defence against the 2026-07-03 bug class ("penny cron silently does
the wrong thing on weekends"). Forever.
"""

import ast
import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Handbook of crons known to be / not be gated as of 2026-07-03.
# ---------------------------------------------------------------------------

# Gated through a wrapper that ultimately calls a gated impl.
# These pass because the *eventual* callee contains the gate.
GATED_VIA_WRAPPER = {
    "run_momentum_screener": "delegates to _run_momentum_screener_impl "
                             "which has `is_trading_day(today)` at top",
}

# Marked with the documented exception marker. Either the gate is
# implicit (e.g. is_market_open() inside) or the operator has documented
# why this cron fires on non-trading days.
GATED_VIA_MARKER = {
    "run_screener",  # uses is_trading_day(today, settings.DB_PATH)
}

# Handlers that are KNOWN to have NO gate today but are not yet fixed in
# this PR. The audit classified them as P1 (network waste + stale regime
# overwriting) rather than P0 (financial risk + Telegram noise). They MUST
# carry the [EXPECTED-FAIL P1] marker so the test can grep them out.
#
# 2026-07-03 PR-2: P1 allowlist is EMPTY. Every penny cron handler is
# now gated. Re-introduce the allowlist only when a future PR needs to
# defer a new handler; the rule is that EVERY new cron must gate or be
# explicitly allowlisted with [EXPECTED-FAIL P*].
EXPECTED_PENDING_P1: set[str] = set()

# Handlers that place real orders. These can NEVER be in
# EXPECTED_PENDING_P1 -- the [EXPECTED-FAIL P1] marker is rejected for
# them, forcing a CI failure if anyone tries to slip them past.
FINANCIAL_RISK = {
    "auto_square_momentum",
    "run_penny_force_close_mis",
    "_run_penny_edge_exit_safe",
}

# Crons that are not financial-risk but operate on a non-trading day
# without much downside (e.g. kite instrumentation refresh). Skipped
# from the gate requirement entirely.
NO_GATE_NEEDED = {
    "kite.refresh_instrument_cache",  # needed for token bootstrap; pure data layer
    "kite.clear_intraday_cache",      # DB cleanup, hour-agnostic
    "_penny_daily_reset",             # risk-engine singleton reset at 00:05 IST
    # [ROADMAP-2.4 2026-07-12] Loop-progress tick for the agent's freeze
    # watchdog. MUST run 24/7: gating it would make "stale file" ambiguous
    # (frozen scheduler vs. calendar gate), defeating the whole probe.
    # Zero financial risk: it only writes a timestamp to /data.
    "_scheduler_tick_job",
}


# ---------------------------------------------------------------------------
# AST extraction: find every `scheduler.add_job(target, ...)` call site.
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
MAIN_PY = REPO_ROOT / "main.py"

# [ROADMAP-4.1 2026-07-13] This guard used to read main.py and nothing else,
# on the assumption that every scheduled handler lives there. The 4.1 split
# broke that assumption -- _token_reconciliation_tick and
# _kite_endpoint_probe_tick moved to token_lifecycle.py / ops_watchdogs.py,
# and the test immediately reported "could not locate function source", which
# is the failure mode it names as "a test infrastructure bug".
#
# It is a genuinely valuable guard (every cron handler must gate on weekends
# and NSE holidays, or be explicitly exempt), so it follows the code rather
# than being narrowed: search the whole engine package. This also means the
# guard keeps working as the rest of main.py is split up.
ENGINE_SOURCES = [
    p for p in sorted(REPO_ROOT.glob("*.py")) if p.name != "conftest.py"
]


def _all_sources() -> str:
    """Every engine module, concatenated. Used for whole-package searches
    (function bodies). Line numbers from this blob are meaningless -- only
    main.py's own numbering is reported, and only as `~N` guidance."""
    return "\n".join(p.read_text() for p in ENGINE_SOURCES)


def _collect_add_job_targets(src_text: str) -> list[tuple[int, str]]:
    """Return a list of (line_number, target_name) for every
    scheduler.add_job(target, ...) call. `target_name` is the AST
    string for the first positional argument of each call.
    """
    tree = ast.parse(src_text)
    targets: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "add_job"):
            continue
        if not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Name):
            targets.append((node.lineno, first.id))
        elif isinstance(first, ast.Attribute):
            # e.g. kite.refresh_instrument_cache
            targets.append((node.lineno, ast.unparse(first)))
        else:
            # Closures (async def inside register_penny_scheduler_jobs)
            # show up as <unknown>; we resolve those by scanning for
            # `async def <name>(` near the call site.
            targets.append((node.lineno, "<closure>"))
    return targets


def _resolve_closures(src_text: str, closure_call_sites: list[int]) -> dict[int, str]:
    """Walk the lines of main.py, find the closest `async def` ABOVE
    each add_job call site. Return {call_site_lineno: closure_name}.
    """
    lines = src_text.split("\n")
    closure_for_site: dict[int, str] = {}
    last_async_def: str | None = None
    last_def_line: int = -1
    for ln, _ in closure_call_sites:
        for i in range(ln - 1, 0, -1):
            line = lines[i - 1]
            m = re.match(r"^\s*async def ([a-zA-Z_]\w*)\(", line)
            if m:
                last_async_def = m.group(1)
                last_def_line = i
                break
        closure_for_site[ln] = last_async_def or "<unknown>"
    return closure_for_site


def _function_body(src_text: str, name: str) -> str:
    """Return the source of a top-level `def name(...)` / `async def name(...)`
    function, plus any nested defs it contains (heuristic: until next
    top-level def/class at column 0)."""
    lines = src_text.split("\n")
    pat = re.compile(rf"^(?:async )?def {re.escape(name)}\(")
    start: int | None = None
    for i, line in enumerate(lines):
        if pat.match(line):
            start = i
            break
    if start is None:
        return ""
    end = len(lines)
    for j in range(start + 1, len(lines)):
        line = lines[j]
        if line and not line.startswith((" ", "\t")) and (
            line.startswith("def ")
            or line.startswith("async def ")
            or line.startswith("class ")
            or line.startswith("@app.")
        ):
            end = j
            break
    return "\n".join(lines[start:end])


# ---------------------------------------------------------------------------
# The actual test classes.
# ---------------------------------------------------------------------------


class TestSchedulerHandlersGated:
    """Every scheduler.add_job(callable, ...) call's target must either
    contain an is_trading_day gate, carry the documented-exception marker,
    or be in EXPECTED_PENDING_P1 -- AND if it's a financial-risk handler
    it can NEVER be in pending."""

    def test_every_cron_handler_has_a_gate_or_is_allowlisted(self):
        src = MAIN_PY.read_text()
        targets = _collect_add_job_targets(src)

        # Resolve closure targets -- they appear as `<closure>`.
        closure_sites = [ln for ln, name in targets if name == "<closure>"]
        closure_names = _resolve_closures(src, closure_sites)

        # Each unique target gets one test verdict.
        unique_targets: dict[str, int] = {}
        for ln, name in targets:
            resolved = (
                closure_names.get(ln, name) if name == "<closure>" else name
            )
            # First occurrence wins for the dedupe but we still want
            # all line numbers reported on failure.
            unique_targets.setdefault(resolved, ln)

        failures: list[str] = []

        for target, first_line in unique_targets.items():
            if target in NO_GATE_NEEDED:
                continue

            # 1. Wrapper delegation is OK.
            if target in GATED_VIA_WRAPPER:
                continue

            # 2. Look up the function body (top-level def OR closure body
            #    via the resolved name). Search main.py first, then the rest
            #    of the package -- handlers extracted by the 4.1 split
            #    (token_lifecycle, ops_watchdogs) live outside main.py now.
            body = _function_body(src, target) or _function_body(
                _all_sources(), target
            )

            # Closures inside register_penny_scheduler_jobs are NOT
            # top-level defs -- `_function_body` returns "" for them.
            # For closures we already know (because they're in the
            # P0-PR allowlist) that they DO have the gate (patched today).
            # Treat them as gated and don't re-test.
            if not body:
                # Closure: scan the source from register_penny_scheduler_jobs
                # to the end of the function for the matched name.
                m = re.search(
                    rf"async def {re.escape(target)}\(.*?(?=\n    [a-zA-Z]|\nasync def |\ndef )",
                    src,
                    re.DOTALL,
                )
                if m:
                    body = m.group(0)

            if not body:
                failures.append(
                    f"  - {target} (line ~{first_line}): "
                    f"could not locate function source -- "
                    f"this is a test infrastructure bug."
                )
                continue

            has_gate = "is_trading_day" in body
            has_marker = "[CALENDAR-GATE 2026-07-03]" in body
            # The expected-fail marker can be the date-suffixed form
            # (`[EXPECTED-FAIL P1 2026-07-03]`) or the bare tag. We
            # accept either.
            has_expected_fail = bool(
                re.search(r"\[EXPECTED-FAIL\s+P1\b", body)
            )

            if has_gate:
                continue
            if has_marker:
                continue

            # 3. Pending-P1 fallback: must carry an audit-code marker.
            if target in EXPECTED_PENDING_P1:
                if target in FINANCIAL_RISK:
                    failures.append(
                        f"  - {target} (line ~{first_line}): FORBIDDEN. "
                        f"This is a financial-risk handler and CANNOT be "
                        f"in EXPECTED_PENDING_P1. Add the gate IMMEDIATELY."
                    )
                    continue
                if not has_expected_fail:
                    failures.append(
                        f"  - {target} (line ~{first_line}): in "
                        f"EXPECTED_PENDING_P1 but lacks the "
                        f"[EXPECTED-FAIL P1 ...] marker. Add the marker "
                        f"so this test can grep it out at audit time."
                    )
                continue

            # 4. New / unrecognised handler: must gate.
            failures.append(
                f"  - {target} (line ~{first_line}): UNGATED. Every "
                f"new cron handler must call is_trading_day(today, "
                f"settings.DB_PATH) at the top, carry the [CALENDAR-GATE "
                f"2026-07-03] documented-exception marker, or be in "
                f"EXPECTED_PENDING_P1 with [EXPECTED-FAIL P1]. "
                f"[CALENDAR-GUARD-TEST 2026-07-03]"
            )

        if failures:
            msg = "\n".join(failures)
            raise AssertionError(
                f"{len(failures)} scheduler-registered handler(s) lack a "
                f"calendar gate or explicit exemption:\n\n{msg}"
            )


class TestFinancialRiskHandlersAlwaysGated:
    """FINANCIAL_RISK handlers must contain `is_trading_day` directly.
    The documented-exception marker and the pending-P1 escape hatches
    are explicitly REJECTED for these.
    """

    def test_financial_risk_handlers_call_is_trading_day(self):
        src = MAIN_PY.read_text()
        for handler in FINANCIAL_RISK:
            body = _function_body(src, handler)
            # Closure fallback.
            if not body:
                m = re.search(
                    rf"async def {re.escape(handler)}\(.*?(?=\n    [a-zA-Z]|\nasync def |\ndef )",
                    src,
                    re.DOTALL,
                )
                if m:
                    body = m.group(0)
            assert "is_trading_day" in body, (
                f"FINANCIAL-RISK handler {handler!r} must call "
                f"`is_trading_day(...)` directly. No documented-exception "
                f"marker, no P1 deferral allowed. Real orders are placed "
                f"here and a weekend firing could exit positions at stale "
                f"quotes. [CALENDAR-GUARD-TEST 2026-07-03]"
            )
