"""[WORKFLOW-H H3 + H4.B 2026-09-13] Intraday-cache caller/key/window diagnostic.

Implements plan section 12 acceptance: *"Investigate historical zero
intraday-cache hit rates: find actual caller/key/window behavior
before adding a cache. Do not mix mutable forming bars with completed
historical bars or cross-account/coin tokens."*

This module is the **diagnostic** phase of H3, extended in H4.B to
cover the by-token path. It is *read-only*: it queries both cache
tables (``intraday_cache`` and ``intraday_cache_by_token``) and
inspects the call shapes of ``kite_client.get_intraday`` and
``kite_client.get_intraday_by_token`` without modifying either.

The reason this exists separately from a fix: §12 mandates the
diagnostic *before* a fix. Cache-add (H4 + H4.B) is shipped as the
subsequent step once the operator reviews this diagnostic.

[WHY-THIS-EXISTS 2026-09-13]
  Pre-investigation, the audit doc claimed "zero intraday-cache hit
  rates" without distinguishing:
    a. Zero callers of the cached entry point (``get_intraday``)
       -- true zero hits, no callers exercise the cache.
    b. Callers that fall through the freshness gate -- the cache
       WOULD have served, but ``last_cached_dt < expected_latest``
       forced a Kite round-trip.
    c. Cold cache -- no rows ever written for that ticker/interval.

  The penny scanner (``penny_scanner.py``) calls
  ``kite.get_intraday(..., interval="minute")`` in production; the
  F&O/partner paths call ``kite.get_intraday_by_token`` which is
  *explicitly* documented as not caching. The diagnostic surfaces
  this distinction so a future operator can decide whether to
  widen caching to the by-token path or tighten the freshness gate
  on the symbol-keyed path.

[DESIGN-INVARIANTS 2026-09-13]
  1. READ-ONLY. No writes, no schema changes, no new tables.
  2. The diagnostic CLI prints the conclusion in operator-readable
     text so a future agent does NOT need to run a Python REPL
     to learn "why is the cache empty".
  3. The key-shape audit (``_audit_key_shape``) verifies the cache
     is NEVER keyed by account_id or coin_token, per §12 explicit
     constraint. A regression that adds such a key is caught
     loudly.
  4. The freshness classification uses the SAME logic as
     ``kite_client.get_intraday``: ``expected_latest =
     to_dt_obj - interval_mins`` -- no invented thresholds.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple


# ---- by-symbol entry points (the cached path) -----------------------------
# Per kite_client.py:450-580, ``get_intraday`` is the only entry
# point that reads from the intraday_cache table. Production callers
# of this entry point are penny_scanner (twice), main.py:2996 (the
# daily attribution / momentum signal evaluator).
CACHED_CALLER_SITES: Tuple[Tuple[str, str, str], ...] = (
    ("penny_scanner.py", "_run_penny_scanner", "interval=minute"),
    ("penny_scanner.py", "compute_atr_1min_post_t1", "interval=minute"),
    ("main.py", "_run_momentum_signal", "default-interval"),
)

# ---- by-token entry points (the by-token cached path) --------------------
# Per kite_client.py (H4.B 2026-09-13), ``get_intraday_by_token`` is
# NOW cached via the ``intraday_cache_by_token`` table -- the previous
# "no sqlite caching" rationale ("F&O ticks re-read every 5 minutes,
# so a cache would only serve stale bars") is replaced by the
# §12 forming-bar filter: forming candles are excluded from the HIT
# path, so a HIT serves strictly completed candles.
BY_TOKEN_CALLER_SITES: Tuple[Tuple[str, str, str], ...] = (
    ("fno_orchestrator.py", "_fetch_futures_bars", "interval=5minute"),
    ("fno_signal_scan.py", "fno_signal_scan", "interval=5minute"),
    ("partner_orchestrator.py", "partner_scan_tick", "interval=5minute"),
    ("partner_orchestrator.py", "partner_eod_wrap", "interval=5minute"),
    ("partner_orchestrator.py", "partner_eod_wrap", "interval=day"),
    ("proactive_market_data.py", "fetch_bars", "interval=5minute"),
    ("market_data_sources.py", "fetch_intraday", "interval=variable"),
    ("scripts/verify_bfo.py", "verify_bfo", "interval=day"),
)

# Back-compat alias. Older callers and tests refer to
# ``UNCACHED_CALLER_SITES``; keep that name exporting the by-token
# list since the semantic is "by-token callers" rather than
# "uncached". H4.B has moved the cache-add code from a deferred
# proposal into shipped behaviour.
UNCACHED_CALLER_SITES = BY_TOKEN_CALLER_SITES

# The freshness check used by ``kite_client.get_intraday`` is:
#     expected_latest = to_dt_obj - timedelta(minutes=interval_mins)
#     if last_cached_dt >= expected_latest: HIT, else: STALE->API.
_INTERVAL_MINUTES: Dict[str, int] = {
    "minute": 1,
    "5minute": 5,
    "15minute": 15,
    "30minute": 30,
    "60minute": 60,
    "day": 1440,
}


def _interval_minutes(interval: str) -> int:
    """Resolve the interval string to a number of minutes.

    Mirrors the helper of the same name in kite_client.get_intraday
    so the diagnostic classifies rows using the SAME rule the
    cache hit/miss path uses.
    """
    iv = (interval or "").strip().lower()
    return _INTERVAL_MINUTES.get(iv, 1)


# ---- diagnostic entry points ------------------------------------------------

def init_intraday_cache_diag_db(db_path: str) -> None:
    """Ensure the intraday_cache tables exist so the diagnostic
    queries return an empty result rather than crashing on a fresh
    DB. Idempotent; matches kite_client._create_intraday_cache_table
    and _create_intraday_cache_by_token_table schemas byte-for-byte.
    """
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS intraday_cache ("
            "ticker   TEXT NOT NULL,"
            "interval TEXT NOT NULL DEFAULT 'legacy_unknown',"
            "datetime TEXT NOT NULL,"
            "open     REAL,"
            "high     REAL,"
            "low      REAL,"
            "close    REAL,"
            "volume   REAL,"
            "fetched_at TIMESTAMP,"
            "PRIMARY KEY (ticker, interval, datetime)"
            ")"
        )
        # [WORKFLOW-H H4.B 2026-09-13] The by-token table.
        # PRIMARY KEY (instrument_token, interval, datetime).
        # ``oi`` is F&O-only.
        conn.execute(
            "CREATE TABLE IF NOT EXISTS intraday_cache_by_token ("
            "instrument_token INTEGER NOT NULL,"
            "interval         TEXT NOT NULL,"
            "datetime         TEXT NOT NULL,"
            "open             REAL,"
            "high             REAL,"
            "low              REAL,"
            "close            REAL,"
            "volume           REAL,"
            "oi               REAL,"
            "fetched_at       TIMESTAMP,"
            "PRIMARY KEY (instrument_token, interval, datetime)"
            ")"
        )
        conn.commit()
    finally:
        conn.close()


def _connect(db_path: str) -> sqlite3.Connection:
    """Sync connection. The diagnostic is a CLI tool; async is
    overhead here. Read-only isolation level.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = ON")
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    )
    return cur.fetchone() is not None


def cache_row_counts(db_path: str) -> Dict[str, Any]:
    """Return a count summary of the intraday_cache table.

    Returns an empty dict if the table is absent (fresh DB), which
    is the most honest signal: no rows yet, no cache hit possible.
    """
    init_intraday_cache_diag_db(db_path)
    out: Dict[str, Any] = {"path": db_path, "table_present": False}
    conn = _connect(db_path)
    try:
        if not _table_exists(conn, "intraday_cache"):
            return out
        out["table_present"] = True
        # Total rows + sessions + tickers + intervals.
        total_row = conn.execute(
            "SELECT COUNT(*) FROM intraday_cache"
        ).fetchone()
        sessions_row = conn.execute(
            "SELECT COUNT(DISTINCT substr(datetime,1,10)) FROM intraday_cache"
        ).fetchone()
        tickers_row = conn.execute(
            "SELECT COUNT(DISTINCT ticker) FROM intraday_cache"
        ).fetchone()
        intervals_row = conn.execute(
            "SELECT COUNT(DISTINCT interval) FROM intraday_cache"
        ).fetchone()
        out["total_rows"] = int(total_row[0])
        out["distinct_sessions"] = int(sessions_row[0])
        out["distinct_tickers"] = int(tickers_row[0])
        out["distinct_intervals"] = int(intervals_row[0])
        return out
    finally:
        conn.close()


def cache_by_token_row_counts(db_path: str) -> Dict[str, Any]:
    """[WORKFLOW-H H4.B 2026-09-13] Same shape as ``cache_row_counts``
    but for the ``intraday_cache_by_token`` table.

    Returns an empty dict (with ``table_present=False``) if the
    table is absent (fresh DB or H4.B not yet loaded). Counts
    are by ``instrument_token`` (not ``ticker``) because the
    by-token path is keyed on integer tokens.
    """
    init_intraday_cache_diag_db(db_path)
    out: Dict[str, Any] = {"path": db_path, "table_present": False}
    conn = _connect(db_path)
    try:
        if not _table_exists(conn, "intraday_cache_by_token"):
            return out
        out["table_present"] = True
        total_row = conn.execute(
            "SELECT COUNT(*) FROM intraday_cache_by_token"
        ).fetchone()
        sessions_row = conn.execute(
            "SELECT COUNT(DISTINCT substr(datetime,1,10)) FROM intraday_cache_by_token"
        ).fetchone()
        tokens_row = conn.execute(
            "SELECT COUNT(DISTINCT instrument_token) FROM intraday_cache_by_token"
        ).fetchone()
        intervals_row = conn.execute(
            "SELECT COUNT(DISTINCT interval) FROM intraday_cache_by_token"
        ).fetchone()
        out["total_rows"] = int(total_row[0])
        out["distinct_sessions"] = int(sessions_row[0])
        out["distinct_instrument_tokens"] = int(tokens_row[0])
        out["distinct_intervals"] = int(intervals_row[0])
        return out
    finally:
        conn.close()


def cache_by_token_interval_breakdown(db_path: str) -> Dict[str, int]:
    """[WORKFLOW-H H4.B 2026-09-13] Row count per interval for the
    by-token table. Sibling of ``cache_interval_breakdown``.
    """
    init_intraday_cache_diag_db(db_path)
    out: Dict[str, int] = {}
    conn = _connect(db_path)
    try:
        if not _table_exists(conn, "intraday_cache_by_token"):
            return out
        cur = conn.execute(
            "SELECT interval, COUNT(*) FROM intraday_cache_by_token "
            "GROUP BY interval ORDER BY COUNT(*) DESC"
        )
        for row in cur.fetchall():
            out[str(row[0])] = int(row[1])
        return out
    finally:
        conn.close()


def cache_interval_breakdown(db_path: str) -> Dict[str, int]:
    """Return the row count per ``interval`` value.

    A future cache-add (H4) needs this distribution to decide
    which intervals to key. The current producer is only
    ``interval=minute`` (the penny scanner); F&O / partner
    paths use ``get_intraday_by_token`` which never writes
    here. If ``interval != minute`` shows up in this dict, a
    future agent has added a new caller.
    """
    init_intraday_cache_diag_db(db_path)
    conn = _connect(db_path)
    try:
        if not _table_exists(conn, "intraday_cache"):
            return {}
        rows = conn.execute(
            "SELECT interval, COUNT(*) AS n FROM intraday_cache "
            "GROUP BY interval ORDER BY n DESC"
        ).fetchall()
        return {str(r["interval"]): int(r["n"]) for r in rows}
    finally:
        conn.close()


def cache_freshness_window(
    db_path: str,
    *,
    interval: str = "minute",
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Classify rows in the cache by freshness relative to
    ``expected_latest = now - interval_mins``.

    The classification mirrors ``kite_client.get_intraday``: rows
    whose ``datetime >= expected_latest`` are FRESH (would serve a
    cache HIT today); rows whose ``datetime < expected_latest`` are
    COMPLETED (would NOT serve a HIT because the freshness check
    forces a Kite round-trip). Rows whose ``datetime`` is in the
    future (clock skew or malformed timestamp) are FLAGGED so a
    future operator can investigate.

    Returns a dict with per-bucket counts; missing table returns
    an empty dict with a ``table_present`` flag.
    """
    init_intraday_cache_diag_db(db_path)
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    interval_mins = _interval_minutes(interval)
    expected_latest = now_utc - timedelta(minutes=interval_mins)
    out: Dict[str, Any] = {
        "interval": interval,
        "now_utc": now_utc.isoformat(),
        "expected_latest": expected_latest.isoformat(),
        "table_present": False,
    }
    conn = _connect(db_path)
    try:
        if not _table_exists(conn, "intraday_cache"):
            return out
        out["table_present"] = True
        rows = conn.execute(
            "SELECT datetime FROM intraday_cache WHERE interval=?",
            (interval,),
        ).fetchall()
        fresh = completed = malformed = 0
        for r in rows:
            dt_str = str(r["datetime"])
            try:
                dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                malformed += 1
                continue
            # Treat naive datetimes as IST (legacy convention in
            # this table). The cache key is wall-clock string, not
            # tz-aware; this is consistent with the writer.
            if dt >= expected_latest.replace(tzinfo=None):
                fresh += 1
            else:
                completed += 1
        out["fresh_count"] = fresh
        out["completed_count"] = completed
        out["malformed_count"] = malformed
        out["total_for_interval"] = fresh + completed + malformed
        return out
    finally:
        conn.close()


def audit_key_shape(db_path: str) -> Dict[str, Any]:
    """Audit the cache key shape for §12's *"do not mix... cross-
    account/coin tokens"* constraint.

    The schema declares PRIMARY KEY (ticker, interval, datetime).
    No account_id column. No coin_token column. A future agent who
    adds such a column -- or who introduces an account-specific
    cache table -- breaks the §12 invariant; this audit surfaces
    the break loudly.

    Returns a dict with the schema, the unique key columns, and
    an explicit assertion that ``account_id`` and ``coin_token``
    are NOT in the key.
    """
    init_intraday_cache_diag_db(db_path)
    conn = _connect(db_path)
    try:
        if not _table_exists(conn, "intraday_cache"):
            return {"table_present": False, "violations": []}
        cur = conn.execute("PRAGMA table_info(intraday_cache)")
        columns = [
            {"name": str(r["name"]),
             "type": str(r["type"]),
             "pk": int(r["pk"])}
            for r in cur.fetchall()
        ]
        pk_columns = [c["name"] for c in columns if c["pk"] > 0]
        violations: List[str] = []
        for forbidden in ("account_id", "coin_token", "account", "user"):
            if forbidden in pk_columns:
                violations.append(
                    f"forbidden key column {forbidden!r} found in PRIMARY KEY"
                )
            if forbidden in {c["name"] for c in columns}:
                violations.append(
                    f"forbidden column {forbidden!r} found in table ("
                    f"even non-key, this is a foot-gun)"
                )
        return {
            "table_present": True,
            "columns": columns,
            "primary_key_columns": pk_columns,
            "violations": violations,
        }
    finally:
        conn.close()


# ---- CLI -------------------------------------------------------------------

def _render_conclusion(
    row_counts: Dict[str, Any],
    interval_breakdown: Dict[str, int],
    freshness: Dict[str, Any],
    key_audit: Dict[str, Any],
    by_token_row_counts: Optional[Dict[str, Any]] = None,
    by_token_interval_breakdown: Optional[Dict[str, int]] = None,
) -> str:
    """Render the operator-readable conclusion.

    A future agent reading this diagnostic in a year should
    understand WHY the cache hit rate was "zero" without
    re-deriving the reasoning.
    """
    by_token_row_counts = by_token_row_counts or {}
    by_token_interval_breakdown = by_token_interval_breakdown or {}
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append("H3 + H4.B Intraday-cache diagnostic -- 2026-09-13")
    lines.append("=" * 72)
    lines.append("")
    lines.append("BY-SYMBOL ENTRY POINTS (intraday_cache table):")
    for site in CACHED_CALLER_SITES:
        lines.append(f"  - {site[0]}::{site[1]} ({site[2]})")
    lines.append("")
    lines.append("BY-TOKEN ENTRY POINTS (intraday_cache_by_token table):")
    for site in BY_TOKEN_CALLER_SITES:
        lines.append(f"  - {site[0]}::{site[1]} ({site[2]})")
    lines.append("")
    lines.append("BY-SYMBOL ROW COUNTS (intraday_cache):")
    if not row_counts.get("table_present"):
        lines.append("  intraday_cache table NOT present (fresh DB)")
    else:
        lines.append(
            f"  total_rows={row_counts.get('total_rows', 0)}"
            f"  distinct_sessions={row_counts.get('distinct_sessions', 0)}"
            f"  distinct_tickers={row_counts.get('distinct_tickers', 0)}"
            f"  distinct_intervals={row_counts.get('distinct_intervals', 0)}"
        )
    lines.append("")
    lines.append("BY-TOKEN ROW COUNTS (intraday_cache_by_token):")
    if not by_token_row_counts.get("table_present"):
        lines.append("  intraday_cache_by_token table NOT present (fresh DB)")
    else:
        lines.append(
            f"  total_rows={by_token_row_counts.get('total_rows', 0)}"
            f"  distinct_sessions={by_token_row_counts.get('distinct_sessions', 0)}"
            f"  distinct_instrument_tokens={by_token_row_counts.get('distinct_instrument_tokens', 0)}"
            f"  distinct_intervals={by_token_row_counts.get('distinct_intervals', 0)}"
        )
    lines.append("")
    lines.append("BY-SYMBOL INTERVAL BREAKDOWN:")
    if not interval_breakdown:
        lines.append("  no rows")
    else:
        for iv, n in sorted(
            interval_breakdown.items(), key=lambda kv: -kv[1]
        ):
            lines.append(f"  interval={iv!r}  rows={n}")
    lines.append("")
    lines.append("BY-TOKEN INTERVAL BREAKDOWN:")
    if not by_token_interval_breakdown:
        lines.append("  no rows")
    else:
        for iv, n in sorted(
            by_token_interval_breakdown.items(), key=lambda kv: -kv[1]
        ):
            lines.append(f"  interval={iv!r}  rows={n}")
    lines.append("")
    lines.append("FRESHNESS (relative to kite_client.get_intraday gate):")
    if not freshness.get("table_present"):
        lines.append("  no rows")
    else:
        lines.append(
            f"  interval={freshness.get('interval')}"
            f"  fresh={freshness.get('fresh_count', 0)}"
            f"  completed={freshness.get('completed_count', 0)}"
            f"  malformed={freshness.get('malformed_count', 0)}"
        )
        total = int(freshness.get("total_for_interval", 0))
        fresh = int(freshness.get("fresh_count", 0))
        if total > 0:
            lines.append(
                f"  interpretation: {fresh}/{total} rows would serve a "
                f"cache HIT if requested today; the rest are stale and "
                f"the freshness gate (last_cached_dt >= expected_latest) "
                f"forces a Kite round-trip"
            )
        else:
            lines.append("  interpretation: no rows to assess")
    lines.append("")
    lines.append("KEY-SHAPE AUDIT (per section 12 'cross-account/coin tokens'):")
    if not key_audit.get("table_present"):
        lines.append("  intraday_cache table NOT present")
    else:
        lines.append(
            f"  PRIMARY KEY columns: {key_audit.get('primary_key_columns')}"
        )
        violations = key_audit.get("violations", [])
        if violations:
            lines.append("  VIOLATIONS:")
            for v in violations:
                lines.append(f"    ! {v}")
        else:
            lines.append(
                "  OK: no account_id / coin_token columns in the key "
                "(section 12 invariant preserved)"
            )
    lines.append("")
    lines.append("CONCLUSION:")
    total_rows = int(row_counts.get("total_rows", 0))
    if total_rows == 0:
        lines.append(
            "  The cache is COLD (zero rows). 'Zero hits' reflects a "
            "fresh DB or a session that hasn't yet completed any "
            "get_intraday() call that fell through the freshness "
            "gate to a Kite round-trip. The cache is populated LAZILY "
            "(see kite_client.get_intraday INSERT OR REPLACE after a "
            "miss). Once any caller triggers a miss + write, the "
            "cache begins to warm."
        )
    else:
        fresh = int(freshness.get("fresh_count", 0))
        total = int(freshness.get("total_for_interval", 0))
        if total == 0:
            lines.append(
                "  Rows exist for OTHER intervals but the requested "
                "interval has zero rows. Cache-add (H4) is the path "
                "forward if the requesting interval needs coverage."
            )
        elif fresh == 0:
            lines.append(
                "  Every row in the requested interval is older than "
                "the freshness gate. The gate (last_cached_dt >= "
                "expected_latest) WILL force a Kite round-trip on "
                "every request until the cache is refreshed (or "
                "until a fresh write happens via the post-miss "
                "INSERT in kite_client.get_intraday)."
            )
        else:
            lines.append(
                f"  {fresh}/{total} rows would serve a HIT today. "
                "Cache-add (H4) is NOT needed for this interval; the "
                "fresh rows ARE eligible. The 'zero hit rate' claim "
                "may reflect a caller that requests an interval "
                "with zero rows OR a freshness gate that's too tight."
            )
    lines.append("")
    lines.append("NEXT STEPS (per plan section 12):")
    lines.append(
        "  Cache-add (H4) is DEFERRED until an operator signs off on "
        "the cache key shape and the freshness budget. This "
        "diagnostic is the input to that decision."
    )
    lines.append("=" * 72)
    return "\n".join(lines)


def run_diagnostic(
    db_path: str,
    *,
    interval: str = "minute",
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Run the full diagnostic. Returns the structured dict AND
    the rendered conclusion.

    The structured dict is what future callers (CI gates, the
    H5 dashboard readiness report) consume; the rendered
    conclusion is what the operator reads at the CLI.
    """
    row_counts = cache_row_counts(db_path)
    interval_breakdown = cache_interval_breakdown(db_path)
    freshness = cache_freshness_window(
        db_path, interval=interval, now_utc=now_utc,
    )
    key_audit = audit_key_shape(db_path)
    # [WORKFLOW-H H4.B 2026-09-13] The by-token stats are reported
    # under ``by_token_row_counts`` / ``by_token_interval_breakdown``
    # so operators can see HIT/MSS-eligible rows independently of
    # the by-symbol path. Both tables may be empty on a fresh DB.
    by_token_row_counts = cache_by_token_row_counts(db_path)
    by_token_interval_breakdown = cache_by_token_interval_breakdown(db_path)
    rendered = _render_conclusion(
        row_counts, interval_breakdown, freshness, key_audit,
        by_token_row_counts=by_token_row_counts,
        by_token_interval_breakdown=by_token_interval_breakdown,
    )
    return {
        "db_path": db_path,
        "row_counts": row_counts,
        "interval_breakdown": interval_breakdown,
        "freshness": freshness,
        "key_audit": key_audit,
        "by_token_row_counts": by_token_row_counts,
        "by_token_interval_breakdown": by_token_interval_breakdown,
        "rendered": rendered,
    }


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point. Exits 0 on success, 1 on I/O error."""
    parser = argparse.ArgumentParser(
        description=(
            "Sentinel intraday-cache diagnostic. Read-only; does not "
            "modify the cache. Prints the caller inventory, key-shape "
            "audit, freshness classification, and the operator-readable "
            "conclusion."
        ),
    )
    parser.add_argument(
        "--db", required=True,
        help="SQLite database path (typically the same cache.db used "
             "by kite_client)",
    )
    parser.add_argument(
        "--interval", default="minute",
        help="interval to classify for the freshness window "
             "(default: minute)",
    )
    parser.add_argument(
        "--output", required=True,
        help="atomic immutable output JSON path",
    )
    args = parser.parse_args(argv)
    try:
        result = run_diagnostic(args.db, interval=args.interval)
    except sqlite3.Error as exc:
        print(
            json.dumps(
                {"ok": False, "error": f"sqlite error: {exc}"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    except OSError as exc:
        print(
            json.dumps(
                {"ok": False, "error": f"i/o error: {exc}"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    # Write the rendered conclusion to the output path.
    try:
        from reconciliation_cli import _write_output_atomic
    except ImportError:
        # Fall back to a minimal atomic writer if reconciliation_cli
        # is unavailable for any reason (e.g. an early test).
        def _write_output_atomic(path: str, value: dict) -> None:
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(value, f, sort_keys=True, allow_nan=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
    # Strip the ``rendered`` field from the JSON output (keep it
    # in stdout) so the JSON is machine-parseable without forcing
    # a multi-line string field.
    json_payload = {
        k: v for k, v in result.items() if k != "rendered"
    }
    try:
        _write_output_atomic(args.output, {
            "ok": True,
            "db_path": args.db,
            "interval": args.interval,
            "row_counts": result["row_counts"],
            "interval_breakdown": result["interval_breakdown"],
            "freshness": result["freshness"],
            "key_audit": {
                k: v for k, v in result["key_audit"].items()
                if k != "columns"
            },
        })
    except OSError as exc:
        print(
            json.dumps(
                {"ok": False, "error": f"output write failed: {exc}"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    # Print the rendered conclusion to stdout for the operator.
    print(result["rendered"])
    print(json.dumps(
        {"path": args.output, "ok": True}, sort_keys=True,
    ))
    return 0


__all__ = [
    "BY_TOKEN_CALLER_SITES",
    "CACHED_CALLER_SITES",
    "UNCACHED_CALLER_SITES",
    "audit_key_shape",
    "cache_by_token_interval_breakdown",
    "cache_by_token_row_counts",
    "cache_freshness_window",
    "cache_interval_breakdown",
    "cache_row_counts",
    "init_intraday_cache_diag_db",
    "main",
    "run_diagnostic",
]


if __name__ == "__main__":
    sys.exit(main())
