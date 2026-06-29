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
        self._as_of: Optional[str] = None  # [AUDIT-FIX-2.4]
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

        # [AUDIT-FIX-2.4 2026-06-25] Capture as_of for staleness checks.
        # Pre-fix the universe JSON's as_of was ignored, so a stale
        # refresh (e.g. last refresh 3 days ago over a long weekend)
        # silently fed the scanner old data. Now we log a WARNING if
        # as_of is older than 1 day AND expose as_of via .as_of for
        # callers (the scanner can surface staleness in hourly reports).
        #
        # We do NOT refuse to load -- the operator-mandated constraint
        # is "don't block the system during market hours". Even a 7-day-
        # old universe is better than no scanner at all. We just make
        # the staleness LOUD so the operator fixes the refresh job.
        self._as_of = data.get("as_of")
        if self._as_of:
            try:
                from datetime import date, datetime as _dt
                as_of_date = _dt.strptime(self._as_of, "%Y-%m-%d").date()
                today = date.today()
                age_days = (today - as_of_date).days
                if age_days > 1:
                    logger.warning(
                        "penny_universe_stale as_of=%s age_days=%d "
                        "FIX=run run_penny_universe_refresh() (scheduled 08:00 IST). "
                        "Scanner continues with stale data; signals may "
                        "miss fresh eligibility changes.",
                        self._as_of, age_days,
                    )
                elif age_days < 0:
                    # as_of in the future -- clock skew or manual edit.
                    logger.warning(
                        "penny_universe_as_of_in_future as_of=%s "
                        "(clock skew or manual edit; treating as fresh)",
                        self._as_of,
                    )
            except ValueError:
                logger.warning(
                    "penny_universe_as_of_unparseable as_of=%r "
                    "(expected YYYY-MM-DD)",
                    self._as_of,
                )
        else:
            logger.warning(
                "penny_universe_no_as_of "
                "FIX=regenerate penny_static.json (regen writes as_of=YYYY-MM-DD)"
            )

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

    @property
    def as_of(self) -> Optional[str]:
        """[AUDIT-FIX-2.4] Returns the as_of date from the universe JSON
        (YYYY-MM-DD), or None if the JSON doesn't have one. Callers
        (e.g. the hourly report) can surface this to surface staleness
        without re-parsing the file."""
        return self._as_of

    @property
    def age_days(self) -> Optional[int]:
        """[AUDIT-FIX-2.4] Days since the universe JSON was refreshed.
        None if as_of is missing or unparseable. Negative if as_of is
        in the future (clock skew)."""
        if not self._as_of:
            return None
        try:
            from datetime import date, datetime as _dt
            as_of_date = _dt.strptime(self._as_of, "%Y-%m-%d").date()
            return (date.today() - as_of_date).days
        except ValueError:
            return None

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


async def compute_metrics_from_history(kite, symbols, lookback_days: int = 30) -> Dict[str, dict]:
    """
    [PENNY-CORP-FALLBACK 2026-06-26] Compute the four corp-data metrics the
    universe needs (median_traded_value_20d, avg_return_20d, vol_20d,
    dist_from_52w_low_pct) directly from Kite's daily history per ticker.

    Why this exists
    ---------------
    `KiteClient.get_corporate_actions()` always returns [] -- Kite Connect
    does not expose a corporate-actions / fundamental-data endpoint. The
    refresh job's fallback path (`penny_company_data.json`) only works if a
    human-curated file is on disk; in the container it does not exist.
    Result: median_traded_value_20d has been 0 for every ticker, the
    eligibility liquidity gate kills all 100, and the scanner produces
    0 signals every day (see 2026-06-26 incident).

    This helper fills those fields from daily history, which IS available
    via kite.get_historical. One round-trip per ticker; Kite self-throttles
    at 3 req/s and the call is SQLite-cached, so the 08:00 IST daily refresh
    pays ~30s on day 1 and is essentially free from day 2 onwards.

    Metrics
    -------
      median_traded_value_20d : median(close * volume) over the trailing
        `lookback_days` calendar days of daily bars. In Rs (NOT crore).
        Liquidity gate compares this against PENNY_MIN_20D_TV.
      avg_return_20d          : mean of daily log returns over the same
        window. Used by the ranker's momentum weight (40%).
      vol_20d                 : stddev of daily log returns. Used by the
        ranker's volatility weight (10%).
      dist_from_52w_low_pct   : (last_close - 52w_low) / 52w_low, capped
        at 0.95 so far-from-low names don't dominate the ranker. Used by
        the ranker's low_distance weight (10%). Requires ~250 daily bars;
        if the window doesn't reach back that far we approximate with the
        full available history (capped lower bound).

    Returns
    -------
    Dict[str, dict] keyed by tradingsymbol. Each value has the four
    fields above plus a `bars_used` counter for observability. Symbols
    whose get_historical call returns empty / raises / has < 10 bars are
    omitted entirely -- the caller treats that as "no data" and falls
    back to the (existing) null-tolerance path in the eligibility filter.

    Failures
    --------
    Per-symbol errors are swallowed and logged at WARNING. A single bad
    ticker never blocks the others. The whole function never raises;
    callers can treat an empty dict the same as "no fallback data".
    """
    from datetime import timedelta

    if not symbols:
        return {}

    to_date = datetime.utcnow().strftime("%Y-%m-%d")
    # Fetch a bit more than lookback_days so we always have 20+ bars even
    # with weekends / holidays in the window.
    from_date = (datetime.utcnow() - timedelta(days=lookback_days + 10)).strftime("%Y-%m-%d")
    # For the 52w-low we want a longer history window; do a second pass.
    from_52w = (datetime.utcnow() - timedelta(days=370)).strftime("%Y-%m-%d")

    out: Dict[str, dict] = {}
    skipped: List[str] = []
    for sym in symbols:
        try:
            df = await kite.get_historical(sym, from_date, to_date)
        except Exception as e:
            logger.warning(
                "penny_metrics_history_fetch_failed symbol=%s error=%s",
                sym, str(e),
            )
            skipped.append(sym)
            continue
        if df is None or df.empty or len(df) < 10:
            skipped.append(sym)
            continue
        try:
            # Sort by date ascending (Kite's cache may not guarantee order
            # if rows were inserted out of band by an earlier bug).
            df = df.sort_index()
            close = df["close"].astype(float)
            volume = df["volume"].astype(float)
            traded_value = close * volume
            tv_20d = float(traded_value.tail(20).median())
            log_ret = (close / close.shift(1)).dropna().apply(
                lambda x: float(x) if x > 0 else float("nan")
            ).dropna()
            if len(log_ret) >= 2:
                avg_ret_20d = float(log_ret.tail(20).mean())
                vol_20d = float(log_ret.tail(20).std(ddof=0))
            else:
                avg_ret_20d = 0.0
                vol_20d = 0.0
            # 52w-low distance: best-effort with the longer window.
            try:
                df_long = await kite.get_historical(sym, from_52w, to_date)
                if df_long is not None and not df_long.empty and len(df_long) >= 10:
                    low_52w = float(df_long["low"].astype(float).min())
                    last_close = float(close.iloc[-1])
                    if low_52w > 0:
                        dist = (last_close - low_52w) / low_52w
                        # Cap at 0.95 per the ranker convention.
                        dist_52w = float(min(max(dist, 0.0), 0.95))
                    else:
                        dist_52w = 0.0
                else:
                    dist_52w = 0.0
            except Exception:
                dist_52w = 0.0
            out[sym] = {
                "median_traded_value_20d": tv_20d,
                "avg_return_20d": avg_ret_20d,
                "vol_20d": vol_20d,
                "dist_from_52w_low_pct": dist_52w,
                "bars_used": int(len(df)),
            }
        except Exception as e:
            logger.warning(
                "penny_metrics_compute_failed symbol=%s error=%s",
                sym, str(e),
            )
            skipped.append(sym)
            continue
    if skipped:
        logger.info(
            "penny_metrics_history_skipped count=%d sample=%s",
            len(skipped), skipped[:5],
        )
    logger.info(
        "penny_metrics_history_computed count=%d skipped=%d lookback_days=%d",
        len(out), len(skipped), lookback_days,
    )
    return out


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

        # [PENNY-CORP-FALLBACK 2026-06-26] If the corp-data source is
        # empty/missing, derive the four numeric metrics from Kite's daily
        # history per symbol. This unblocks the eligibility liquidity gate
        # (PENNY_MIN_20D_TV) which has been killing every ticker with tv=0.
        # Pre-existing fields from `corp_by_sym` are NOT overwritten --
        # history-derived values only fill where the corp record is missing
        # the field. See docs/deviations/2026-06-26-penny-corp-from-history.md
        symbols_for_metrics = [inst["tradingsymbol"] for inst in instruments]
        try:
            history_metrics = await compute_metrics_from_history(kite, symbols_for_metrics)
        except Exception as e:
            logger.warning(
                "penny_metrics_history_failed error=%s -- continuing with corp-only data",
                str(e),
            )
            history_metrics = {}
        if history_metrics:
            for sym, hm in history_metrics.items():
                rec = corp_by_sym.setdefault(sym, {})
                for k in ("median_traded_value_20d", "avg_return_20d",
                          "vol_20d", "dist_from_52w_low_pct"):
                    if rec.get(k) in (None, 0) and hm.get(k) is not None:
                        rec[k] = hm[k]
            logger.info(
                "penny_metrics_history_applied symbols=%d (filled missing corp fields)",
                len(history_metrics),
            )

        # 4-5. Build candidate records (eligibility filters happen here)
        # [PENNY-SEGMENT-FILTER 2026-06-26] Reject NSE non-EQ segments
        # (SME = "-SM"/"-ST" suffix, BE = "-BE", BZ = "-BZ", etc.). The
        # Kite filter in kite_client.get_instruments_nse_eq() relies on
        # `instrument_type=="EQ"` returning only the standard NSE EQ
        # series, but in practice some SME/BE symbols surface with
        # instrument_type=EQ in certain Kite responses -- leaving the
        # universe full of un-tokenisable tickers and the scanner
        # producing 0/0/0 forever. Defence in depth: also reject by
        # tradingsymbol suffix here so the refresh cannot accidentally
        # pick up non-standard segments regardless of Kite behaviour.
        # Counter is logged so the operator can see the leak size.
        sm_be_rejected = 0
        candidates = []
        for inst in instruments:
            sym = inst["tradingsymbol"]
            tok = inst["instrument_token"]
            q = quotes.get(tok) if isinstance(quotes, dict) else None
            if not q:
                continue
            # Standard NSE EQ segments: EQ only. Anything else (SM, BE,
            # BZ, IL, GS) is a non-standard series; reject.
            series = (inst.get("series") or "EQ").upper()
            if series != "EQ":
                sm_be_rejected += 1
                continue
            # Belt-and-braces: some Kite responses report series=EQ for
            # SME tickers too. Filter by tradingsymbol suffix as well.
            for bad_suffix in ("-SM", "-ST", "-BE", "-BZ", "-IL", "-GS"):
                if sym.endswith(bad_suffix):
                    sm_be_rejected += 1
                    break
            else:
                prev_close = q.get("ohlc", {}).get("close") or q.get("last_price")
                if prev_close is None:
                    continue
                corp_rec = corp_by_sym.get(sym, {})
                tv_20d = corp_rec.get("median_traded_value_20d", 0) or 0
                cand = {
                    "symbol": sym,
                    "series": series,
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
        if sm_be_rejected:
            logger.info(
                "penny_universe_segment_filtered count=%d "
                "(rejected NSE non-EQ series: SM/BE/ST/BZ/IL/GS)",
                sm_be_rejected,
            )

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