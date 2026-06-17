"""Static Nifty 100 ticker universe loader with cache.

Loads a JSON file of Nifty 100 symbols, resolves each to a Kite instrument
token via an injected ``instrument_cache`` dict, and exposes the resolved
set. Fails fast on bad JSON; warns (does not raise) on individual symbols
that can't be resolved in the cache.
"""
import json
import logging
import os
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)


class UniverseError(Exception):
    """Raised when the Nifty 100 universe JSON is missing, malformed, or invalid."""


class Universe:
    """Loads the Nifty 100 ticker list from a static JSON file and resolves
    Kite instrument tokens at construction time. Caches the result in-memory.

    The ``instrument_cache`` dict is injected (not imported) so this module
    has no dependency on a live KiteClient instance. Production callers pass
    ``kite_client.KiteClient().instrument_cache``; tests pass a fixture dict.
    """

    def __init__(self, json_path: str, instrument_cache: Optional[Dict[str, int]] = None):
        self._tokens: Set[int] = set()
        self._token_to_symbol: Dict[int, str] = {}
        cache = instrument_cache if instrument_cache is not None else {}
        self._load(json_path, cache)

    def _load(self, json_path: str, instrument_cache: Dict[str, int]) -> None:
        """Read JSON, validate schema, resolve tokens. Fail-fast on bad data."""
        if not os.path.exists(json_path):
            raise UniverseError(f"Nifty 100 JSON not found at {json_path}")

        try:
            with open(json_path) as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise UniverseError(f"Nifty 100 JSON is malformed: {e}") from e

        if "tickers" not in data or not isinstance(data["tickers"], list):
            raise UniverseError("Nifty 100 JSON missing 'tickers' array")

        resolved = 0
        missing = []
        for entry in data["tickers"]:
            symbol = entry.get("symbol") if isinstance(entry, dict) else None
            if not symbol:
                continue
            token = instrument_cache.get(symbol)
            if token is None:
                missing.append(symbol)
                continue
            self._tokens.add(token)
            self._token_to_symbol[token] = symbol
            resolved += 1

        if missing:
            logger.warning(
                f"Universe: {len(missing)} symbols unresolvable in Kite cache, "
                f"excluded from breadth: {missing[:5]}{'...' if len(missing) > 5 else ''}"
            )
        logger.info(f"Universe loaded: {resolved} tokens from {len(data['tickers'])} entries")

    def get_nifty100_tokens(self) -> Set[int]:
        """Return the resolved Nifty 100 instrument tokens. Cached after first call."""
        return self._tokens.copy()

    def token_to_symbol(self, token: int) -> Optional[str]:
        """Reverse lookup: instrument_token -> NSE symbol."""
        return self._token_to_symbol.get(token)
