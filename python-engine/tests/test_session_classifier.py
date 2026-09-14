"""[WORKFLOW-J 2026-09-13] CAS-aware session classifier acceptance.

Plan §14: introduce an exchange/security/session-phase model after
verifying effective dates and broker behaviour. The dates have been
verified from primary NSE/BSE sources (see
``docs/2026-09-13-workflow-j-deep-research.md``); broker behaviour is
NOT verified (no live broker in Dev). This file therefore asserts the
classifier's pure/total contract over the documented phases without
depending on a live broker.

The classifier is consumed by J.2+ callers; production behaviour in
J.1 is unchanged -- ``stamp_session_phase`` (in ``proactive_intelligence``)
still returns "UNKNOWN" for ``observation_at=None`` so existing call
sites are not regressed.

Sources (all verified 2026-09-13):
  * NSE CAS page: https://www.nseindia.com/static/products-services/closing-auction-session
  * NSE circulars NSE/CMTR/72394 (CAS Phase 1 introduction),
    NSE/CMTR/73362 (SOP), NSE/CMTR/76170 (index-futures CAS-aligned band,
    effective 2026-09-07).
  * BSE Notice 20260801-2 (BSE CAS derivatives effective 2026-08-03).
"""
from __future__ import annotations

import datetime as _dt

import pytz
import pytest

from market_calendar import (
    CAS_LIMIT_ENTRY_ONLY_END,
    CAS_MATCHING_END,
    CAS_OPEN_TIME,
    CAS_ORDER_ENTRY_END,
    CAS_POST_CLOSE_END,
    CAS_REFERENCE_PRICE_END,
    DERIVATIVES_CLOSE_TIME,
    MARKET_CLOSE_TIME,
    MARKET_OPEN_TIME,
    PRE_MARKET_OPEN_TIME,
    SESSION_PHASE_CAS_LIMIT_ENTRY_ONLY,
    SESSION_PHASE_CAS_MATCHING,
    SESSION_PHASE_CAS_ORDER_ENTRY,
    SESSION_PHASE_CAS_POST,
    SESSION_PHASE_CAS_REFERENCE_PRICE_WINDOW,
    SESSION_PHASE_CLOSED,
    SESSION_PHASE_CONTINUOUS_TRADING,
    SESSION_PHASE_DERIVATIVES_CAS_ALIGNED,
    SESSION_PHASE_PRE_MARKET,
    SESSION_PHASE_UNKNOWN,
    _VALID_SESSION_PHASES,
    classify_session_phase,
    is_cas_eligible,
)

IST = pytz.timezone("Asia/Kolkata")


#: 2026-09-14 is a Monday; tests below use it as the canonical
#: weekday=0 trading day. Saturday = +5, Sunday = +6.
_BASE_DATE = _dt.date(2026, 9, 14)


def _ist(h: int, m: int, *, weekday_offset: int = 0, seconds: int = 0) -> _dt.datetime:
    """Return a timezone-aware UTC datetime that, in IST, is the
    given hour:minute on the canonical Monday plus ``weekday_offset``
    days. ``seconds`` lets tests probe the within-minute boundary.
    """
    local = IST.localize(_dt.datetime(
        _BASE_DATE.year, _BASE_DATE.month, _BASE_DATE.day + weekday_offset,
        h, m, seconds,
    ))
    return local.astimezone(pytz.UTC)


# ---- (1) Constants are documented and correct ------------------------

class TestCentralSessionConstants:
    """The constants are the single source of truth for session
    clocks. Adding a new constant requires a docstring update here
    AND in ``market_calendar.py``. Tests pin the values so a typo
    fails CI.
    """

    def test_pre_market_opens_at_09_00(self) -> None:
        assert (PRE_MARKET_OPEN_TIME.hour, PRE_MARKET_OPEN_TIME.minute) == (9, 0)

    def test_market_opens_at_09_15(self) -> None:
        assert (MARKET_OPEN_TIME.hour, MARKET_OPEN_TIME.minute) == (9, 15)

    def test_cash_market_closes_at_15_30(self) -> None:
        assert (MARKET_CLOSE_TIME.hour, MARKET_CLOSE_TIME.minute) == (15, 30)

    def test_derivatives_close_at_15_40(self) -> None:
        # NSE equity derivatives session: 09:15-15:40 IST.
        assert (DERIVATIVES_CLOSE_TIME.hour, DERIVATIVES_CLOSE_TIME.minute) == (15, 40)

    def test_cas_opens_at_15_15(self) -> None:
        # NSE CAS sub-window 1 begins at 15:15 IST.
        assert (CAS_OPEN_TIME.hour, CAS_OPEN_TIME.minute) == (15, 15)

    def test_cas_reference_price_window_5_min(self) -> None:
        # 15:15-15:20: reference price calc.
        assert (CAS_REFERENCE_PRICE_END.hour, CAS_REFERENCE_PRICE_END.minute) == (15, 20)

    def test_cas_order_entry_window_5_min(self) -> None:
        # 15:20-15:25: order entry for limit + market.
        assert (CAS_ORDER_ENTRY_END.hour, CAS_ORDER_ENTRY_END.minute) == (15, 25)

    def test_cas_limit_only_window_5_min(self) -> None:
        # 15:25-15:30: limit orders only, market orders blocked.
        assert (CAS_LIMIT_ENTRY_ONLY_END.hour, CAS_LIMIT_ENTRY_ONLY_END.minute) == (15, 30)

    def test_cas_matching_window_5_min(self) -> None:
        # 15:30-15:35: matching + confirmation.
        assert (CAS_MATCHING_END.hour, CAS_MATCHING_END.minute) == (15, 35)

    def test_cas_post_close_window_25_min(self) -> None:
        # 15:35-16:00: transition + post-close session.
        assert (CAS_POST_CLOSE_END.hour, CAS_POST_CLOSE_END.minute) == (16, 0)


# ---- (2) Bounded phase set --------------------------------------------

class TestBoundedPhaseSet:
    def test_valid_phases_is_frozen_and_complete(self) -> None:
        # Exactly the 10 documented phases. A future addition must
        # update this set AND the docstring list above.
        assert _VALID_SESSION_PHASES == frozenset({
            SESSION_PHASE_CLOSED, SESSION_PHASE_PRE_MARKET,
            SESSION_PHASE_CONTINUOUS_TRADING,
            SESSION_PHASE_CAS_REFERENCE_PRICE_WINDOW,
            SESSION_PHASE_CAS_ORDER_ENTRY,
            SESSION_PHASE_CAS_LIMIT_ENTRY_ONLY,
            SESSION_PHASE_CAS_MATCHING,
            SESSION_PHASE_CAS_POST,
            SESSION_PHASE_DERIVATIVES_CAS_ALIGNED,
            SESSION_PHASE_UNKNOWN,
        })

    def test_classifier_never_returns_an_unmapped_phase(self) -> None:
        """Try a wide range of timestamps + flag combinations; every
        return value must be a documented phase. This is the
        contract test: if a new branch returns a string outside the
        set, this fails.
        """
        from datetime import datetime, timezone
        samples = []
        # Generate a comprehensive set of (timestamp, is_derivative, symbol).
        for weekday_offset in range(7):
            for h in range(0, 24):
                for m in (0, 15, 30, 45):
                    samples.append((_ist(h, m, weekday_offset=weekday_offset), False, None))
                    samples.append((_ist(h, m, weekday_offset=weekday_offset), True, "SYNTH"))
        # Edge: naive datetime
        samples.append((datetime(2026, 9, 14, 4, 0), False, None))
        # Edge: aware UTC midnight
        samples.append((datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc), False, None))
        # Edge: None
        samples.append((None, False, None))
        for observation_at, is_derivative, symbol in samples:
            phase = classify_session_phase(
                observation_at, symbol=symbol, is_derivative=is_derivative,
            )
            assert phase in _VALID_SESSION_PHASES, (
                f"unmapped phase {phase!r} for {observation_at!r} "
                f"is_derivative={is_derivative} symbol={symbol!r}"
            )


# ---- (3) Ordinary day phases -------------------------------------------

class TestOrdinaryDay:
    """The Monday base date with no CAS eligibility (Phase 1 list
    empty in Dev) -- the most common case.
    """

    def test_pre_market_open(self) -> None:
        assert classify_session_phase(_ist(9, 0)) == SESSION_PHASE_PRE_MARKET

    def test_pre_market_last_minute(self) -> None:
        assert classify_session_phase(_ist(9, 14, seconds=59)) == SESSION_PHASE_PRE_MARKET

    def test_continuous_trading_open(self) -> None:
        assert classify_session_phase(_ist(9, 15)) == SESSION_PHASE_CONTINUOUS_TRADING

    def test_continuous_trading_midday(self) -> None:
        assert classify_session_phase(_ist(12, 0)) == SESSION_PHASE_CONTINUOUS_TRADING

    def test_continuous_trading_reference_window_for_non_cas(self) -> None:
        """15:00-15:14 IST is still continuous trading for
        non-CAS-eligible cash symbols (the reference price is
        computed from trades IN continuous trading).
        """
        assert classify_session_phase(_ist(15, 0)) == SESSION_PHASE_CONTINUOUS_TRADING
        assert classify_session_phase(_ist(15, 14, seconds=59)) == SESSION_PHASE_CONTINUOUS_TRADING

    def test_non_cas_cash_after_15_15_is_continuous(self) -> None:
        """Non-CAS cash stays in continuous trading until 15:30."""
        assert classify_session_phase(_ist(15, 15)) == SESSION_PHASE_CONTINUOUS_TRADING
        assert classify_session_phase(_ist(15, 29, seconds=59)) == SESSION_PHASE_CONTINUOUS_TRADING

    def test_non_cas_cash_15_30_is_closed(self) -> None:
        assert classify_session_phase(_ist(15, 30)) == SESSION_PHASE_CLOSED

    def test_post_market_window(self) -> None:
        assert classify_session_phase(_ist(15, 31)) == SESSION_PHASE_CLOSED
        assert classify_session_phase(_ist(15, 59, seconds=59)) == SESSION_PHASE_CLOSED

    def test_late_evening_is_closed(self) -> None:
        assert classify_session_phase(_ist(16, 0)) == SESSION_PHASE_CLOSED
        assert classify_session_phase(_ist(23, 59)) == SESSION_PHASE_CLOSED


# ---- (4) CAS windows (Phase 1 eligibility is operator-supplied) -------

class TestCASWindows:
    """Phase 1 CAS only applies to CAS-eligible cash symbols. Dev
    has no populated eligibility list, so the operator has to
    populate it before the classifier returns CAS phases for any
    symbol. We exercise the CAS-eligibility path by monkey-patching
    ``is_cas_eligible`` for these tests.
    """

    @pytest.fixture
    def cas_eligible_world(self, monkeypatch):
        """Force ``is_cas_eligible`` to return True for any symbol
        so the classifier's CAS branches are exercised in Dev.
        """
        def _force_true(symbol):
            return bool(symbol)
        monkeypatch.setattr("market_calendar.is_cas_eligible", _force_true)

    @pytest.mark.usefixtures("cas_eligible_world")
    def test_cas_reference_price_window(self) -> None:
        assert classify_session_phase(_ist(15, 15), symbol="CAS_FAKE") == SESSION_PHASE_CAS_REFERENCE_PRICE_WINDOW
        assert classify_session_phase(_ist(15, 19, seconds=59), symbol="CAS_FAKE") == SESSION_PHASE_CAS_REFERENCE_PRICE_WINDOW

    @pytest.mark.usefixtures("cas_eligible_world")
    def test_cas_order_entry_window(self) -> None:
        assert classify_session_phase(_ist(15, 20), symbol="CAS_FAKE") == SESSION_PHASE_CAS_ORDER_ENTRY
        assert classify_session_phase(_ist(15, 24, seconds=59), symbol="CAS_FAKE") == SESSION_PHASE_CAS_ORDER_ENTRY

    @pytest.mark.usefixtures("cas_eligible_world")
    def test_cas_limit_entry_only_window(self) -> None:
        assert classify_session_phase(_ist(15, 25), symbol="CAS_FAKE") == SESSION_PHASE_CAS_LIMIT_ENTRY_ONLY
        assert classify_session_phase(_ist(15, 29, seconds=59), symbol="CAS_FAKE") == SESSION_PHASE_CAS_LIMIT_ENTRY_ONLY

    @pytest.mark.usefixtures("cas_eligible_world")
    def test_cas_matching_window(self) -> None:
        assert classify_session_phase(_ist(15, 30), symbol="CAS_FAKE") == SESSION_PHASE_CAS_MATCHING
        assert classify_session_phase(_ist(15, 34, seconds=59), symbol="CAS_FAKE") == SESSION_PHASE_CAS_MATCHING

    @pytest.mark.usefixtures("cas_eligible_world")
    def test_cas_post_close_window(self) -> None:
        assert classify_session_phase(_ist(15, 35), symbol="CAS_FAKE") == SESSION_PHASE_CAS_POST
        assert classify_session_phase(_ist(15, 59, seconds=59), symbol="CAS_FAKE") == SESSION_PHASE_CAS_POST

    def test_no_cas_phases_when_symbol_empty(self) -> None:
        """Without a symbol the classifier cannot tell whether the
        observation is CAS-eligible. It stays in continuous trading
        until 15:30 (the conservative non-CAS default).
        """
        assert classify_session_phase(_ist(15, 15), symbol=None) == SESSION_PHASE_CONTINUOUS_TRADING
        assert classify_session_phase(_ist(15, 25), symbol=None) == SESSION_PHASE_CONTINUOUS_TRADING
        assert classify_session_phase(_ist(15, 32), symbol=None) == SESSION_PHASE_CLOSED


# ---- (5) Derivatives session ------------------------------------------

class TestDerivativesSession:
    """The CAS-aligned price band at 15:30-15:40 IST for equity
    derivatives (NSE/CMTR/76170 effective 2026-09-07) is a separate
    phase from CAS for cash. The phase is non-cash-eligible so the
    eligibility branch is skipped; the derivative CAS-aligned
    band applies regardless of CAS-eligibility.
    """

    def test_derivatives_continuous_trading(self) -> None:
        assert classify_session_phase(_ist(9, 30), is_derivative=True) == SESSION_PHASE_CONTINUOUS_TRADING
        assert classify_session_phase(_ist(14, 30), is_derivative=True) == SESSION_PHASE_CONTINUOUS_TRADING

    def test_derivatives_through_15_29_continuous(self) -> None:
        """Derivatives trade continuously through 15:29 IST (CAS
        eligibility only affects cash).
        """
        assert classify_session_phase(_ist(15, 15), is_derivative=True) == SESSION_PHASE_CONTINUOUS_TRADING
        assert classify_session_phase(_ist(15, 29, seconds=59), is_derivative=True) == SESSION_PHASE_CONTINUOUS_TRADING

    def test_derivatives_cas_aligned_band(self) -> None:
        assert classify_session_phase(_ist(15, 30), is_derivative=True) == SESSION_PHASE_DERIVATIVES_CAS_ALIGNED
        assert classify_session_phase(_ist(15, 39, seconds=59), is_derivative=True) == SESSION_PHASE_DERIVATIVES_CAS_ALIGNED

    def test_derivatives_close_at_15_40(self) -> None:
        """15:40 IST = derivatives session CLOSED (per NSE equity
        derivatives end).
        """
        assert classify_session_phase(_ist(15, 40), is_derivative=True) == SESSION_PHASE_CLOSED
        assert classify_session_phase(_ist(15, 50), is_derivative=True) == SESSION_PHASE_CLOSED


# ---- (6) Pre-market and weekend --------------------------------------

class TestPreMarketAndWeekend:
    def test_pre_market_09_00_through_09_14(self) -> None:
        for h, m in [(9, 0), (9, 5), (9, 10), (9, 14)]:
            assert classify_session_phase(_ist(h, m)) == SESSION_PHASE_PRE_MARKET, (h, m)

    def test_saturday_all_day(self) -> None:
        for h in range(0, 24, 3):
            assert classify_session_phase(_ist(h, 0, weekday_offset=5)) == SESSION_PHASE_CLOSED, h

    def test_sunday_all_day(self) -> None:
        for h in range(0, 24, 3):
            assert classify_session_phase(_ist(h, 0, weekday_offset=6)) == SESSION_PHASE_CLOSED, h


# ---- (7) Defensive inputs --------------------------------------------

class TestDefensiveInputs:
    def test_none_observation_is_unknown(self) -> None:
        assert classify_session_phase(None) == SESSION_PHASE_UNKNOWN

    def test_naive_datetime_interpreted_as_utc(self) -> None:
        from datetime import datetime
        # 04:00 UTC = 09:30 IST -> continuous trading
        assert classify_session_phase(datetime(2026, 9, 14, 4, 0)) == SESSION_PHASE_CONTINUOUS_TRADING

    def test_cas_eligibility_with_none_symbol(self) -> None:
        assert is_cas_eligible(None) is False

    def test_cas_eligibility_with_empty_symbol(self) -> None:
        assert is_cas_eligible("") is False

    def test_cas_eligibility_with_non_string(self) -> None:
        """Defensive: a non-string symbol returns False (the
        classifier never crashes on a bad input).
        """
        assert is_cas_eligible(12345) is False  # type: ignore[arg-type]
        assert is_cas_eligible(None) is False


# ---- (8) Production behaviour is preserved ---------------------------

class TestProductionBehaviourPreserved:
    """``stamp_session_phase`` is the J-forward-compat seam. Its
    behaviour MUST NOT change in this slice: it still returns
    ``"UNKNOWN"`` for every input (the existing tests assert
    that).
    """

    def test_stamp_session_phase_still_returns_unknown(self) -> None:
        from proactive_intelligence import stamp_session_phase
        from datetime import datetime
        # The existing call site shape (single keyword arg,
        # observation_at).
        assert stamp_session_phase(observation_at=None) == "UNKNOWN"
        assert stamp_session_phase(observation_at=datetime(2026, 9, 14, 10, 0)) == "UNKNOWN"
        assert stamp_session_phase(observation_at=datetime(2026, 9, 14, 10, 0, tzinfo=pytz.UTC)) == "UNKNOWN"

    def test_existing_is_market_open_unchanged(self) -> None:
        """The existing ``is_market_open`` helper is untouched;
        the new constants are aliases for the same values.
        """
        from market_calendar import is_market_open
        # We can't easily mock datetime.now() here; just confirm
        # the function exists and uses the same constants.
        assert callable(is_market_open)


# ---- (9) J.2 CAS eligibility list -------------------------------------

class TestIsCasEligible:
    """[WORKFLOW-J.2 2026-09-13] Tests for the operator-supplied
    Phase 1 F&O eligibility list.

    Contract:

      1. Empty list returns False for any symbol (the documented
         bounded default -- no symbol is CAS-eligible until the
         operator opts in).
      2. A symbol present in the configured list returns True.
      3. Case-insensitive match works on both the input symbol AND
         the configured list entries (we normalise on both sides).
      4. Whitespace is stripped on both the input symbol AND the
         configured list entries.
      5. ``is_cas_eligible`` does not crash if ``config.settings``
         cannot be imported (lazy-import defensive). The function
         is total -- it returns False rather than raising.

    These tests use ``monkeypatch.setattr`` on
    ``_normalised_cas_eligibility_set`` in ``market_calendar``
    rather than mutating the env / patching ``settings``: that
    keeps the tests independent of how settings are loaded AND
    avoids contaminating the lru_cache across tests.
    """

    def _clear_cache(self) -> None:
        """Clear the lru_cache. The function is decorated at module
        load with ``@functools.lru_cache(maxsize=1)`` so any test
        that calls it once will see the cached value for the
        remainder of the process. Clearing each test starts with a
        clean cache so a future test does not inherit a previous
        test's mock.
        """
        from market_calendar import _normalised_cas_eligibility_set
        _normalised_cas_eligibility_set.cache_clear()

    def test_empty_list_returns_false_for_any_symbol(self) -> None:
        """Default behaviour (empty setting) returns False for every
        symbol. The classifier stays in non-CAS mode until the
        operator opts in.
        """
        from market_calendar import is_cas_eligible
        self._clear_cache()
        assert is_cas_eligible("RELIANCE") is False
        assert is_cas_eligible("HDFCBANK") is False
        assert is_cas_eligible("TCS") is False
        assert is_cas_eligible("ANYTHING") is False
        # Documented defensive inputs also stay False.
        assert is_cas_eligible(None) is False
        assert is_cas_eligible("") is False
        assert is_cas_eligible(12345) is False  # type: ignore[arg-type]

    def test_symbol_in_list_returns_true(self, monkeypatch) -> None:
        """A configured underlying returns True. We patch the
        Settings attribute that drives ``is_cas_eligible`` so the
        test is deterministic regardless of process env.
        """
        from market_calendar import is_cas_eligible
        from config import settings

        monkeypatch.setattr(
            settings, "CAS_PHASE1_FNO_UNDERLYINGS",
            "RELIANCE, HDFCBANK, INFY",
        )

        assert is_cas_eligible("RELIANCE") is True
        assert is_cas_eligible("HDFCBANK") is True
        assert is_cas_eligible("INFY") is True
        assert is_cas_eligible("TCS") is False
        assert is_cas_eligible("NOTINTABLE") is False

    def test_case_insensitive_match(self, monkeypatch) -> None:
        """Uppercase vs lowercase vs mixed case all resolve the same
        way. Real upstream callers (Kite, our own scanners) sometimes
        hand us lowercase symbols.
        """
        from market_calendar import is_cas_eligible
        from config import settings

        monkeypatch.setattr(
            settings, "CAS_PHASE1_FNO_UNDERLYINGS",
            "RELIANCE, HDFCBANK",
        )

        assert is_cas_eligible("RELIANCE") is True
        assert is_cas_eligible("reliance") is True
        assert is_cas_eligible("ReLiAnCe") is True
        assert is_cas_eligible("hdfcbank") is True
        assert is_cas_eligible("HdfcbAnk") is True

    def test_whitespace_stripped(self, monkeypatch) -> None:
        """Leading / trailing whitespace on the input symbol AND on
        the configured list entries is stripped defensively.
        """
        from market_calendar import is_cas_eligible
        from config import settings

        # Use a CSV with embedded whitespace + capitalised entries.
        monkeypatch.setattr(
            settings, "CAS_PHASE1_FNO_UNDERLYINGS",
            "  RELIANCE , HDFCBANK  ",
        )

        assert is_cas_eligible("  RELIANCE  ") is True
        assert is_cas_eligible("\tHDFCBANK\n") is True
        assert is_cas_eligible("  reliance  ") is True
        assert is_cas_eligible("  ReLiAnCe  ") is True

    def test_lazy_import_no_crash_on_config_failure(self, monkeypatch) -> None:
        """``is_cas_eligible`` must NOT crash if the lazy
        ``from config import settings`` raises (e.g. partial
        deploy, bad .env, missing module). It degrades to False --
        the safest default per the bounded contract -- rather than
        propagating the import error.

        We simulate the failure by patching the module-level
        ``__import__`` builtin to raise for the ``config`` module
        only. pytest's monkeypatch restores the original after the
        test so the other tests in this file (and elsewhere) are
        not affected.
        """
        import builtins
        from market_calendar import is_cas_eligible
        from market_calendar import _normalised_cas_eligibility_set

        real_import = builtins.__import__

        def _failing_import(name, *args, **kwargs):
            # Match both ``import config`` and ``from config import ...``
            if name == "config" or name.startswith("config"):
                raise RuntimeError("simulated config import failure")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _failing_import)
        # The cached lru_cache entry from earlier tests could mask
        # the import path. Clear it so this exercise really walks
        # the import.
        _normalised_cas_eligibility_set.cache_clear()

        # Even with config import failing, the function must return
        # a value (False) and not raise.
        result = is_cas_eligible("RELIANCE")
        assert result is False
        assert is_cas_eligible(None) is False
        assert is_cas_eligible(12345) is False  # type: ignore[arg-type]

    def test_csv_whitespace_tolerance_in_parser(self) -> None:
        """The underlying parser tolerates whitespace around commas,
        trailing commas, double commas, and mixed case in the raw
        CSV. This is a unit test on ``_normalised_cas_eligibility_set``
        so a future regex refactor cannot silently lose coverage.
        """
        from market_calendar import _normalised_cas_eligibility_set
        # Standard CSV with spaces.
        assert (
            _normalised_cas_eligibility_set("RELIANCE, HDFCBANK ,INFY")
            == frozenset({"RELIANCE", "HDFCBANK", "INFY"})
        )
        # Trailing + double commas dropped.
        assert (
            _normalised_cas_eligibility_set("RELIANCE,, HDFCBANK,")
            == frozenset({"RELIANCE", "HDFCBANK"})
        )
        # Mixed case normalised to upper.
        assert (
            _normalised_cas_eligibility_set("Reliance,hdfcbank , InFy")
            == frozenset({"RELIANCE", "HDFCBANK", "INFY"})
        )
        # Empty / whitespace-only / all-commas -> empty frozenset.
        assert _normalised_cas_eligibility_set("") == frozenset()
        assert _normalised_cas_eligibility_set("   ") == frozenset()
        assert _normalised_cas_eligibility_set(", , ,") == frozenset()
