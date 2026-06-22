"""
[PENNY-UNIVERSE 2026-06-21] Penny-stock universe loader + eligibility filter.

Mirrors the structure of universe.py but is owned by the penny subsystem.
Loads a JSON file of penny candidates, validates each ticker against the
spec §2.3 eligibility gates, resolves to Kite instrument tokens via an
injected instrument_cache dict, and exposes the eligible set.

Hard architectural rule (enforced by tests/test_penny_isolation.py):
  this module MUST NOT import from engine, regime, risk_engine, portfolio,
  evaluate_signal, or evaluate_momentum_signal.

Allowed shared imports: kite_client, models (base only), config,
position_tracker, performance, analytics, stdlib.
"""
import json
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class UniverseError(Exception):
    """Raised when the penny JSON is missing, malformed, or invalid."""


class PennyUniverse:
    """
    Loads the penny ticker list from a static JSON file and applies
    spec §2.3 eligibility filters at construction time. Caches the
    result in-memory.

    instrument_cache is injected (not imported) so this module has no
    dependency on a live KiteClient instance. Production callers pass
    kite_client.KiteClient().instrument_cache; tests pass a fixture dict.
    """

    def __init__(self, json_path: str, instrument_cache: Optional[Dict[str, int]] = None):
        cache = instrument_cache if instrument_cache is not None else {}
        self._all_tickers: List[dict] = []
        self._tokens: set = set()
        self._token_to_symbol: Dict[int, str] = {}
        self._symbol_to_token: Dict[str, int] = {}
        self._load(json_path, cache)

    def _load(self, json_path: str, instrument_cache: Dict[str, int]) -> None:
        if not os.path.exists(json_path):
            raise UniverseError(f"penny JSON not found at {json_path}")
        try:
            with open(json_path) as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise UniverseError(f"penny JSON is malformed: {e}") from e

        if "tickers" not in data or not isinstance(data["tickers"], list):
            raise UniverseError("penny JSON missing 'tickers' array")

        self._all_tickers = data["tickers"]
        missing = []
        for t in self._all_tickers:
            sym = t.get("symbol")
            tok = instrument_cache.get(sym)
            if tok is not None:
                self._tokens.add(tok)
                self._token_to_symbol[tok] = sym
                self._symbol_to_token[sym] = tok
            else:
                missing.append(sym)
        if missing:
            logger.warning(
                "penny_universe_tokens_unresolved count=%d sample=%s",
                len(missing),
                missing[:5],
            )

    @property
    def size(self) -> int:
        return len(self._all_tickers)

    @property
    def tokens(self) -> set:
        return set(self._tokens)

    def token_to_symbol(self, token: int) -> Optional[str]:
        return self._token_to_symbol.get(token)

    def symbol_to_token(self, symbol: str) -> Optional[int]:
        return self._symbol_to_token.get(symbol)

    def eligible_tickers(self) -> List[dict]:
        """
        Apply spec §2.3 eligibility gates and return the surviving
        ticker records (unranked; ranking is in the refresh job).
        """
        from config import settings
        out = []
        for t in self._all_tickers:
            sym = t.get("symbol")
            if sym not in self._symbol_to_token:
                continue  # not resolvable; skip

            # Series gate: EQ only
            if t.get("series") != "EQ":
                continue

            # Price band gate (using prev_close as proxy at refresh time)
            pc = t.get("prev_close")
            if pc is None or pc < settings.PENNY_PRICE_MIN or pc > settings.PENNY_PRICE_MAX:
                continue

            # Liquidity gate
            tv = t.get("median_traded_value_20d", 0) or 0
            if tv < settings.PENNY_MIN_20D_TV:
                continue

            # Segment gates
            if t.get("is_t2t"):
                continue
            if t.get("is_asm"):
                continue
            if t.get("is_gsm"):
                continue

            # Promoter gate: strictly > 25% AND strictly < 75%.
            # Storage convention: universe JSON stores promoter_holding_pct
            # as a percentage (0-100). Settings store the threshold as a
            # fraction (0-1) for human readability ("0.75" is easier to read
            # than "75.0"). Convert settings to percent at compare time.
            prom = t.get("promoter_holding_pct")
            if prom is None:
                continue
            if prom <= settings.PENNY_MIN_PROMOTER_HOLD * 100:
                continue
            if prom >= settings.PENNY_MAX_PROMOTER_HOLD * 100:
                continue

            # P/B gate: <= 2.0
            pb = t.get("pb_ratio")
            if pb is None or pb > settings.PENNY_MAX_PB_RATIO:
                continue

            out.append(t)
        return out