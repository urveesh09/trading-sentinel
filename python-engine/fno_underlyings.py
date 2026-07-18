"""
[PARTNER-TIPS 2026-07-18] Multi-underlying registry for F&O analytics
(partner tips bot, plan feat/partner-tips-bot WS1).

The trading path stays single-underlying (FNO_UNDERLYING=NIFTY, spec
"NIFTY only in P1") and is NOT routed through this module. This registry
exists for the read-only analytics/signal-generation side: NIFTY +
BANKNIFTY on NFO, SENSEX on BFO (BSE F&O).

Hard rules:
  - ONE instruments-dump fetch per SEGMENT per refresh (an NFO dump is
    60-90k rows; fetching it twice for NIFTY and BANKNIFTY would double
    the 38-minute cold-start pathology ops rule 61 exists to prevent).
  - A BANKNIFTY/SENSEX failure must NEVER sink the NIFTY refresh: the
    NIFTY book feeds the live paper-trading path; the others feed tips.
  - SENSEX ships signal_enabled=False until scripts/verify_bfo.py has
    passed against live Kite (BFO token-form quotes + futures volume
    quality are unverified, plan WS6).
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from typing import Dict, List, Optional

import structlog

from config import settings
from fno_instruments import FnoInstruments

logger = structlog.get_logger()

FNO_UNDERLYING_NAMES_PATH = "/data/fno_underlying_names.json"


@dataclass(frozen=True)
class UnderlyingSpec:
    """Static description of one analytics underlying. Per-underlying
    numeric params (OR minutes, RVOL floor) default to the global FNO_*
    settings when None -- override only with data, never taste."""
    name: str                       # "NIFTY" | "BANKNIFTY" | "SENSEX"
    segment: str                    # "NFO" | "BFO"
    signal_enabled: bool = True     # ORB signal-gen for partner tips
    or_minutes: Optional[int] = None
    min_rvol: Optional[float] = None


SPECS: Dict[str, UnderlyingSpec] = {
    "NIFTY": UnderlyingSpec("NIFTY", "NFO"),
    "BANKNIFTY": UnderlyingSpec("BANKNIFTY", "NFO"),
    # signal_enabled flips to True only after WS6 verification: BSE index
    # futures volume may be too thin for an honest RVOL baseline, in
    # which case ORB signals are structurally absent and only the chain
    # analytics (options ARE liquid on BFO) carry value.
    "SENSEX": UnderlyingSpec("SENSEX", "BFO", signal_enabled=False),
}


def analytics_underlyings() -> List[UnderlyingSpec]:
    """Specs selected by FNO_ANALYTICS_UNDERLYINGS, unknown names logged
    and skipped (a typo in .env must degrade, not crash the scheduler)."""
    out: List[UnderlyingSpec] = []
    for raw in settings.FNO_ANALYTICS_UNDERLYINGS.split(","):
        name = raw.strip().upper()
        if not name:
            continue
        spec = SPECS.get(name)
        if spec is None:
            logger.warning("fno_underlyings_unknown name=%s -- skipped", name)
            continue
        out.append(spec)
    return out


def instruments_path(name: str) -> str:
    """Disk snapshot path per underlying. NIFTY keeps the legacy path so
    the trading path's cold-start rehydration is byte-for-byte unchanged."""
    if name.upper() == "NIFTY":
        return settings.FNO_INSTRUMENTS_JSON_PATH
    return f"/data/fno_{name.lower()}_instruments.json"


# ---------------------------------------------------------------------------
# per-underlying book registry
# ---------------------------------------------------------------------------

_books: Dict[str, FnoInstruments] = {}


def get_instruments_for(name: str) -> FnoInstruments:
    """Book for one underlying. NIFTY delegates to the existing module
    singleton so analytics and the trading path share ONE book (one
    refresh, one disk snapshot, no drift between the two views).

    The NIFTY singleton is resolved through the fno_instruments module at
    CALL time (not bound at import) -- the test suite patches it by name,
    the same discipline scheduler_setup documents for main.*."""
    name = name.upper()
    if name == "NIFTY":
        import fno_instruments as _fi
        return _fi.get_fno_instruments()
    book = _books.get(name)
    if book is None:
        spec = SPECS[name]
        book = FnoInstruments(
            underlying=name, segment=spec.segment,
            json_path=instruments_path(name),
        )
        book.load_from_disk()
        _books[name] = book
    return book


def _persist_underlying_names(raw_nfo_csv: str) -> None:
    """Distinct `name` column of the NFO dump = the F&O-listed underlying
    set (index + stock). The momentum stock-option cue filters against
    this file. Atomic write (tmp+rename, 2026-07-13 truncate lesson)."""
    try:
        import csv as _csv
        import io as _io
        names = sorted({
            (rec.get("name") or "").strip().upper()
            for rec in _csv.DictReader(_io.StringIO(raw_nfo_csv))
            if (rec.get("name") or "").strip()
        })
        if not names:
            return
        path = FNO_UNDERLYING_NAMES_PATH
        os.makedirs(os.path.dirname(path), exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".fno-names-")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump({"names": names}, f)
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        logger.info("fno_underlying_names_persisted count=%d", len(names))
    except Exception as exc:
        logger.warning("fno_underlying_names_persist_failed err=%s", str(exc))


def load_underlying_names() -> set:
    try:
        with open(FNO_UNDERLYING_NAMES_PATH) as f:
            return set(json.load(f).get("names", []))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return set()


async def refresh_all(kite) -> Dict[str, bool]:
    """Refresh every analytics book: ONE dump fetch per segment, shared
    across that segment's underlyings. Returns {name: ok}. Callers judge
    the trading path on the NIFTY entry alone."""
    specs = analytics_underlyings()
    # NIFTY is non-negotiable: the daily_bootstrap task delegates the
    # trading path's book refresh here, so an .env that trims the
    # analytics list must never silently starve the live NIFTY book.
    if not any(s.name == "NIFTY" for s in specs):
        specs.insert(0, SPECS["NIFTY"])
    results: Dict[str, bool] = {}
    by_segment: Dict[str, List[UnderlyingSpec]] = {}
    for s in specs:
        by_segment.setdefault(s.segment, []).append(s)

    for segment, seg_specs in by_segment.items():
        try:
            raw = await kite.get_instruments_dump(segment)
        except Exception as exc:
            logger.error(
                "fno_underlyings_dump_failed segment=%s err=%s", segment, str(exc)
            )
            raw = ""
        if not raw:
            for s in seg_specs:
                results[s.name] = False
            continue
        if segment == "NFO":
            _persist_underlying_names(raw)
        for s in seg_specs:
            try:
                results[s.name] = get_instruments_for(s.name).load_from_raw(raw)
            except Exception as exc:
                logger.error(
                    "fno_underlyings_refresh_failed name=%s err=%s", s.name, str(exc)
                )
                results[s.name] = False

    logger.info(
        "fno_underlyings_refresh_all results=%s",
        ",".join(f"{k}={v}" for k, v in results.items()),
    )
    return results
