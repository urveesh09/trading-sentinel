# Breadth Enrichment — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real market-breadth signals (Nifty 100 % above SMA50 + per-stock relative-strength rank) into the existing signal scoring, so the system surfaces winners in any regime (including R2/R3 down markets) and tightens R1 entries during narrow rallies.

**Architecture:** Two new modules — `universe.py` (static Nifty 100 ticker list with cache) and `breadth.py` (two-tier BreadthEngine: Tier 1 hourly with 1h cache for SMA50/distances; Tier 2 per-scan with zero Kite calls for fresh rank using scan LTP). Hooks into `engine.py` (score bonus + multiplier + R1 narrow-rally gate) and `main.py` (wire BreadthEngine into the scan cycle). Shipped behind `BREADTH_ENRICHMENT_ENABLED` feature flag, default OFF for safe rollout.

**Tech Stack:** Python 3.11, pandas, numpy, pytest, pytest-asyncio, asyncio. Reuses `kite_client.historical()` (already in the codebase) and `pydantic-settings` (already used by `config.py`).

**Spec:** `docs/superpowers/specs/2026-06-14-breadth-enrichment-design.md` (commit `f422404`)

---

## File Map

| File | Action | What changes |
|---|---|---|
| `python-engine/data/nifty100.json` | NEW | Static Nifty 100 ticker list (100 entries: symbol, instrument_token) |
| `python-engine/universe.py` | NEW | `Universe` class: loads Nifty 100, exposes `get_nifty100_tokens()`, raises `UniverseError` on bad JSON |
| `python-engine/breadth.py` | NEW | `BreadthEngine` class: `compute_tier1()` (async), `compute_tier2(scan_ltp)`, two-tier cache, degraded-path handling |
| `python-engine/tests/test_universe.py` | NEW | Universe tests (load, cache, error paths) |
| `python-engine/tests/test_breadth.py` | NEW | BreadthEngine tests (Tier 1, Tier 2, cache TTL, degraded, two-tier) |
| `python-engine/config.py` | MODIFY | Add 12 new `BREADTH_*` settings (all defaults defined, flag off) |
| `python-engine/engine.py` | MODIFY | Extend `evaluate_signal()` signature with `breadth_rank`; add score bonus + multiplier; add R1 narrow-rally gate |
| `python-engine/main.py` | MODIFY | Instantiate `BreadthEngine`; wire into scan cycle; pass `breadth_rank` to `evaluate_signal()` |
| `python-engine/tests/test_engine.py` | MODIFY | Add tests for breadth scoring bonus + multiplier + R1 narrow-rally gate |
| `docs/runbooks/breadth-debug.md` | NEW | Operator runbook for breadth-degraded scenarios |

---

## Task 1: Add breadth configuration to `config.py`

**Files:**
- Modify: `python-engine/config.py`

- [ ] **Step 1: Add the 12 new settings to the `Settings` class**

Open `python-engine/config.py`. Find the line `settings = Settings()` (last line of file). Insert the new settings block immediately **above** that line (i.e. as the last fields in the `Settings` class):

```python
    # === Breadth Enrichment (2026-06-14) ===
    BREADTH_ENRICHMENT_ENABLED:         bool  = False   # Feature flag — OFF by default
    BREADTH_UNIVERSE:                   str   = "NIFTY100"
    BREADTH_CACHE_TTL_SECONDS:          int   = 3600    # Tier 1 stale-while-revalidate window
    BREADTH_FETCH_TIMEOUT_SECONDS:      int   = 90      # Max time for Tier 1 fetch
    BREADTH_NARROW_RALLY_THRESHOLD:     float = 0.40    # R1 gate fires below this
    BREADTH_NARROW_GATE_EXEMPT_RANK:    float = 0.80    # Top quintile bypasses R1 gate
    BREADTH_RANK_BONUS_TOP:             int   = 15      # +15 if rank >= 0.80
    BREADTH_RANK_BONUS_MID:             int   = 7       # +7 if rank >= 0.60
    BREADTH_RANK_PENALTY_BOTTOM:        int   = -10     # -10 if rank < 0.20
    BREADTH_RANK_MULTIPLIER:            float = 1.2     # Top quintile score × this
    BREADTH_DATA_DEGRADED_THRESHOLD:    float = 0.10    # >10% fetch failures = degraded
    BREADTH_TIER1_PARALLELISM:          int   = 4       # Concurrent Kite historical fetches
```

- [ ] **Step 2: Verify settings load without error**

```bash
cd ~/trading-sentinel/python-engine
python -c "from config import settings; print(settings.BREADTH_ENRICHMENT_ENABLED, settings.BREADTH_NARROW_RALLY_THRESHOLD, settings.BREADTH_RANK_MULTIPLIER)"
```

Expected output: `False 0.4 1.2`

- [ ] **Step 3: Commit**

```bash
cd ~/trading-sentinel
git add python-engine/config.py
git commit -m "feat(config): add breadth enrichment settings (feature flag off)"
```

---

## Task 2: Create the static Nifty 100 ticker data file

**Files:**
- Create: `python-engine/data/nifty100.json`

- [ ] **Step 1: Create the `data/` directory**

```bash
mkdir -p ~/trading-sentinel/python-engine/data
```

- [ ] **Step 2: Fetch the current Nifty 100 constituent list from NSE**

```bash
curl -s "https://archives.nseindia.com/content/indices/ind_nifty100list.csv" -o /tmp/nifty100.csv
head -3 /tmp/nifty100.csv
```

Expected: CSV with header row including `Symbol` and columns for ISIN, Industry, etc. NSE occasionally rate-limits; if the request fails, use the saved list from the last quarterly rebalance (commit a static fallback in this case and note the source date in a header comment).

- [ ] **Step 3: Convert CSV to the project's `nifty100.json` schema**

Create `python-engine/data/nifty100.json` with the following JSON structure (one entry per stock):

```json
{
  "as_of_date": "2026-06-14",
  "source": "NSE ind_nifty100list.csv (quarterly rebalance)",
  "tickers": [
    {"symbol": "RELIANCE", "instrument_token": null},
    {"symbol": "TCS", "instrument_token": null},
    ...98 more entries...
    {"symbol": "ZOMATO", "instrument_token": null}
  ]
}
```

The `instrument_token` field is `null` at the JSON level because it depends on Kite's instrument master, which is fetched at runtime by `Universe`. The `Universe` class resolves the token via `kite_client.instrument_cache[SYMBOL]` during startup. If a symbol can't be resolved, `Universe` logs a warning and excludes it from the breadth universe (does not raise).

- [ ] **Step 4: Verify the JSON parses and has 100 entries**

```bash
cd ~/trading-sentinel/python-engine
python -c "
import json
with open('data/nifty100.json') as f:
    d = json.load(f)
assert len(d['tickers']) == 100, f'Expected 100, got {len(d[\"tickers\"])}'
assert d['as_of_date']
print(f'OK: {len(d[\"tickers\"])} tickers, as_of={d[\"as_of_date\"]}')
"
```

Expected: `OK: 100 tickers, as_of=2026-06-14`

- [ ] **Step 5: Commit**

```bash
cd ~/trading-sentinel
git add python-engine/data/nifty100.json
git commit -m "feat(data): add static Nifty 100 ticker list (2026-06-14 rebalance)"
```

---

## Task 3: Create the `Universe` module (TDD)

**Files:**
- Create: `python-engine/universe.py`
- Test: `python-engine/tests/test_universe.py`

- [ ] **Step 1: Write the failing tests**

Create `python-engine/tests/test_universe.py`:

```python
"""Tests for the static Nifty 100 universe loader."""
import json
import os
import pytest
from unittest.mock import patch

from universe import Universe, UniverseError


@pytest.fixture
def fake_kite_cache():
    """Mock kite_client.instrument_cache with 100 valid + 1 missing symbol."""
    cache = {f"SYM{i:03d}": 100000 + i for i in range(100)}
    cache["SYM042"] = None  # Simulate one unresolvable symbol
    return cache


def test_universe_loads_all_100_tickers(fake_kite_cache, tmp_path):
    """Universe should resolve 99 of 100 tokens (1 missing excluded, not raised)."""
    data_file = tmp_path / "nifty100.json"
    data_file.write_text(json.dumps({
        "as_of_date": "2026-06-14",
        "tickers": [{"symbol": f"SYM{i:03d}", "instrument_token": None} for i in range(100)]
    }))

    with patch("kite_client.instrument_cache", fake_kite_cache):
        u = Universe(str(data_file))
        tokens = u.get_nifty100_tokens()

    assert len(tokens) == 99, f"Expected 99 (1 missing), got {len(tokens)}"


def test_universe_raises_on_missing_file(tmp_path):
    """Universe should fail-fast if JSON file is missing."""
    with pytest.raises(UniverseError, match="not found"):
        Universe(str(tmp_path / "does_not_exist.json"))


def test_universe_raises_on_malformed_json(tmp_path):
    """Universe should fail-fast if JSON is malformed (not a dict)."""
    data_file = tmp_path / "bad.json"
    data_file.write_text("not valid json {[}")

    with pytest.raises(UniverseError, match="malformed"):
        Universe(str(data_file))


def test_universe_raises_on_missing_tickers_key(tmp_path):
    """Universe should fail-fast if 'tickers' key is missing."""
    data_file = tmp_path / "no_tickers.json"
    data_file.write_text(json.dumps({"as_of_date": "2026-06-14"}))

    with pytest.raises(UniverseError, match="tickers"):
        Universe(str(data_file))


def test_universe_caches_tokens_on_second_call(fake_kite_cache, tmp_path):
    """Universe should not re-read file or re-resolve on second call."""
    data_file = tmp_path / "nifty100.json"
    data_file.write_text(json.dumps({
        "as_of_date": "2026-06-14",
        "tickers": [{"symbol": f"SYM{i:03d}", "instrument_token": None} for i in range(100)]
    }))

    with patch("kite_client.instrument_cache", fake_kite_cache) as mock_cache:
        u = Universe(str(data_file))
        tokens1 = u.get_nifty100_tokens()
        tokens2 = u.get_nifty100_tokens()
        assert tokens1 == tokens2
        # Cache should only be touched once (during initial load)
        # (Weak assertion: dict access isn't easy to count; we just verify
        #  equality + that get_nifty100_tokens doesn't fail.)
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd ~/trading-sentinel/python-engine
python -m pytest tests/test_universe.py -v
```

Expected: All 5 tests FAIL with `ModuleNotFoundError: No module named 'universe'` or `ImportError`.

- [ ] **Step 3: Write the minimal implementation**

Create `python-engine/universe.py`:

```python
"""Static Nifty 100 ticker universe loader with cache."""
import json
import logging
from typing import List, Set

from kite_client import instrument_cache

logger = logging.getLogger(__name__)


class UniverseError(Exception):
    """Raised when the Nifty 100 universe JSON is missing, malformed, or invalid."""


class Universe:
    """Loads the Nifty 100 ticker list from a static JSON file and resolves
    Kite instrument tokens at construction time. Caches the result in-memory."""

    def __init__(self, json_path: str):
        self._tokens: Set[int] = set()
        self._load(json_path)

    def _load(self, json_path: str) -> None:
        """Read JSON, validate schema, resolve tokens. Fail-fast on bad data."""
        if not __import__("os").path.exists(json_path):
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
            symbol = entry.get("symbol")
            if not symbol:
                continue
            token = instrument_cache.get(symbol)
            if token is None:
                missing.append(symbol)
                continue
            self._tokens.add(token)
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
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
cd ~/trading-sentinel/python-engine
python -m pytest tests/test_universe.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/trading-sentinel
git add python-engine/universe.py python-engine/tests/test_universe.py
git commit -m "feat(universe): static Nifty 100 loader with cache + fail-fast validation"
```

---

## Task 4: Create the `BreadthEngine` module (TDD) — Tier 1 only

**Files:**
- Create: `python-engine/breadth.py`
- Test: `python-engine/tests/test_breadth.py`

We split the BreadthEngine work into two tasks (4 and 5) so each is reviewable. Task 4 covers Tier 1 only; Task 5 adds Tier 2 + the integration glue.

- [ ] **Step 1: Write the failing tests for Tier 1**

Create `python-engine/tests/test_breadth.py` with these Tier 1 tests:

```python
"""Tests for the BreadthEngine (Tier 1 + Tier 2)."""
import time
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from breadth import BreadthEngine, BreadthResult, BreadthDegraded


# --- Helpers ---

def make_closes(above_sma: int, total: int = 100) -> pd.DataFrame:
    """Synthesize a 60-day daily close series where the last close is either
    above or below its 50-day SMA. For 'above' stocks, last close is +5% of SMA;
    for 'below' stocks, last close is -5% of SMA. Earlier 50 closes are flat
    around 100 (so SMA50 ≈ 100)."""
    n_above = above_sma
    n_below = total - above_sma
    above_returns = [+0.001] * 49 + [+0.05]  # drift up 0.1% per day, +5% last day
    below_returns = [+0.001] * 49 + [-0.05]  # drift up 0.1% per day, -5% last day
    return {
        "above": [100.0] + [100.0 * (1 + sum(above_returns[:i+1])) for i in range(49)] + [100.0 * (1 + sum(above_returns))],
        "below": [100.0] + [100.0 * (1 + sum(below_returns[:i+1])) for i in range(49)] + [100.0 * (1 + sum(below_returns))],
    }


@pytest.fixture
def universe_100():
    """A Universe returning 100 tokens."""
    u = MagicMock()
    u.get_nifty100_tokens.return_value = set(range(1000, 1100))
    return u


@pytest.fixture
def kite_historical_factory():
    """Factory: returns an async function that mocks kite.historical(token, ...)."""
    def _factory(above_count: int = 60):
        closes_map = make_closes(above_count, 100)
        async def fake_historical(token, period, interval):
            # Tokens 1000..1059 are 'above', 1060..1099 are 'below'
            idx = token - 1000
            if idx < above_count:
                closes = closes_map["above"]
            else:
                closes = closes_map["below"]
            return pd.DataFrame({"close": closes})
        return fake_historical
    return _factory


# --- Tier 1 tests ---

@pytest.mark.asyncio
async def test_compute_tier1_60_above_40_below(universe_100, kite_historical_factory):
    """Tier 1: 60 stocks above SMA50, 40 below → breadth_pct = 0.60."""
    engine = BreadthEngine(universe_100, kite_historical_factory(), cache_ttl_seconds=3600)
    result = await engine.compute_tier1()

    assert isinstance(result, BreadthResult)
    assert result.breadth_pct_above_sma50 == pytest.approx(0.60, abs=0.01)
    assert result.degraded is False
    assert result.nb_ratio_distribution_pct is not None  # OQ1 future-use field present


@pytest.mark.asyncio
async def test_compute_tier1_caches_sma50_map(universe_100, kite_historical_factory):
    """Tier 1 should populate sma50_map and distance_pct_cache for Tier 2 use."""
    engine = BreadthEngine(universe_100, kite_historical_factory(), cache_ttl_seconds=3600)
    result = await engine.compute_tier1()

    assert len(engine.sma50_map) == 100
    assert len(engine.distance_pct_cache) == 100
    # Spot check: tokens 1000..1059 are 'above' (positive distance_pct)
    assert engine.distance_pct_cache[1000] > 0
    assert engine.distance_pct_cache[1099] < 0


@pytest.mark.asyncio
async def test_compute_tier1_degraded_when_15pct_fail(universe_100, kite_historical_factory):
    """If >10% of fetches fail, result is degraded with None breadth_pct."""
    async def flaky_historical(token, period, interval):
        if token - 1000 < 15:  # 15% fail
            raise RuntimeError("Kite 503")
        return await kite_historical_factory()(token, period, interval)

    engine = BreadthEngine(universe_100, flaky_historical, cache_ttl_seconds=3600)
    result = await engine.compute_tier1()

    assert result.degraded is True
    assert result.breadth_pct_above_sma50 is None
    assert result.rank_map == {}


@pytest.mark.asyncio
async def test_compute_tier1_cache_ttl(universe_100, kite_historical_factory):
    """Second call within TTL returns cached result; after TTL, refetches."""
    call_count = [0]
    async def counting_historical(token, period, interval):
        call_count[0] += 1
        return await kite_historical_factory()(token, period, interval)

    engine = BreadthEngine(universe_100, counting_historical, cache_ttl_seconds=60)

    with patch("breadth.time.time") as mock_time:
        mock_time.return_value = 1000.0
        await engine.compute_tier1()
        first_calls = call_count[0]
        assert first_calls == 100

        # 30 seconds later, still in TTL
        mock_time.return_value = 1030.0
        await engine.compute_tier1()
        assert call_count[0] == 100  # No new calls

        # 2 minutes later, TTL expired
        mock_time.return_value = 1120.0
        await engine.compute_tier1()
        assert call_count[0] == 200  # 100 new calls
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd ~/trading-sentinel/python-engine
python -m pytest tests/test_breadth.py -v
```

Expected: All 4 tests FAIL with `ModuleNotFoundError: No module named 'breadth'`.

- [ ] **Step 3: Write the minimal Tier 1 implementation**

Create `python-engine/breadth.py`:

```python
"""Two-tier market-breadth computation engine.

Tier 1 (hourly): fetches 60-day daily history for the Nifty 100 universe,
computes SMA50 and signed distance_pct per stock, caches the result.

Tier 2 (per-scan): uses the scan pass's live LTP + cached SMA50 to refresh
breadth_pct_above_sma50 and per-stock rank. Zero Kite calls.

Both tiers return a BreadthResult. When Tier 1 fails on >10% of fetches,
returns a BreadthDegraded marker (breadth_pct=None, rank_map={}).
"""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Set

import pandas as pd

from config import settings
from universe import Universe

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
    in_flight: bool = False


class BreadthEngine:
    """Two-tier breadth computer. Stateless across processes; one per scan cycle."""

    def __init__(
        self,
        universe: Universe,
        kite_historical_fn: Callable,    # async (token, period, interval) -> DataFrame
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
        if self._state.computed_at > 0 and (now - self._state.computed_at) < self._cache_ttl:
            # Cache hit: rebuild rank_map from cached data, return as if Tier 2
            logger.debug("Tier 1 cache hit")
            return await self._result_from_cached_tier1(stale=False)

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
        nb_ratios: list = []
        failures = 0

        sem = asyncio.Semaphore(self._parallelism)

        async def fetch_one(token: int):
            nonlocal failures
            try:
                async with sem:
                    df = await asyncio.wait_for(
                        self._kite_historical(token, period="60d", interval="day"),
                        timeout=settings.BREADTH_FETCH_TIMEOUT_SECONDS / self._parallelism,
                    )
                if df is None or len(df) < 50 or "close" not in df.columns:
                    failures += 1
                    return
                closes = df["close"]
                sma50 = float(closes.rolling(50).mean().iloc[-1])
                last_close = float(closes.iloc[-1])
                distance_pct = (last_close - sma50) / sma50 if sma50 > 0 else 0.0
                sma50_map[token] = sma50
                distance_pct_map[token] = distance_pct
                # NB ratio placeholder: real implementation pulls NB close from kite.quote
                # For this spec, we record 0.0 as a stub (OQ1 — wired in follow-up PR)
                nb_ratios.append(0.0)
            except Exception as e:
                logger.warning(f"Tier 1 fetch failed for token {token}: {e}")
                failures += 1

        await asyncio.gather(*(fetch_one(t) for t in tokens))

        total = len(tokens)
        failure_rate = failures / total if total else 1.0
        degraded = failure_rate > self._degraded_threshold

        if degraded:
            logger.warning(f"Tier 1 degraded: {failures}/{total} fetches failed ({failure_rate:.1%})")
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

        return await self._result_from_cached_tier1(stale=False)

    async def _result_from_cached_tier1(self, stale: bool) -> BreadthResult:
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
        Returns 0.0 (bottom) to 1.0 (top). Uses simple sorted-position percentile."""
        if not distances:
            return {}
        sorted_items = sorted(distances.items(), key=lambda kv: kv[1])
        n = len(sorted_items)
        # Handle ties by averaging the rank of tied items
        rank_map: Dict[int, float] = {}
        i = 0
        while i < n:
            j = i
            while j + 1 < n and sorted_items[j + 1][1] == sorted_items[i][1]:
                j += 1
            avg_rank = (i + j) / 2.0
            for k in range(i, j + 1):
                rank_map[sorted_items[k][0]] = avg_rank / (n - 1) if n > 1 else 1.0
            i = j + 1
        return rank_map

    # Tier 2 is added in Task 5
    async def compute_tier2(self, scan_ltp: Dict[int, float]) -> BreadthResult:
        """Override implemented in Task 5."""
        raise NotImplementedError("Tier 2 implemented in Task 5")
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
cd ~/trading-sentinel/python-engine
python -m pytest tests/test_breadth.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/trading-sentinel
git add python-engine/breadth.py python-engine/tests/test_breadth.py
git commit -m "feat(breadth): Tier 1 SMA50 + distance_pct computation with 1h cache"
```

---

## Task 5: Add Tier 2 to `BreadthEngine` (TDD)

**Files:**
- Modify: `python-engine/breadth.py`
- Modify: `python-engine/tests/test_breadth.py`

- [ ] **Step 1: Add the failing Tier 2 tests**

Append these tests to `python-engine/tests/test_breadth.py` (after the Tier 1 tests):

```python
# --- Tier 2 tests ---

@pytest.mark.asyncio
async def test_compute_tier2_uses_scan_ltp(universe_100, kite_historical_factory):
    """Tier 2 should refresh distance_pct with live LTP from the scan pass,
    without making any Kite calls."""
    call_count = [0]
    async def counting_historical(token, period, interval):
        call_count[0] += 1
        return await kite_historical_factory()(token, period, interval)

    engine = BreadthEngine(universe_100, counting_historical, cache_ttl_seconds=3600)
    # First run Tier 1 to populate cache
    await engine.compute_tier1()
    assert call_count[0] == 100

    # Build a scan_ltp: bump all 'above' tokens by +2% (improving) and all 'below'
    # by -2% (worsening). All 60 'above' should still be above; all 40 'below' below.
    scan_ltp = {}
    for token in range(1000, 1100):
        old_close = 100.0 * (1.05 if token - 1000 < 60 else 0.95)
        scan_ltp[token] = old_close * 1.02

    tier1_calls = call_count[0]
    result = await engine.compute_tier2(scan_ltp)
    assert call_count[0] == tier1_calls  # Zero new Kite calls

    assert result.degraded is False
    assert result.breadth_pct_above_sma50 == pytest.approx(0.60, abs=0.01)
    # All 100 should have a rank in the map
    assert len(result.rank_map) == 100


@pytest.mark.asyncio
async def test_compute_tier2_degraded_when_tier1_cache_empty(universe_100, kite_historical_factory):
    """If Tier 1 was never run (cold start), Tier 2 returns degraded without
    falling back to a live fetch."""
    engine = BreadthEngine(universe_100, kite_historical_factory(), cache_ttl_seconds=3600)
    # No compute_tier1() call
    result = await engine.compute_tier2(scan_ltp={t: 100.0 for t in range(1000, 1100)})

    assert result.degraded is True
    assert result.breadth_pct_above_sma50 is None
    assert result.rank_map == {}


@pytest.mark.asyncio
async def test_tier2_rank_changes_with_ltp(universe_100, kite_historical_factory):
    """Stock that was 'below' SMA50 in Tier 1 but spikes in Tier 2 LTP should
    get a higher rank in Tier 2 than in Tier 1."""
    engine = BreadthEngine(universe_100, kite_historical_factory(), cache_ttl_seconds=3600)
    tier1 = await engine.compute_tier1()
    rank_in_tier1_token1099 = tier1.rank_map[1099]  # This is a 'below' stock

    # Spike token 1099's LTP to +10% above its SMA50
    scan_ltp = {t: 100.0 for t in range(1000, 1100)}
    scan_ltp[1099] = 100.0 * 1.10  # 10% above its SMA50 (was 5% below)

    tier2 = await engine.compute_tier2(scan_ltp)
    rank_in_tier2_token1099 = tier2.rank_map[1099]

    assert rank_in_tier2_token1099 > rank_in_tier1_token1099
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
cd ~/trading-sentinel/python-engine
python -m pytest tests/test_breadth.py -v
```

Expected: The 3 new Tier 2 tests FAIL with `NotImplementedError: Tier 2 implemented in Task 5` (or similar).

- [ ] **Step 3: Replace the Tier 2 stub with the real implementation**

In `python-engine/breadth.py`, replace the stub:

```python
    # Tier 2 is added in Task 5
    async def compute_tier2(self, scan_ltp: Dict[int, float]) -> BreadthResult:
        """Override implemented in Task 5."""
        raise NotImplementedError("Tier 2 implemented in Task 5")
```

with:

```python
    async def compute_tier2(self, scan_ltp: Dict[int, float]) -> BreadthResult:
        """Per-scan: refresh distance_pct with live LTP from the scan pass.
        Zero Kite calls. If Tier 1 was never run (cold start), return degraded."""
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
```

- [ ] **Step 4: Run the tests to confirm they pass**

```bash
cd ~/trading-sentinel/python-engine
python -m pytest tests/test_breadth.py -v
```

Expected: All 7 tests (4 Tier 1 + 3 Tier 2) PASS.

- [ ] **Step 5: Commit**

```bash
cd ~/trading-sentinel
git add python-engine/breadth.py python-engine/tests/test_breadth.py
git commit -m "feat(breadth): Tier 2 per-scan rank with live LTP, zero Kite calls"
```

---

## Task 6: Wire breadth scoring into `engine.py` (TDD)

**Files:**
- Modify: `python-engine/engine.py` (extend `evaluate_signal()` signature + add scoring logic)
- Modify: `python-engine/tests/test_engine.py`

- [ ] **Step 1: Read the current `evaluate_signal()` signature to know what to extend**

```bash
cd ~/trading-sentinel/python-engine
grep -n "def evaluate_signal" engine.py
sed -n '168,180p' engine.py
```

Expected: `def evaluate_signal(ticker, df, bankroll, risk_pct, regime=..., market_regime=..., nifty_50_current=..., nifty_ema20=..., nifty_return_1d=..., rsi_history=...)` at line 168.

- [ ] **Step 2: Write the failing tests**

Append to `python-engine/tests/test_engine.py`:

```python
# --- Breadth enrichment tests (Task 6) ---

from engine import evaluate_signal
from regime import Regime


def _make_df():
    """Build a minimal 250-day OHLCV DataFrame that passes the 200-day gate."""
    import numpy as np
    n = 250
    close = np.linspace(100, 150, n) + np.random.RandomState(42).normal(0, 1, n)
    high = close + 1
    low = close - 1
    open_ = close
    volume = np.full(n, 1_000_000.0)
    return pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close, "volume": volume
    })


def test_breadth_rank_top_quintile_gets_bonus_and_multiplier():
    """breadth_rank >= 0.80 → +15 bonus + 1.2x multiplier."""
    df = _make_df()
    bankroll = 100_000
    # Build a baseline (no breadth_rank) and a top-rank variant
    _, base = evaluate_signal("TEST", df, bankroll, 0.02, regime=Regime.REGIME_1_NORMAL)
    _, top = evaluate_signal(
        "TEST", df, bankroll, 0.02,
        regime=Regime.REGIME_1_NORMAL, breadth_rank=0.85,
    )
    # The top-rank score should be at least +15 and * 1.2
    # i.e. expected >= base + 15 then * 1.2 (clamped to 100)
    expected_min = min(100, int((base["score"] + 15) * 1.2))
    assert top["score"] >= expected_min - 1  # Allow ±1 for rounding


def test_breadth_rank_mid_gets_bonus_no_multiplier():
    """0.60 <= breadth_rank < 0.80 → +7 bonus, no multiplier."""
    df = _make_df()
    bankroll = 100_000
    _, base = evaluate_signal("TEST", df, bankroll, 0.02, regime=Regime.REGIME_1_NORMAL)
    _, mid = evaluate_signal(
        "TEST", df, bankroll, 0.02,
        regime=Regime.REGIME_1_NORMAL, breadth_rank=0.65,
    )
    assert mid["score"] == base["score"] + 7


def test_breadth_rank_bottom_gets_penalty():
    """breadth_rank < 0.20 → -10 penalty."""
    df = _make_df()
    bankroll = 100_000
    _, base = evaluate_signal("TEST", df, bankroll, 0.02, regime=Regime.REGIME_1_NORMAL)
    _, bot = evaluate_signal(
        "TEST", df, bankroll, 0.02,
        regime=Regime.REGIME_1_NORMAL, breadth_rank=0.10,
    )
    assert bot["score"] == base["score"] - 10


def test_breadth_rank_none_no_effect():
    """breadth_rank=None (degraded) → no scoring changes."""
    df = _make_df()
    bankroll = 100_000
    _, base = evaluate_signal("TEST", df, bankroll, 0.02, regime=Regime.REGIME_1_NORMAL)
    _, none = evaluate_signal(
        "TEST", df, bankroll, 0.02,
        regime=Regime.REGIME_1_NORMAL, breadth_rank=None,
    )
    assert none["score"] == base["score"]


def test_breadth_narrow_rally_gate_r1_rejects_non_leader():
    """R1 + breadth_pct < 0.40 + rank < 0.80 → rejected."""
    df = _make_df()
    bankroll = 100_000
    ok, res = evaluate_signal(
        "TEST", df, bankroll, 0.02,
        regime=Regime.REGIME_1_NORMAL,
        breadth_rank=0.50,
        breadth_pct_above_sma50=0.30,
    )
    assert ok is False
    assert res.get("narrow_rally_filtered") is True


def test_breadth_narrow_rally_gate_r1_exempts_top_quintile():
    """R1 + breadth_pct < 0.40 + rank >= 0.80 → accepted."""
    df = _make_df()
    bankroll = 100_000
    ok, res = evaluate_signal(
        "TEST", df, bankroll, 0.02,
        regime=Regime.REGIME_1_NORMAL,
        breadth_rank=0.85,
        breadth_pct_above_sma50=0.30,
    )
    # Should pass the gate (may still fail other gates, but not narrow_rally)
    assert res.get("narrow_rally_filtered") is None or res.get("narrow_rally_filtered") is False


def test_breadth_narrow_rally_gate_r1_skips_when_degraded():
    """R1 + breadth_pct=None (degraded) → gate skipped, signal allowed."""
    df = _make_df()
    bankroll = 100_000
    ok, res = evaluate_signal(
        "TEST", df, bankroll, 0.02,
        regime=Regime.REGIME_1_NORMAL,
        breadth_rank=0.50,
        breadth_pct_above_sma50=None,
    )
    assert res.get("narrow_rally_filtered") is None or res.get("narrow_rally_filtered") is False


def test_breadth_narrow_rally_gate_does_not_fire_in_r2():
    """R2 + breadth_pct < 0.40 + rank < 0.80 → gate does NOT fire (R1 only)."""
    df = _make_df()
    bankroll = 100_000
    ok, res = evaluate_signal(
        "TEST", df, bankroll, 0.02,
        regime=Regime.REGIME_2_ELEVATED,
        breadth_rank=0.50,
        breadth_pct_above_sma50=0.30,
    )
    # Should pass the gate; may fail other R2 filters but not narrow_rally
    assert res.get("narrow_rally_filtered") is None or res.get("narrow_rally_filtered") is False


def test_breadth_narrow_rally_gate_does_not_fire_in_r3():
    """R3 + breadth_pct < 0.40 + rank < 0.80 → gate does NOT fire (R1 only)."""
    df = _make_df()
    bankroll = 100_000
    ok, res = evaluate_signal(
        "TEST", df, bankroll, 0.02,
        regime=Regime.REGIME_3_CRISIS,
        breadth_rank=0.50,
        breadth_pct_above_sma50=0.30,
    )
    assert res.get("narrow_rally_filtered") is None or res.get("narrow_rally_filtered") is False
```

- [ ] **Step 3: Run the new tests to confirm they fail**

```bash
cd ~/trading-sentinel/python-engine
python -m pytest tests/test_engine.py -v -k "breadth"
```

Expected: All 9 breadth tests FAIL with `TypeError: evaluate_signal() got an unexpected keyword argument 'breadth_rank'`.

- [ ] **Step 4: Extend `evaluate_signal()` signature**

Open `python-engine/engine.py`. Find `def evaluate_signal(` at line 168. Replace the signature line (only the `rsi_history` line; leave the rest):

```python
def evaluate_signal(
    ticker: str,
    df: pd.DataFrame,
    bankroll: float,
    risk_pct: float,
    regime: Regime = Regime.REGIME_1_NORMAL,
    market_regime: str = "BULL",
    nifty_50_current: Optional[float] = None,
    nifty_ema20: Optional[float] = None,
    nifty_return_1d: Optional[float] = None,
    rsi_history: Optional[pd.Series] = None,
    breadth_rank: Optional[float] = None,
    breadth_pct_above_sma50: Optional[float] = None,
) -> Tuple[bool, Dict[str, Any]]:
```

- [ ] **Step 5: Add the scoring bonus + multiplier + gate logic**

In `engine.py`, find the `score = min(score, 100)` line (around line 430). Insert the breadth block **immediately after** it (before the `# RESULT` comment):

```python
    # -----------------------------------------------------
    # BREADTH ENRICHMENT (Task 6, 2026-06-14)
    # Counter-trend enabler: top-breadth stocks get a bonus + multiplier
    # even in R2/R3. Bottom-rank stocks get a penalty.
    # -----------------------------------------------------
    if settings.BREADTH_ENRICHMENT_ENABLED and breadth_rank is not None:
        if breadth_rank >= settings.BREADTH_RANK_BONUS_TOP / 100.0:    # default 0.15
            score += settings.BREADTH_RANK_BONUS_TOP                    # +15
        elif breadth_rank >= 0.60:
            score += settings.BREADTH_RANK_BONUS_MID                    # +7
        elif breadth_rank < 0.20:
            score += settings.BREADTH_RANK_PENALTY_BOTTOM               # -10
        # Top quintile also gets a score multiplier to nudge borderline signals
        if breadth_rank >= 0.80:
            score = int(score * settings.BREADTH_RANK_MULTIPLIER)       # ×1.2
            score = min(score, 100)

    # -----------------------------------------------------
    # R1 NARROW-RALLY GATE (Task 6, 2026-06-14)
    # In R1, if breadth is bad (<40% above SMA50), only top-quintile stocks pass.
    # Skipped entirely if breadth data is degraded (breadth_pct is None).
    # -----------------------------------------------------
    narrow_rally_filtered = False
    if (
        settings.BREADTH_ENRICHMENT_ENABLED
        and regime == Regime.REGIME_1_NORMAL
        and breadth_pct_above_sma50 is not None
        and breadth_pct_above_sma50 < settings.BREADTH_NARROW_RALLY_THRESHOLD
        and (breadth_rank is None or breadth_rank < settings.BREADTH_NARROW_GATE_EXEMPT_RANK)
    ):
        narrow_rally_filtered = True
```

- [ ] **Step 6: Surface `narrow_rally_filtered` in the result dict**

In `engine.py`, find the result-dict block (lines 436-459, after the `# RESULT` comment). Add `narrow_rally_filtered` to it (right after the `regime` field, around line 455):

```python
    res = {
        "close": c,
        "ema_21": e21,
        "ema_50": e50,
        "ema_200": e200,
        "atr_14": a14,
        "volume_ratio": vol_ratio,
        "rsi_14": rsi14,
        "slope_5": slope5,
        "stop_loss": stop_loss,
        "target_1": target_1,
        "target_2": target_2,
        "shares": shares,
        "capital_deployed": capital_required,
        "capital_at_risk": shares * (c - stop_loss),
        "net_ev": net_ev,
        "score": score,
        "trailing_stop": stop_loss,
        # Regime metadata
        "regime": regime,
        "narrow_rally_filtered": narrow_rally_filtered,
        "rsi_percentile": rsi_pct if regime in (Regime.REGIME_1_NORMAL, Regime.REGIME_2_ELEVATED) else None,
        "volume_zscore": vol_zscore,
        "rs_vs_nifty": rs_vs_nifty if regime == Regime.REGIME_3_CRISIS else None,
    }
```

- [ ] **Step 7: Add the early-return for the narrow-rally gate**

In `engine.py`, find the line `if len(df) < 200:` at line 181. Add the early-return for the narrow-rally gate **right after** that block (before `df = df.copy()`):

```python
    if len(df) < 200:
        return False, {"reject_reason": "insufficient_data_200_days"}
    if narrow_rally_filtered:
        return False, {
            "reject_reason": "narrow_rally_filtered",
            "breadth_pct_above_sma50": breadth_pct_above_sma50,
            "breadth_rank": breadth_rank,
            "threshold": settings.BREADTH_NARROW_RALLY_THRESHOLD,
            "exempt_rank": settings.BREADTH_NARROW_GATE_EXEMPT_RANK,
        }
```

**Important:** The `narrow_rally_filtered` flag is computed in step 5 (after the main score block). The early-return in step 7 must use the value computed there. To make this work, you must **move the `narrow_rally_filtered = False` initialisation and the gate evaluation block from step 5 to BEFORE the `if len(df) < 200:` check**. The cleanest layout:

1. At the top of `evaluate_signal` (right after the signature), initialise `narrow_rally_filtered = False` and `score = 0`.
2. Keep the gate evaluation block in its current location (after the main score block) — but make it a **no-op for the early return** by also adding a guard: the early return only fires if the flag is `True`.
3. Alternatively (simpler): do the gate evaluation **before** `if len(df) < 200:`. Since the gate only depends on `regime`, `breadth_pct_above_sma50`, and `breadth_rank` — none of which need the `df` — this is safe.

**Recommended layout (move the gate up):**

Replace step 5 with this version that puts the gate evaluation **immediately after** the existing filters (around line 250, after the `Regime.REGIME_3_CRISIS` block), so the early return can fire before the scoring block runs:

```python
    # -----------------------------------------------------
    # R1 NARROW-RALLY GATE (Task 6, 2026-06-14)
    # Computed BEFORE the score block so the early-return is unambiguous.
    # -----------------------------------------------------
    narrow_rally_filtered = (
        settings.BREADTH_ENRICHMENT_ENABLED
        and regime == Regime.REGIME_1_NORMAL
        and breadth_pct_above_sma50 is not None
        and breadth_pct_above_sma50 < settings.BREADTH_NARROW_RALLY_THRESHOLD
        and (breadth_rank is None or breadth_rank < settings.BREADTH_NARROW_GATE_EXEMPT_RANK)
    )
```

Then keep the **scoring bonus** block (the first half of step 5) where it was (after `score = min(score, 100)`).

- [ ] **Step 8: Run the new tests to confirm they pass**

```bash
cd ~/trading-sentinel/python-engine
python -m pytest tests/test_engine.py -v -k "breadth"
```

Expected: All 9 breadth tests PASS.

- [ ] **Step 9: Run the full engine test suite to confirm no regressions**

```bash
cd ~/trading-sentinel/python-engine
python -m pytest tests/test_engine.py -v
```

Expected: All tests PASS (existing + 9 new).

- [ ] **Step 10: Commit**

```bash
cd ~/trading-sentinel
git add python-engine/engine.py python-engine/tests/test_engine.py
git commit -m "feat(engine): breadth rank scoring bonus + multiplier + R1 narrow-rally gate"
```

---

## Task 7: Wire `BreadthEngine` into `main.py` scan cycle

**Files:**
- Modify: `python-engine/main.py`

- [ ] **Step 1: Add imports at the top of `main.py`**

Open `python-engine/main.py`. Find the existing imports near the top. Add:

```python
from breadth import BreadthEngine
from universe import Universe
```

- [ ] **Step 2: Find where the scan cycle starts**

```bash
cd ~/trading-sentinel/python-engine
grep -n "def.*scan\|def.*run_scan\|def.*main\|async def" main.py | head -20
```

Look for the function that iterates the universe per scan tick. It will be the function that calls `evaluate_signal()` for each ticker.

- [ ] **Step 3: Instantiate `Universe` and `BreadthEngine` at startup**

Find the `if __name__ == "__main__":` block at the bottom of `main.py` (or wherever the app boots). Add immediately before the scan loop starts:

```python
    # Breadth enrichment (Task 7, 2026-06-14). Only constructed when the
    # feature flag is on; otherwise the engine path early-returns.
    breadth_engine: Optional[BreadthEngine] = None
    if settings.BREADTH_ENRICHMENT_ENABLED:
        universe = Universe(settings.BREADTH_DATA_DIR + "/nifty100.json")
        # kite_client.get_historical is async; BreadthEngine expects an async fn
        async def kite_historical_async(token: int, period: str, interval: str):
            return await asyncio.to_thread(
                kite_client.get_historical, token, period, interval
            )
        breadth_engine = BreadthEngine(
            universe=universe,
            kite_historical_fn=kite_historical_async,
            cache_ttl_seconds=settings.BREADTH_CACHE_TTL_SECONDS,
            degraded_threshold=settings.BREADTH_DATA_DEGRADED_THRESHOLD,
            tier1_parallelism=settings.BREADTH_TIER1_PARALLELISM,
        )
        logger.info(f"BreadthEngine enabled: {len(universe.get_nifty100_tokens())} tokens")
```

**Note:** You'll need a `BREADTH_DATA_DIR` setting. Add this to `config.py` (you can amend the config block from Task 1 or add a one-liner below it):

```python
    BREADTH_DATA_DIR: str = "data"   # relative to python-engine/ working dir
```

- [ ] **Step 4: Wire Tier 1 + Tier 2 into the scan tick**

In the scan function, find the spot where the scan cycle begins (typically right after fetching the universe OHLCV). Add:

```python
        # Breadth enrichment (Task 7)
        breadth_result = None
        scan_ltp: Dict[int, float] = {}
        if breadth_engine is not None:
            # Tier 1: cached or fresh
            breadth_result = await breadth_engine.compute_tier1()
            if breadth_result.degraded:
                logger.warning("Breadth data degraded, falling back to regime-only filters")
            # Collect live LTPs from the current scan pass for Tier 2
            for ticker_data in scan_universe:
                scan_ltp[ticker_data["instrument_token"]] = ticker_data["ltp"]
            # Tier 2: refresh rank with live LTP
            breadth_result = await breadth_engine.compute_tier2(scan_ltp)
```

**Note:** `scan_universe` is the name used here for the existing per-scan data structure. Find its actual variable name in the scan function and adapt.

- [ ] **Step 5: Pass `breadth_rank` to `evaluate_signal()`**

Find every call site of `evaluate_signal(` in `main.py`. There should be one. Add the two new keyword arguments:

```python
        ok, result = evaluate_signal(
            ticker=...,
            df=...,
            bankroll=...,
            risk_pct=...,
            regime=...,
            # ... all existing args ...
            breadth_rank=breadth_result.rank_map.get(ticker_data["instrument_token"]) if breadth_result and not breadth_result.degraded else None,
            breadth_pct_above_sma50=breadth_result.breadth_pct_above_sma50 if breadth_result and not breadth_result.degraded else None,
        )
```

- [ ] **Step 6: Log breadth diagnostics per scan**

Add (typically right after the scan tick completes):

```python
        if breadth_result is not None:
            logger.info(
                f"Breadth scan: pct_above_sma50={breadth_result.breadth_pct_above_sma50}, "
                f"degraded={breadth_result.degraded}, n_resolved={breadth_result.n_resolved}, "
                f"nb_ratio_pct={breadth_result.nb_ratio_distribution_pct}"
            )
```

- [ ] **Step 7: Run the full test suite to confirm no regressions**

```bash
cd ~/trading-sentinel/python-engine
python -m pytest tests/ -v
```

Expected: All tests PASS (no new tests added in this task, just wiring).

- [ ] **Step 8: Smoke-test the scan cycle manually**

```bash
cd ~/trading-sentinel/python-engine
BREADTH_ENRICHMENT_ENABLED=True python -c "
import asyncio
from main import run_scan_cycle    # adapt to actual function name
asyncio.run(run_scan_cycle())
" 2>&1 | grep -i breadth
```

Expected: At least one log line matching `Breadth scan: pct_above_sma50=...` with non-degraded values.

- [ ] **Step 9: Commit**

```bash
cd ~/trading-sentinel
git add python-engine/main.py python-engine/config.py
git commit -m "feat(main): wire BreadthEngine into scan cycle (Tier 1 hourly + Tier 2 per-scan)"
```

---

## Task 8: Write the operator runbook

**Files:**
- Create: `docs/runbooks/breadth-debug.md`

- [ ] **Step 1: Create the runbook**

Create `docs/runbooks/breadth-debug.md` with this content:

```markdown
# Breadth Enrichment — Operator Runbook

**Audience:** Whoever is on-call when the bot starts behaving strangely.
**Spec:** `docs/superpowers/specs/2026-06-14-breadth-enrichment-design.md`

## What this feature does

Computes real market breadth (% of Nifty 100 stocks above their 50-day SMA)
every hour (Tier 1) and refreshes the per-stock rank every 15 minutes
(Tier 2). The system uses breadth to:
- Give a +15 / +7 / -10 score bonus to stocks in the top 40% / bottom 20%
  of the breadth distribution (works in all regimes including R2/R3)
- Apply a 1.2× score multiplier to top-quintile stocks (pushes borderline
  signals above the score threshold)
- In R1 (normal) regime, when breadth is below 40%, only allow entry into
  top-quintile stocks (narrow-rally gate)

## Quick diagnostics

### "Breadth is degraded" warning in logs

**What it means:** Tier 1 failed on >10% of Nifty 100 fetches. The system
falls back to regime-only filtering (no bonus, no multiplier, no
narrow-rally gate).

**How to check:**
```bash
# 1. Confirm degraded state in logs
journalctl -u trading-sentinel | grep -i "breadth" | tail -20

# 2. Test Kite historical endpoint directly
curl -H "Authorization: token $KITE_API_KEY:$KITE_ACCESS_TOKEN" \
  "https://api.kite.trade/instruments/historical/256265/day?from=2026-04-15&to=2026-06-14"
```

**Common causes:**
- Kite API rate limit hit (3 req/s). Wait 60s, retry.
- Kite historical endpoint down. Check status.kite.trade.
- Access token expired. Re-login via ngrok flow.
- `nifty100.json` has stale symbols (Kite instrument cache not refreshed).
  Run `python -m kite_client.refresh_instrument_cache`.

**Recovery:** Setting `BREADTH_ENRICHMENT_ENABLED=False` in `.env`
disables the feature and returns the system to pre-breadth behaviour.
Restart the python-engine container after the change.

### "Too few signals firing" complaint

**What it means:** The R1 narrow-rally gate is rejecting more signals
than expected.

**How to check:** Look at scan logs for `narrow_rally_filtered=True`
rejections:
```bash
journalctl -u trading-sentinel --since "1 hour ago" | grep "narrow_rally_filtered" | wc -l
```

**Tuning:** If too aggressive, raise `BREADTH_NARROW_RALLY_THRESHOLD`
(default 0.40) toward 0.30 (more permissive) in `.env`. If still too
aggressive, raise `BREADTH_NARROW_GATE_EXEMPT_RANK` (default 0.80)
toward 0.70 (broader exemption).

**Rollback:** Set `BREADTH_ENRICHMENT_ENABLED=False` in `.env` and
restart.

### "Score feels inflated" complaint

**What it means:** The 1.2× multiplier is pushing borderline signals
above `MIN_SIGNAL_SCORE` more than expected.

**How to check:** Look at top-quintile signal scores in scan logs and
compare to pre-breadth baseline.

**Tuning:** Lower `BREADTH_RANK_MULTIPLIER` (default 1.2) toward 1.1
in `.env`. Setting it to 1.0 disables the multiplier while keeping
the +15 base bonus.

## Feature flag

| Env var | Default | What it does |
|---|---|---|
| `BREADTH_ENRICHMENT_ENABLED` | `False` | Master kill switch. `False` = no behaviour change |
| `BREADTH_NARROW_RALLY_THRESHOLD` | `0.40` | R1 gate fires below this breadth % |
| `BREADTH_NARROW_GATE_EXEMPT_RANK` | `0.80` | Top quintile bypasses R1 gate |
| `BREADTH_RANK_BONUS_TOP` | `15` | +15 to top 20% of breadth distribution |
| `BREADTH_RANK_BONUS_MID` | `7` | +7 to top 40% |
| `BREADTH_RANK_PENALTY_BOTTOM` | `-10` | -10 to bottom 20% |
| `BREADTH_RANK_MULTIPLIER` | `1.2` | Top quintile score × this |
| `BREADTH_CACHE_TTL_SECONDS` | `3600` | Tier 1 stale-while-revalidate window |
| `BREADTH_TIER1_PARALLELISM` | `4` | Concurrent Kite historical fetches |

All defaults are defined in `python-engine/config.py` and can be
overridden via `.env`. The flag is the kill switch — set it to `False`
for instant revert with no code rollback.

## Rollout checklist

- [ ] Stage 0: `BREADTH_ENRICHMENT_ENABLED=False`. Run 1 week. Confirm
  scan logs show breadth being computed (`pct_above_sma50=...`) without
  affecting signal flow.
- [ ] Stage 1: `BREADTH_ENRICHMENT_ENABLED=True`. Run 1 week. Monitor:
  - Signal count delta (expect 5-15% reduction from narrow-rally filter)
  - Win rate (expect 1-3pp improvement)
  - Breadth-degraded alerts (expect zero)
- [ ] Stage 2: After 2 clean weeks, default the flag to `True` in
  `config.py`.
```

- [ ] **Step 2: Commit**

```bash
cd ~/trading-sentinel
mkdir -p docs/runbooks
git add docs/runbooks/breadth-debug.md
git commit -m "docs(runbook): breadth enrichment operator guide + feature flag reference"
```

---

## Task 9: Integration audit

**Files:** Read-only inspection of all changed files.

- [ ] **Step 1: Verify file map matches the plan**

```bash
cd ~/trading-sentinel
echo "=== New files ==="
ls -la python-engine/universe.py python-engine/breadth.py python-engine/data/nifty100.json \
       python-engine/tests/test_universe.py python-engine/tests/test_breadth.py \
       docs/runbooks/breadth-debug.md 2>&1
echo "=== Modified files (should show breadth-related changes) ==="
git diff main --stat
```

Expected: All 6 new files exist. `git diff main --stat` shows changes in
`config.py`, `engine.py`, `main.py`, `tests/test_engine.py`.

- [ ] **Step 2: Run the full test suite one more time**

```bash
cd ~/trading-sentinel/python-engine
python -m pytest tests/ -v
```

Expected: All tests PASS (existing + new breadth tests).

- [ ] **Step 3: Cross-check the integration points**

The dev-workflow skill's "Main-vs-Branch integration gap" pitfall flags
that new modules can be wired in `main.py` (the new feature) but tests
pass because they import the new API directly. Verify by:

```bash
cd ~/trading-sentinel
echo "=== main.py should call breadth_engine.compute_tier1 / compute_tier2 ==="
grep -n "breadth_engine\|breadth_result" python-engine/main.py | head -20
echo "=== main.py should pass breadth_rank to evaluate_signal ==="
grep -n "breadth_rank" python-engine/main.py
```

Expected: Both grep commands return non-empty output.

- [ ] **Step 4: Commit the audit (only if changes were made)**

If the integration check revealed gaps, fix them and commit:
```bash
cd ~/trading-sentinel
git add -A
git commit -m "fix: integration audit follow-ups"
```

If no gaps, this task is complete with no commit.

---

## Task 10: Final commit + branch state check

- [ ] **Step 1: Verify branch state**

```bash
cd ~/trading-sentinel
git status
git log --oneline main..HEAD
```

Expected: Working tree clean. ~8 commits ahead of `main` (one per task).

- [ ] **Step 2: Confirm feature flag is OFF by default**

```bash
cd ~/trading-sentinel/python-engine
grep "BREADTH_ENRICHMENT_ENABLED" config.py
```

Expected: Line shows `BREADTH_ENRICHMENT_ENABLED: bool = False`.

---

## Done Criteria

- [ ] All 9 new breadth tests pass
- [ ] All existing tests pass (no regressions)
- [ ] Feature flag defaults to `False` (safe rollout)
- [ ] `universe.py` raises `UniverseError` on bad JSON (fail-fast)
- [ ] `breadth.py` returns `BreadthResult` with `degraded=True` when
      >10% of Tier 1 fetches fail
- [ ] `engine.py` rejects signals with `narrow_rally_filtered=True`
      before scoring
- [ ] `main.py` logs breadth diagnostics per scan
- [ ] Runbook exists at `docs/runbooks/breadth-debug.md`
- [ ] Branch is on `evolve/smart-strategies` (not `main`)
- [ ] No commits to `main` (development is on the dedicated branch)

When all of the above are true, the breadth enrichment feature is
ready for Stage 0 deployment (ship with flag off, monitor logs for 1
week, then enable in Stage 1).
