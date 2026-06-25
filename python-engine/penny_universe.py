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

        Null-tolerant (2026-06-25 deviation): when promoter_holding_pct or
        pb_ratio is missing from the universe record (Kite corp-data
        endpoint empty + no fallback file), the ticker is NOT silently
        dropped. Instead, it passes with a `data_quality` flag set so the
        operator can see degraded universe quality in the pre-market
        digest and the hourly report. Hard rejects (real promoter > 75%,
        real PB > 2.0) still apply when data IS available.

        Rationale: spec §2.3 promoter + PB gates are about avoiding
        shell / promoter-heavy / distressed names. The intent is
        preserved when data is present; when data is missing, downstream
        gates (volume surge 3x median, RS breakout, RSI<70) still filter
        to high-conviction setups, and the per-trade risk caps
        (Rs 500/stock, 5 positions, 5%/trade) limit damage if a
        low-quality name sneaks through.
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
            #
            # Null tolerance (2026-06-25): missing promoter data is
            # tagged `data_quality=DEGRADED_promoter_missing` rather than
            # dropping the ticker. Hard rejects still apply when present.
            prom = t.get("promoter_holding_pct")
            data_quality_flags = []
            if prom is None:
                data_quality_flags.append("promoter_missing")
            else:
                if prom <= settings.PENNY_MIN_PROMOTER_HOLD * 100:
                    continue
                if prom >= settings.PENNY_MAX_PROMOTER_HOLD * 100:
                    continue

            # P/B gate: <= 2.0 (null tolerance mirrors promoter above)
            pb = t.get("pb_ratio")
            if pb is None:
                data_quality_flags.append("pb_missing")
            else:
                if pb > settings.PENNY_MAX_PB_RATIO:
                    continue

            # Tag the record with quality flags so downstream observers
            # (pre-market digest, hourly report) can surface degradation.
            if data_quality_flags:
                t = dict(t)  # do not mutate the cached dict
                t["data_quality"] = "DEGRADED:" + ",".join(data_quality_flags)
            out.append(t)
        return out

    def quality_audit(self) -> dict:
        """
        Summarise data quality of the currently loaded universe.
        Returns counts of tickers with null / missing fields that the
        eligibility filter would have used pre-2026-06-25 deviation.

        Used by the daily refresh job to log
        `penny_universe_quality_audit` and by the hourly report to
        surface degraded-universe warnings.
        """
        total = len(self._all_tickers)
        null_promoter = 0
        null_pb = 0
        null_tv = 0
        null_pc = 0
        for t in self._all_tickers:
            if t.get("promoter_holding_pct") is None:
                null_promoter += 1
            if t.get("pb_ratio") is None:
                null_pb += 1
            if not t.get("median_traded_value_20d"):
                null_tv += 1
            if t.get("prev_close") is None:
                null_pc += 1
        return {
            "total": total,
            "null_promoter": null_promoter,
            "null_pb": null_pb,
            "null_tv": null_tv,
            "null_pc": null_pc,
            "degraded_pct": round(
                100.0 * max(null_promoter, null_pb) / max(total, 1), 1
            ),
        }

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
    8. Emit penny_universe_quality_audit (2026-06-25) so operators can
       see degraded-universe conditions without waiting for the hourly
       report to surface them.

    Failures must NOT crash the daily scheduler -- log + return None.
    """
    try:
        from config import settings
        # 1. Instruments
        instruments = await kite.get_instruments_nse_eq()
        # 2. Quotes (batched -- Kite's /quote URL has a length limit, so
        # passing ~2000 tokens at once raises "URL component 'query'
        # too long". Batch by 500 tokens per call.)
        #
        # If ALL batches return empty (e.g., Kite outage, network
        # failure during peak hours), do NOT overwrite the existing
        # penny_static.json with an empty universe. The scanner will
        # keep using the previous file until next refresh.
        all_tokens = [i["instrument_token"] for i in instruments]
        quotes: dict = {}
        failed_batches = 0
        total_batches = 0
        batch_size = 500
        for start in range(0, len(all_tokens), batch_size):
            total_batches += 1
            batch = all_tokens[start:start + batch_size]
            try:
                chunk = await kite.get_quote(batch)
                if isinstance(chunk, dict) and chunk:
                    quotes.update(chunk)
                else:
                    failed_batches += 1
                    logger.warning(
                        "penny_universe_quote_batch_empty start=%d size=%d",
                        start, len(batch),
                    )
            except Exception as e:
                failed_batches += 1
                logger.warning(
                    "penny_universe_quote_batch_failed start=%d size=%d error=%s",
                    start, len(batch), str(e),
                )
        if total_batches > 0 and failed_batches == total_batches:
            # All batches failed -- do NOT overwrite the universe file
            # with empty data. Caller will see this and skip writing.
            logger.error(
                "penny_universe_quote_all_batches_failed count=%d -- aborting refresh",
                total_batches,
            )
            return None
        if not quotes:
            logger.warning(
                "penny_universe_quote_empty total_batches=%d -- continuing with empty quote set",
                total_batches,
            )
        # 3. Corporate actions (with fallback)
        corp_source = "kite"  # tracked for audit logging
        try:
            corp = await kite.get_corporate_actions()
        except Exception:
            corp = None
        if not corp:
            try:
                with open(corp_json_path) as f:
                    corp_data = json.load(f)
                corp = corp_data.get("records", [])
                corp_source = "fallback_file"
            except Exception:
                corp = []
                corp_source = "missing"
        if corp_source == "missing":
            logger.warning(
                "penny_corp_data_missing kite=empty fallback_file=%s -- "
                "universe will have null promoter_holding_pct and pb_ratio "
                "(eligibility filter is now null-tolerant, see deviation "
                "2026-06-25-penny-eligibility-null-tolerance.md)",
                corp_json_path,
            )
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

        # 8. Quality audit (2026-06-25): write a temporary PennyUniverse
        # instance just to compute the audit (avoids re-reading the file
        # after we just wrote it; uses the in-memory `ranked` list).
        try:
            audit_universe = PennyUniverse.__new__(PennyUniverse)
            audit_universe._all_tickers = ranked
            audit_universe._tokens = set()
            audit_universe._token_to_symbol = {}
            audit_universe._symbol_to_token = {}
            audit = audit_universe.quality_audit()
            audit["corp_source"] = corp_source
            logger.info(
                "penny_universe_quality_audit "
                "total=%d null_promoter=%d null_pb=%d null_tv=%d "
                "null_pc=%d degraded_pct=%.1f corp_source=%s",
                audit["total"], audit["null_promoter"], audit["null_pb"],
                audit["null_tv"], audit["null_pc"], audit["degraded_pct"],
                corp_source,
            )
        except Exception as e:
            logger.warning("penny_universe_quality_audit_failed error=%s", str(e))

        return ranked
    except Exception as e:
        logger.error("penny_universe_refresh_failed error=%s", str(e))
        return None