"""Two-tier market-breadth computation engine.

Tier 1 (hourly): fetches 60-day daily history for the Nifty 100 universe,
computes SMA50 and signed distance_pct per stock, caches the result with a
1-hour stale-while-revalidate window.

Tier 2 (per-scan): uses the scan pass's live LTP + cached SMA50 to refresh
breadth_pct_above_sma50 and per-stock rank. Zero Kite calls.

Both tiers return a BreadthResult. When Tier 1 fails on more than
``degraded_threshold`` of fetches, returns a degraded result (breadth_pct=None,
rank_map={}).
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Set

import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class BreadthResult:
    """Output of BreadthEngine.compute_tier1() and compute_tier2()."""
    breadth_pct_above_sma50: Optional[float]
    rank_map: Dict[int, float]            # token -> 0.0..1.0 percentile rank
    nb_ratio_distribution_pct: Optional[float]  # OQ1 future-use field
    degraded: bool
    stale: bool = False                   # Tier 2 only: Tier 1 cache expired and unreachable
    n_resolved: int = 0                   # # of tokens that contributed (for diagnostics)


@dataclass
class _Tier1State:
    """Internal: persists between Tier 1 and Tier 2 calls."""
    sma50_map: Dict[int, float] = field(default_factory=dict)
    distance_pct_cache: Dict[int, float] = field(default_factory=dict)
    nb_ratio_distribution_pct: Optional[float] = None
    computed_at: float = 0.0


class BreadthEngine:
    """Two-tier breadth computer. Stateless across processes; one per scan cycle."""

    def __init__(
        self,
        universe,
        kite_historical_fn: Callable,
        cache_ttl_seconds: int = 3600,
        degraded_threshold: float = 0.10,
        tier1_parallelism: int = 4,
    ):
        self.universe = universe
        self._kite_historical = kite_historical_fn
        self._cache_ttl = cache_ttl_seconds
        self._degraded_threshold = degraded_threshold
        self._parallelism = tier1_parallelism
        self._state = _Tier1State()

        # Publicly readable by Tier 2:
        self.sma50_map: Dict[int, float] = {}
        self.distance_pct_cache: Dict[int, float] = {}

    async def compute_tier1(self) -> BreadthResult:
        """Hourly: fetch 60-day history for all Nifty 100, compute SMA50 + distance_pct."""
        now = time.time()
        if (
            self._state.computed_at > 0
            and (now - self._state.computed_at) < self._cache_ttl
        ):
            logger.debug("Tier 1 cache hit")
            return self._result_from_cached_tier1(stale=False)

        tokens = sorted(self.universe.get_nifty100_tokens())
        if not tokens:
            logger.error("Universe returned 0 tokens; breadth degraded")
            return BreadthResult(
                breadth_pct_above_sma50=None,
                rank_map={},
                nb_ratio_distribution_pct=None,
                degraded=True,
                n_resolved=0,
            )

        sma50_map: Dict[int, float] = {}
        distance_pct_map: Dict[int, float] = {}
        failures = 0
        nb_ratios: list = []

        sem = asyncio.Semaphore(self._parallelism)

        async def fetch_one(token: int) -> None:
            nonlocal failures
            try:
                async with sem:
                    df = await self._kite_historical(token, period="60d", interval="day")
                if df is None or len(df) < 50 or "close" not in df.columns:
                    failures += 1
                    return
                closes = df["close"]
                sma50 = float(closes.rolling(50).mean().iloc[-1])
                last_close = float(closes.iloc[-1])
                distance_pct = (last_close - sma50) / sma50 if sma50 > 0 else 0.0
                sma50_map[token] = sma50
                distance_pct_map[token] = distance_pct
                # NB ratio placeholder: real impl will pull NB close from kite.quote
                # in a follow-up PR (OQ1 — wired to regime in a separate spec).
                # Recording 0.0 as a stub so nb_ratio_distribution_pct is computable.
                nb_ratios.append(0.0)
            except Exception as e:
                logger.warning(f"Tier 1 fetch failed for token {token}: {e}")
                failures += 1

        await asyncio.gather(*(fetch_one(t) for t in tokens))

        total = len(tokens)
        failure_rate = failures / total if total else 1.0
        degraded = failure_rate > self._degraded_threshold

        if degraded:
            logger.warning(
                f"Tier 1 degraded: {failures}/{total} fetches failed ({failure_rate:.1%})"
            )
            return BreadthResult(
                breadth_pct_above_sma50=None,
                rank_map={},
                nb_ratio_distribution_pct=None,
                degraded=True,
                n_resolved=total - failures,
            )

        # Cache the result
        self.sma50_map = sma50_map
        self.distance_pct_cache = distance_pct_map
        self._state.sma50_map = sma50_map
        self._state.distance_pct_cache = distance_pct_map
        self._state.computed_at = now
        self._state.nb_ratio_distribution_pct = (
            sum(1 for r in nb_ratios if r > 0) / len(nb_ratios) if nb_ratios else None
        )

        return self._result_from_cached_tier1(stale=False)

    def _result_from_cached_tier1(self, stale: bool) -> BreadthResult:
        """Build BreadthResult from cached SMA50/distance data (no Kite calls)."""
        if not self.sma50_map:
            return BreadthResult(
                breadth_pct_above_sma50=None,
                rank_map={},
                nb_ratio_distribution_pct=None,
                degraded=True,
                stale=stale,
                n_resolved=0,
            )

        n_above = sum(1 for d in self.distance_pct_cache.values() if d > 0)
        breadth_pct = n_above / len(self.distance_pct_cache)
        rank_map = self._rank_from_distances(self.distance_pct_cache)
        return BreadthResult(
            breadth_pct_above_sma50=breadth_pct,
            rank_map=rank_map,
            nb_ratio_distribution_pct=self._state.nb_ratio_distribution_pct,
            degraded=False,
            stale=stale,
            n_resolved=len(self.distance_pct_cache),
        )

    @staticmethod
    def _rank_from_distances(distances: Dict[int, float]) -> Dict[int, float]:
        """Percentile-rank each token's distance_pct within the universe.

        Returns 0.0 (bottom) to 1.0 (top). Ties share the average rank.
        """
        if not distances:
            return {}
        sorted_items = sorted(distances.items(), key=lambda kv: kv[1])
        n = len(sorted_items)
        if n == 1:
            return {sorted_items[0][0]: 1.0}
        rank_map: Dict[int, float] = {}
        i = 0
        while i < n:
            j = i
            while j + 1 < n and sorted_items[j + 1][1] == sorted_items[i][1]:
                j += 1
            avg_position = (i + j) / 2.0
            percentile = avg_position / (n - 1)
            for k in range(i, j + 1):
                rank_map[sorted_items[k][0]] = percentile
            i = j + 1
        return rank_map

    async def compute_tier2(self, scan_ltp: Dict[int, float]) -> BreadthResult:
        """Per-scan: refresh distance_pct with live LTP from the scan pass.

        Zero Kite calls. If Tier 1 was never run (cold start), return degraded.
        If a token is missing from ``scan_ltp``, fall back to last known distance_pct.
        """
        if not self.sma50_map:
            logger.warning("Tier 2 called without Tier 1 cache; returning degraded")
            return BreadthResult(
                breadth_pct_above_sma50=None,
                rank_map={},
                nb_ratio_distribution_pct=None,
                degraded=True,
                stale=False,
                n_resolved=0,
            )

        # Refresh distance_pct with today's close (live LTP from scan)
        live_distances: Dict[int, float] = {}
        for token, sma50 in self.sma50_map.items():
            ltp = scan_ltp.get(token)
            if ltp is None or sma50 <= 0:
                # If scan didn't include this token (e.g. data gap), use last known
                live_distances[token] = self.distance_pct_cache.get(token, 0.0)
            else:
                live_distances[token] = (ltp - sma50) / sma50

        n_above = sum(1 for d in live_distances.values() if d > 0)
        breadth_pct = n_above / len(live_distances) if live_distances else None
        rank_map = self._rank_from_distances(live_distances)

        return BreadthResult(
            breadth_pct_above_sma50=breadth_pct,
            rank_map=rank_map,
            nb_ratio_distribution_pct=self._state.nb_ratio_distribution_pct,
            degraded=False,
            stale=False,
            n_resolved=len(live_distances),
        )
