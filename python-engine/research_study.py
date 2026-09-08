"""Reproducible, explicitly modelled intraday research reports.

The existing F&O backtest is useful for testing the signal/exit policy on
underlying futures bars.  It is *not* historical option execution evidence.
This wrapper freezes the input fingerprint, parameters and chronological
split, reports unresolved/no-fill limitations, and never writes a strategy
qualification by itself.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd

from fno_backtest import run_fno_backtest
from research_archive import ARCHIVE_FORMAT, _atomic_bytes, _canonical_json, _iso, guarded_write

EVIDENCE_UNDERLYING_RESEARCH = "UNDERLYING_RESEARCH"
EVIDENCE_OPTION_CANDLE_MODELLED = "OPTION_CANDLE_MODELLED"


def _normalise_bars(bars: pd.DataFrame) -> pd.DataFrame:
    required = {"open", "high", "low", "close", "volume"}
    if bars is None or bars.empty or not required.issubset(bars.columns):
        raise ValueError("bars require a non-empty datetime index and open/high/low/close/volume")
    frame = bars.copy()
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("bars index must be a DatetimeIndex")
    if frame.index.tz is not None:
        frame.index = frame.index.tz_convert("Asia/Kolkata").tz_localize(None)
    if not frame.index.is_monotonic_increasing or frame.index.has_duplicates:
        raise ValueError("bars must be strictly chronological without duplicate timestamps")
    if (frame[list(required)] < 0).any().any() or (frame["high"] < frame["low"]).any():
        raise ValueError("bars contain invalid negative/range values")
    return frame[["open", "high", "low", "close", "volume"]]


def _fingerprint(frame: pd.DataFrame) -> str:
    csv = frame.to_csv(date_format="%Y-%m-%dT%H:%M:%S", float_format="%.10g")
    return hashlib.sha256(csv.encode("utf-8")).hexdigest()


@guarded_write
def run_modelled_intraday_study(
    bars: pd.DataFrame, *, underlying: str, archive_root: str,
    run_id: str, model_iv: Optional[float] = None, pool: Optional[float] = None,
    development_end: Optional[str] = None,
) -> Dict[str, Any]:
    """Run a deterministic frozen study and publish an immutable report.

    ``development_end`` is a date (YYYY-MM-DD).  When provided, the report
    keeps development and later evaluation results separate; it rejects an
    empty evaluation partition instead of silently reporting an in-sample win.
    """
    name = underlying.upper()
    if name != "NIFTY":
        # fno_backtest intentionally has NIFTY's configured strike/lot/expiry
        # assumptions.  Reusing those for BFO would create a convincing but
        # false SENSEX result; a BFO-calibrated policy must be supplied first.
        raise ValueError("only NIFTY is currently calibrated for this modelled backtest; do not map BFO/SENSEX into NFO assumptions")
    if not run_id or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for char in run_id):
        raise ValueError("run_id must be a safe non-empty identifier")
    frame = _normalise_bars(bars)
    fingerprint = _fingerprint(frame)
    development = frame
    evaluation = None
    if development_end:
        cutoff = pd.Timestamp(development_end)
        development = frame[frame.index.date <= cutoff.date()]
        evaluation = frame[frame.index.date > cutoff.date()]
        if development.empty or evaluation.empty:
            raise ValueError("chronological split must contain both development and evaluation bars")
    results: Dict[str, Any] = {"development": run_fno_backtest(development, iv=model_iv, pool=pool)}
    if evaluation is not None:
        results["evaluation"] = run_fno_backtest(evaluation, iv=model_iv, pool=pool)
    created = datetime.now(timezone.utc)
    report = {
        "format": ARCHIVE_FORMAT, "kind": "modelled_intraday_study", "run_id": run_id,
        "underlying": name, "created_at_utc": _iso(created),
        "evidence_level": EVIDENCE_UNDERLYING_RESEARCH,
        "data": {"bar_count": len(frame), "first_bar": frame.index[0].isoformat(),
                 "last_bar": frame.index[-1].isoformat(), "sha256": fingerprint,
                 "chronological_development_end": development_end},
        "policy": {"implementation": "fno_backtest.run_fno_backtest",
                   "option_pricing": "Black-76 synthetic constant-IV with conservative configured spread",
                   "iv": model_iv, "pool": pool},
        "results": results,
        "qualification": {"automatically_registered": False, "automatically_qualified": False,
                          "reason": "Underlying/modelled study has no synchronous historical option bid/ask/depth or fill evidence."},
        "limitations": [
            "No bid/ask depth, displayed capacity, queue position or multi-leg fill is inferred from bars.",
            "Missing option exit observations remain outside this study, not zero loss or forward-filled evidence.",
            "Results do not establish future profitability or delivery eligibility.",
        ],
    }
    payload = _canonical_json(report) + b"\n"
    digest = hashlib.sha256(payload).hexdigest()
    destination = Path(archive_root) / "studies" / name / run_id / digest
    _atomic_bytes(destination / "report.json", payload)
    return {"dataset_ref": str(destination), "content_sha256": digest, "report": report}
