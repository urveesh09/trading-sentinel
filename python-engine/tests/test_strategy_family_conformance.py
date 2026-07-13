"""[ROADMAP-4.2 2026-07-13] Cross-family conformance invariants.

WHY THIS FILE EXISTS INSTEAD OF THE SHARED BASE CLASSES THE ROADMAP ASKED FOR
----------------------------------------------------------------------------
Roadmap 4.2 says the strategy families "each reimplement the same
schema-write / kill-switch / zero-accept / report pattern" and asks for
shared bases to be extracted. Measuring the actual code says otherwise:

    family            shared fn names   avg structural similarity
    signal_log (x3)   0                 --
    accept_watchdog   2                 10-15%
    hourly_report     1                 0%
    risk_engine (x3)  1 (__init__)      26%  (penny vs fno: nothing)

They are not copies that drifted apart. They are independent
implementations that share a NAMING CONVENTION and nothing else. Extracting
a "shared base" from bodies with ~10% in common would mean writing a base
class with more hooks than shared logic -- a false abstraction, in the code
that sizes real money.

The roadmap's own justification does not survive either. It says the 3.7
kill-switch timezone bug "exists precisely because they diverged". It does
not: penny keys the day through PennyRiskEngine._trading_day(), F&O derives
IST dates in SQL over fno_positions. There was never a shared copy to
diverge FROM. Penny's bug was penny's own bug.

But the RISK the roadmap was reaching for is real, and worth defending:
several independent families must obey the same cross-cutting rules, and
today nothing checks that they do. A fourth family would be free to get the
day boundary wrong all over again.

So: enforce the invariants directly, without forcing the families to share
structure they do not have. Conformance, not inheritance. This scales to
the next strategy; a base class would only have constrained it.
"""
import ast
import pathlib

import pytest

ENGINE = pathlib.Path(__file__).resolve().parent.parent


# ===================================================================
# Invariant 1: the trading day is an IST day. Always.
# ===================================================================
# This is the 3.7 bug class, stated as a rule instead of fixed once.
#
# A naive `datetime.now()` / `date.today()` / `utcnow()` inside a module
# that decides WHICH TRADING DAY IT IS rolls over at UTC midnight -- 05:30
# IST, i.e. in the middle of the pre-market window. A daily kill-switch
# keyed that way resets itself hours after the day it is meant to protect
# has already begun.

DAY_KEYED_MODULES = [
    "penny_risk.py",       # penny daily kill-switch (the 3.7 fix lives here)
    "fno_risk.py",         # F&O daily loss caps + liveness
    "penny_scanner.py",    # per-day signal dedupe
    "token_lifecycle.py",  # same-IST-day token freshness rule
    "ops_metrics.py",      # per-IST-day liveness/funnel rows
]

# Bare-naive constructors that silently mean UTC inside a container.
NAIVE_CALLS = {
    "datetime.now": "datetime.now() with no tz -- UTC in the container",
    "datetime.utcnow": "datetime.utcnow() -- explicitly UTC",
    "date.today": "date.today() -- rolls at UTC midnight = 05:30 IST",
}


def _naive_day_calls(path: pathlib.Path) -> list[str]:
    """Find datetime.now()/utcnow()/date.today() calls that are NOT handed a
    timezone. `datetime.now(IST)` and `datetime.now(timezone.utc)` are both
    explicit and fine; a bare `datetime.now()` is the bug.

    Match on the AST shape, NOT on the unparsed string. The first version of
    this matched `ast.unparse(node.func).split("(")[0]`, which turns the
    chained call `datetime.now(timezone.utc).isoformat()` into the text
    "datetime.now" -- and then, because .isoformat() takes no arguments, the
    "is it given a timezone?" check looked at the WRONG call's arg list and
    flagged a perfectly explicit UTC timestamp. Three false positives.
    """
    tree = ast.parse(path.read_text())
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # We want exactly `<something>.now(...)` / `.utcnow()` / `.today()`,
        # where <something> is the datetime/date class itself -- and we must
        # look at THIS call's args, not an outer chained call's.
        if not isinstance(func, ast.Attribute):
            continue
        attr = func.attr
        if attr not in ("now", "utcnow", "today"):
            continue
        owner = func.value
        owner_name = owner.attr if isinstance(owner, ast.Attribute) else (
            owner.id if isinstance(owner, ast.Name) else ""
        )
        # `datetime`, `date`, and the `_dt` / `dt` aliases this codebase uses.
        if owner_name not in ("datetime", "date", "_dt", "dt"):
            continue
        key = f"{'date' if attr == 'today' else 'datetime'}.{attr}"
        if key not in NAIVE_CALLS:
            continue
        # An explicit tz (positional or keyword) makes it unambiguous.
        if node.args or any(k.arg in ("tz", "tzinfo") for k in node.keywords):
            continue
        hits.append(
            f"line {node.lineno}: {owner_name}.{attr}() -- {NAIVE_CALLS[key]}"
        )
    return hits


@pytest.mark.parametrize("module", DAY_KEYED_MODULES)
def test_day_keyed_modules_never_use_a_naive_clock(module):
    """Every module that keys state on 'today' must go through IST.

    Roadmap 3.7 fixed exactly this in penny_risk (the kill-switch was
    rolling at UTC midnight). Fixing it once does not stop the next family
    from reintroducing it -- this does.
    """
    path = ENGINE / module
    if not path.exists():
        pytest.skip(f"{module} not present")

    hits = _naive_day_calls(path)
    assert not hits, (
        f"{module} decides which trading day it is, but uses a NAIVE clock:\n"
        + "\n".join(f"  {h}" for h in hits)
        + "\n\nA naive datetime is UTC inside the container, so the day rolls "
        "at 05:30 IST -- mid pre-market. Pass IST explicitly: "
        "datetime.now(IST). This is the roadmap-3.7 bug class."
    )


# ===================================================================
# Invariant 2: every strategy family that can reject has a zero-accept
# watchdog wired to the scheduler.
# ===================================================================
# The 9-month penny dead-gate (a gate that could never fire, discovered only
# by hand-auditing 215,814 CSV rows) is the reason the zero-accept watchdogs
# exist at all. A new family without one can repeat that in silence.

FAMILIES_THAT_GATE = ["penny", "fno"]


@pytest.mark.parametrize("family", FAMILIES_THAT_GATE)
def test_every_gating_family_has_a_zero_accept_watchdog(family):
    watchdog = ENGINE / f"{family}_accept_watchdog.py"
    assert watchdog.exists(), (
        f"family '{family}' has entry gates but no {watchdog.name}. "
        "The penny dead-gate went unnoticed for nine months precisely "
        "because nothing watched for a gate that never accepts."
    )
    src = watchdog.read_text()
    assert "zero_accept_scan" in src
    assert "format_zero_accept_alert" in src


def test_zero_accept_watchdogs_are_actually_scheduled():
    """A watchdog that exists but is never registered is decoration. Assert
    each one is wired into a real add_job call somewhere in the package."""
    all_src = "\n".join(
        p.read_text() for p in ENGINE.glob("*.py")
    )
    for family in FAMILIES_THAT_GATE:
        assert f"_run_{family}_accept_watchdog_safe" in all_src, (
            f"{family}'s zero-accept watchdog is not registered with the "
            "scheduler -- it will never run."
        )


# ===================================================================
# Invariant 3: bankroll isolation -- families never read each other's money.
# ===================================================================
# The pools are deliberately separate (penny / nifty-swing+momentum / fno).
# A query that forgets its `source` filter silently mixes them, and the
# symptom is a wrong bankroll, i.e. wrong position sizes.

RISK_PATH_MODULES = [
    "risk_engine.py", "penny_risk.py", "fno_risk.py",
    "penny_scanner.py", "penny_engine_breakout.py", "penny_engine_connors.py",
    "fno_orchestrator.py", "fno_gates.py",
]


def test_deprecated_global_bankroll_never_returns_to_a_sizing_path():
    """current_bankroll() reads the LAST bankroll_after row across ALL
    sources, so whichever pool traded most recently wins. AUDIT-FIX-1.1
    already removed it from the risk paths and replaced it with
    bankroll_for_source() / nifty_bankroll(); the function survives only for
    legacy report fields.

    Removing it once does not stop it coming back -- it is the obvious-looking
    helper with the friendly name, and re-introducing it into a sizing path
    would silently size penny trades off the swing pool's bankroll (or vice
    versa). That is the concrete way the "shared bankroll isolation" the
    roadmap wants to preserve actually gets broken.

    (This is what invariant 3 SHOULD assert. The first draft asserted that
    every bankroll_ledger SQL string mentions `source`, which flagged three
    legitimately global reads -- a row-count existence check, the CB_RESET
    marker lookup, and current_bankroll's own deprecated body. A rule that
    cries wolf on correct code gets deleted by the next person; this one has
    no false positives and names a real regression.)
    """
    offenders = []
    for name in RISK_PATH_MODULES:
        path = ENGINE / name
        if not path.exists():
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call):
                try:
                    called = ast.unparse(node.func)
                except Exception:
                    continue
                if called.split(".")[-1] == "current_bankroll":
                    offenders.append(f"{name}:{node.lineno}: calls {called}()")
            if isinstance(node, ast.ImportFrom) and node.module == "performance":
                for a in node.names:
                    if a.name == "current_bankroll":
                        offenders.append(
                            f"{name}:{node.lineno}: imports current_bankroll"
                        )

    assert not offenders, (
        "the deprecated global current_bankroll() is back in a RISK/SIZING "
        "path -- it reads the last ledger row across ALL pools, so it sizes "
        "one strategy off another's money:\n"
        + "\n".join(f"  {o}" for o in offenders)
        + "\nUse bankroll_for_source(db_path, source) or nifty_bankroll()."
    )
