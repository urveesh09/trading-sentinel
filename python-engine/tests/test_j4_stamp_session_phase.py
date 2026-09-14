"""[WORKFLOW-J.4 2026-09-13] Tests for the wired ``stamp_session_phase``.

The G forward-compat seam ``proactive_intelligence.stamp_session_phase``
was a typed placeholder returning ``_SESSION_PHASE_UNKNOWN`` for every
input. J.4 wires it to the J.1+J.3.1 classifier via
``market_calendar.classify_session_phase``.

The contract change is bounded and explicit:

  1. ``observation_at=None`` still returns ``"UNKNOWN"``. This
     preserves the existing call site at ``_ensure_shadow_run``
     (line 817 of ``proactive_intelligence.py``) which has no
     timestamp in scope and the integration test at
     ``test_run_workflow_manifest_records_session_phase_unknown``
     which asserts that integration record carries
     ``session_phase == "UNKNOWN"``.

  2. ``observation_at=<real datetime>`` returns the bounded phase
     from ``classify_session_phase``. Legacy tests in
     ``test_session_phase_placeholder`` (``TestStampSessionPhase``)
     and ``test_session_classifier``
     (``TestProductionBehaviourPreserved``) pin "returns UNKNOWN
     for every input" were updated in J.4 to reflect the new
     contract: UNKNOWN only for ``None``, real phases otherwise.

  3. New kwargs ``symbol``, ``is_derivative``, ``cas_eligible`` are
     keyword-only and default to ``None`` / ``False``. They mirror
     ``classify_session_phase`` so callers can supply a CAS-eligible
     symbol or a derivative without consulting ``is_cas_eligible``
     themselves. The legacy path (``observation_at`` only) preserves
     byte-identity for any caller that does not pass the new
     kwargs.

  4. The function remains pure (no I/O, no clock) and total
     (returns a known phase from ``_VALID_SESSION_PHASES`` for any
     input). Laziness is preserved: we import
     ``market_calendar.classify_session_phase`` inside the function
     to keep ``proactive_intelligence`` importable without
     ``market_calendar`` present (the G-side module is policy-
     agnostic and the prior arc explicitly avoided coupling to
     session-aware modules at import time).
"""
from __future__ import annotations

import inspect
from datetime import datetime, timezone

import pytz
import pytest

from market_calendar import (
    _VALID_SESSION_PHASES,
    SESSION_PHASE_UNKNOWN,
)
from proactive_intelligence import (
    _SESSION_PHASE_UNKNOWN,
    stamp_session_phase,
)


# ---- (1) Constants still export UNKNOWN -------------------------------

def test_session_phase_unknown_constant_unchanged() -> None:
    """The exported constant keeps its identity (manifests emitted
    before and after J.4 still reference the same string).
    """
    assert _SESSION_PHASE_UNKNOWN == "UNKNOWN"
    assert SESSION_PHASE_UNKNOWN == "UNKNOWN"
    assert _SESSION_PHASE_UNKNOWN == SESSION_PHASE_UNKNOWN


# ---- (2) None still returns UNKNOWN (preserved contract) -----------

class TestNonePreservesUnknown:
    """The ``_ensure_shadow_run`` manifest site passes
    ``observation_at=None``. The existing integration test
    asserts the persisted manifest carries ``UNKNOWN`` for that
    case. J.4 keeps this contract.
    """

    def test_none_returns_unknown(self) -> None:
        assert stamp_session_phase(observation_at=None) == "UNKNOWN"

    def test_none_with_other_kwargs_returns_unknown(self) -> None:
        # Even with the new kwargs set, observation_at=None
        # pins the unknown branch.
        assert stamp_session_phase(
            observation_at=None,
            symbol="RELIANCE", is_derivative=False,
        ) == "UNKNOWN"
        assert stamp_session_phase(
            observation_at=None,
            symbol="RELIANCE", is_derivative=False,
            cas_eligible=True,
        ) == "UNKNOWN"


# ---- (3) Real datetime returns the classified phase ---------------

class TestRealDatetimeWired:
    """When ``observation_at`` is a real datetime, the helper
    delegates to ``classify_session_phase`` and returns its bounded
    phase. The new kwargs control the eligibility boundary:
    explicit ``cas_eligible=True`` triggers CAS-aware branches even
    when ``settings.CAS_PHASE1_FNO_UNDERLYINGS`` is empty (the
    default in Dev).
    """

    IST = pytz.timezone("Asia/Kolkata")

    def _ist(self, hh: int, mm: int) -> datetime:
        """2026-09-14 in IST. Mondays are canonical trading days."""
        local = self.IST.localize(datetime(2026, 9, 14, hh, mm))
        return local.astimezone(pytz.UTC)

    def test_continuous_trading_at_midday(self) -> None:
        result = stamp_session_phase(
            observation_at=self._ist(12, 0),
        )
        assert result in _VALID_SESSION_PHASES
        assert result == "CONTINUOUS_TRADING"

    def test_pre_market_window(self) -> None:
        result = stamp_session_phase(
            observation_at=self._ist(9, 5),
        )
        assert result == "PRE_MARKET"

    def test_post_market_is_closed(self) -> None:
        result = stamp_session_phase(
            observation_at=self._ist(16, 30),
        )
        assert result == "CLOSED"

    def test_cas_window_requires_explicit_eligibility(self) -> None:
        # Without explicit cas_eligible=True, 15:17 IST on a
        # non-CAS-eligible symbol (Dev's default) returns
        # CONTINUOUS_TRADING -- the symbol has no F&O
        # membership by default.
        result = stamp_session_phase(
            observation_at=self._ist(15, 17), symbol="RELIANCE",
        )
        assert result == "CONTINUOUS_TRADING"

    def test_cas_window_with_explicit_eligibility(self) -> None:
        # The legacy path would return CONTINUOUS_TRADING because
        # Dev settings.CAS_PHASE1_FNO_UNDERLYINGS is empty.
        # The new explicit cas_eligible=True kwarg fires the
        # CAS-aware branch -- this is the J.3.1 boundary wired
        # through the seam.
        result = stamp_session_phase(
            observation_at=self._ist(15, 17),
            symbol="RELIANCE", cas_eligible=True,
        )
        assert result == "CAS_REFERENCE_PRICE_WINDOW"

    def test_cas_window_with_explicit_ineligibility(self) -> None:
        # Belt and suspenders: explicit cas_eligible=False also
        # produces CONTINUOUS_TRADING.
        result = stamp_session_phase(
            observation_at=self._ist(15, 22),
            symbol="RELIANCE", cas_eligible=False,
        )
        assert result == "CONTINUOUS_TRADING"

    def test_derivative_continuous_trading_through_15_29(self) -> None:
        # Derivatives trade continuously through 15:29 IST.
        result = stamp_session_phase(
            observation_at=self._ist(15, 15), is_derivative=True,
        )
        assert result == "CONTINUOUS_TRADING"

    def test_derivative_cas_aligned_at_15_30(self) -> None:
        # NSE/CMTR/76170 effective 2026-09-07: futures CAS-
        # aligned band 15:30-15:40 IST. Applies to derivatives
        # regardless of CAS eligibility.
        result = stamp_session_phase(
            observation_at=self._ist(15, 35), is_derivative=True,
        )
        assert result == "DERIVATIVES_CAS_ALIGNED"

    def test_naive_datetime_treated_as_utc(self) -> None:
        # 04:00 UTC = 09:30 IST (continuous trading). Same
        # convention as classify_session_phase.
        result = stamp_session_phase(
            observation_at=datetime(2026, 9, 14, 4, 0),
        )
        assert result == "CONTINUOUS_TRADING"


# ---- (4) Helper purity and totality -----------------------------

class TestHelperStillPureAndTotal:
    """The helper remains pure (no I/O, no clock) and total
    (returns a known string for any input). J.4 extends the
    signature but does NOT add an I/O coupling.
    """

    def test_returns_string_type(self) -> None:
        out = stamp_session_phase(observation_at=None)
        assert isinstance(out, str)

    def test_returns_documented_phase_value(self) -> None:
        for ts in (None, datetime(2026, 9, 14, 10, 0),
                   datetime(2026, 9, 14, 10, 0, tzinfo=pytz.UTC)):
            out = stamp_session_phase(observation_at=ts)
            assert out in _VALID_SESSION_PHASES, (
                f"unmapped phase {out!r} for {ts!r}"
            )

    def test_signature_uses_keyword_only(self) -> None:
        """No positional drift: G's signature stays keyword-only
        so future J migration is a drop-in. The new kwargs
        append to the parameter list, all keyword-only.
        """
        sig = inspect.signature(stamp_session_phase)
        params = list(sig.parameters.values())
        names = {p.name for p in params}
        assert "observation_at" in names
        # ALL keyword-only. The original contract had ONE
        # keyword-only; J.4 keeps that and appends additional
        # keyword-only kwargs in a stable order.
        assert all(
            p.kind == inspect.Parameter.KEYWORD_ONLY for p in params
        ), "all parameters must be keyword-only"

    def test_source_does_not_call_clock(self) -> None:
        """The implementation must not read the wall clock. J.4's
        contract is total and pure; ``datetime.now`` would
        silently break that.

        We check via AST for actual call nodes, not by string
        match (the function's docstring mentions ``datetime.now``
        in a comment that would otherwise false-fail the test).
        """
        import ast
        src = inspect.getsource(stamp_session_phase)
        tree = ast.parse(src)
        forbidden_call_names = {"datetime.now", "time.time", "time.clock"}
        leaks: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            target_name: str | None = None
            if isinstance(func, ast.Attribute):
                target_name = f"{func.value.id}.{func.attr}" if isinstance(
                    func.value, ast.Name
                ) else None
            elif isinstance(func, ast.Name):
                target_name = func.id
            if target_name in forbidden_call_names:
                leaks.append(target_name)
        assert leaks == [], f"helper uses forbidden tokens: {leaks}"


# ---- (5) Cross-cutting: scheduler / manifest internals ----------

class TestSchedulerCompatibility:
    """The two production call sites in ``proactive_intelligence``
    call ``stamp_session_phase(observation_at=<X>)`` with the
    single-kwarg shape. J.4 preserves those call sites byte-
    identically and accepts the new kwargs only as opt-in.
    """

    @pytest.fixture
    def call_site_shapes(self):
        # The two production call sites and the value of
        # observation_at at each.
        return [
            # _ensure_shadow_run line 817: no observation in
            # scope, always None.
            ("none", None),
            # run_shadow_research_comparison line 2268: signal_at
            # of the first proposal when proposals non-empty.
            ("aware_dt", datetime(2026, 9, 14, 9, 30, tzinfo=timezone.utc)),
        ]

    def test_call_site_shapes_resolve_to_documented_phase(self, call_site_shapes):
        """The two production call sites both produce a known
        bounded phase. The ``none`` site preserves the existing
        UNKNOWN behavior; the ``aware_dt`` site now resolves to
        a real phase (this IS the J.4 contract change).
        """
        from market_calendar import SESSION_PHASE_CONTINUOUS_TRADING
        for label, ts in call_site_shapes:
            out = stamp_session_phase(observation_at=ts)
            assert out in _VALID_SESSION_PHASES, (label, out)
            if label == "none":
                assert out == "UNKNOWN"
            elif label == "aware_dt":
                # 09:30 UTC = 15:00 IST = CONTINUOUS_TRADING on a
                # Monday trading day.
                assert out == SESSION_PHASE_CONTINUOUS_TRADING
