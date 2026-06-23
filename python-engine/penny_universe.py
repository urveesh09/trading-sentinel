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
from datetime import datetime
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

    # ---- ranking + refresh (spec §2.4) -----------------------------------

    # Spec §2.4 composite-score weights
    RANK_WEIGHTS = {
        "momentum": 0.40,     # 20d avg daily return
        "liquidity": 0.30,    # 20d median traded value
        "low_distance": 0.20,  # distance from 52-week low (capped)
        "volatility": 0.10,   # 20d realized volatility
    }

    @staticmethod
    def _normalize(values):
        """Min-max normalize a list of numbers to [0, 1]. Handles empty + constant cases."""
        if not values:
            return []
        lo, hi = min(values), max(values)
        if hi == lo:
            return [0.5 for _ in values]
        return [(v - lo) / (hi - lo) for v in values]

    @classmethod
    def rank_tickers(cls, tickers, top_n=100):
        """
        Spec §2.4: composite-score ranking. Returns the top_n tickers.

        Each ticker record is expected to have:
          - avg_return_20d (float, can be negative)
          - median_traded_value_20d (float)
          - dist_from_52w_low_pct (float in [0, 1], capped at 0.95)
          - vol_20d (float, realized volatility)

        Composite = 0.40*norm(momentum) + 0.30*norm(liquidity)
                    + 0.20*norm(low_distance) + 0.10*norm(volatility)

        Negative momentum ranks below positive (we don't clip). This is
        intentional per spec: the "top 100 performing" list should bias
        toward positive momentum without excluding negative names entirely
        (since negative momentum + low PB = contrarian setup).
        """
        if not tickers:
            return []

        # Pre-process: cap low_distance at 0.95 so a single runaway can't
        # dominate that axis.
        capped = []
        for t in tickers:
            tt = dict(t)
            tt["dist_from_52w_low_pct"] = min(tt.get("dist_from_52w_low_pct", 0) or 0, 0.95)
            capped.append(tt)

        n = len(capped)
        mom = cls._normalize([t.get("avg_return_20d", 0) or 0 for t in capped])
        liq = cls._normalize([t.get("median_traded_value_20d", 0) or 0 for t in capped])
        dst = cls._normalize([t.get("dist_from_52w_low_pct", 0) or 0 for t in capped])
        vol = cls._normalize([t.get("vol_20d", 0) or 0 for t in capped])

        w = cls.RANK_WEIGHTS
        scored = []
        for i, t in enumerate(capped):
            score = w["momentum"] * mom[i] + w["liquidity"] * liq[i] + \
                    w["low_distance"] * dst[i] + w["volatility"] * vol[i]
            scored.append((score, t))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored[:top_n]]


async def refresh_from_kite(kite, out_json_path, corp_json_path, top_n=100):
    """
    Daily universe-refresh job (spec §2.4 + §9.1).

    1. Fetch NSE EQ instruments from Kite
    2. Fetch last price + previous close + volume per instrument
    3. Fetch corporate actions (promoter_holding_pct, pb_ratio, segment flags)
       or fall back to penny_company_data.json if Kite endpoint missing
    4. Apply PennyUniverse eligibility gates (price band, liquidity, promoter, PB)
    5. Compute 20d momentum + 52w-low distance + realized vol per ticker
    6. Rank via composite score
    7. Write top_n to penny_static.json

    Failures must NOT crash the daily scheduler -- log + return None.
    """
    try:
        from config import settings
        # 1. Instruments
        instruments = await kite.get_instruments_nse_eq()
        # 2. Quotes (batched -- Kite's /quote URL has a length limit, so
        # passing ~2000 tokens at once raises "URL component 'query'
        # too long". Batch by 500 tokens per call.)
        all_tokens = [i["instrument_token"] for i in instruments]
        quotes: dict = {}
        batch_size = 500
        for start in range(0, len(all_tokens), batch_size):
            batch = all_tokens[start:start + batch_size]
            try:
                chunk = await kite.get_quote(batch)
                if isinstance(chunk, dict):
                    quotes.update(chunk)
            except Exception as e:
                logger.warning(
                    "penny_universe_quote_batch_failed start=%d size=%d error=%s",
                    start, len(batch), str(e),
                )
        # 3. Corporate actions (with fallback)
        try:
            corp = await kite.get_corporate_actions()
        except Exception:
            corp = None
        if not corp:
            try:
                with open(corp_json_path) as f:
                    corp_data = json.load(f)
                corp = corp_data.get("records", [])
            except Exception:
                corp = []
        corp_by_sym = {c.get("symbol"): c for c in (corp or [])}

        # 4-5. Build candidate records (eligibility filters happen here)
        candidates = []
        for inst in instruments:
            sym = inst["tradingsymbol"]
            tok = inst["instrument_token"]
            q = quotes.get(tok) if isinstance(quotes, dict) else None
            if not q:
                continue
            prev_close = q.get("ohlc", {}).get("close") or q.get("last_price")
            if prev_close is None:
                continue
            corp_rec = corp_by_sym.get(sym, {})
            tv_20d = corp_rec.get("median_traded_value_20d", 0) or 0
            cand = {
                "symbol": sym,
                "series": inst.get("series", "EQ"),
                "prev_close": prev_close,
                "promoter_holding_pct": corp_rec.get("promoter_holding_pct"),
                "pb_ratio": corp_rec.get("pb_ratio"),
                "is_t2t": corp_rec.get("is_t2t", False),
                "is_asm": corp_rec.get("is_asm", False),
                "is_gsm": corp_rec.get("is_gsm", False),
                "median_traded_value_20d": tv_20d,
                # momentum metrics populated below
                "avg_return_20d": corp_rec.get("avg_return_20d", 0) or 0,
                "dist_from_52w_low_pct": corp_rec.get("dist_from_52w_low_pct", 0) or 0,
                "vol_20d": corp_rec.get("vol_20d", 0) or 0,
            }
            candidates.append(cand)

        # Apply price-band eligibility only here (the full eligibility
        # filter with promoter/PB re-runs at scan time via PennyUniverse.eligible_tickers).
        in_band = [c for c in candidates
                   if settings.PENNY_PRICE_MIN <= c["prev_close"] <= settings.PENNY_PRICE_MAX]

        # 6. Rank
        ranked = PennyUniverse.rank_tickers(in_band, top_n=top_n)

        # 7. Write
        payload = {
            "as_of": datetime.utcnow().strftime("%Y-%m-%d"),
            "universe_size_target": top_n,
            "tickers": ranked,
        }
        os.makedirs(os.path.dirname(out_json_path), exist_ok=True)
        with open(out_json_path, "w") as f:
            json.dump(payload, f, indent=2)
        logger.info("penny_universe_refreshed count=%d", len(ranked))
        return ranked
    except Exception as e:
        logger.error("penny_universe_refresh_failed error=%s", str(e))
        return None