"""
[FNO-INSTRUMENTS 2026-07-10] NFO instrument dump -> keyed contract maps
(spec §6.1).

GET /instruments/NFO returns 60,000-90,000 rows. We keep ONLY the
FNO_UNDERLYING (NIFTY) rows -- a few thousand -- in our own structure,
keyed (name, expiry, strike, instrument_type) -> Contract, plus a
tradingsymbol side map. It is NEVER poured into kite_client's flat
equity instrument_cache (symbol collisions + rule-61 cold-start bloat).

From the dump we READ, never hardcode (spec §14):
  - lot_size      (VERIFY-2: revised Nov 2024 and possibly since)
  - strike step   (derived from the nearest expiry's strike ladder)
  - expiry dates  (VERIFY-3: the weekly expiry day changed several
                   times in 2025; the calendar IS the dump)

Cold-start rule (spec §15 open question 3, answered YES): the filtered
rows persist to FNO_INSTRUMENTS_JSON_PATH after every refresh and
re-hydrate from disk at import-init if the file is fresh (same IST day).
A morning container restart therefore does NOT miss the 09:45 entry
window waiting on a 38-minute dump download.
"""
from __future__ import annotations

import csv
import io
import json
import os
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

import pytz
import structlog

from config import settings
from fno_models import Contract, OptionType

logger = structlog.get_logger()
IST = pytz.timezone("Asia/Kolkata")


class FnoInstruments:
    """In-memory NIFTY contract book, refreshed daily at 08:00 IST."""

    def __init__(
        self,
        underlying: Optional[str] = None,
        segment: str = "NFO",
        json_path: Optional[str] = None,
    ):
        # [PARTNER-TIPS 2026-07-18] segment + json_path parameterized so
        # the analytics registry (fno_underlyings) can hold BANKNIFTY/NFO
        # and SENSEX/BFO books. Defaults reproduce the original NIFTY
        # behavior exactly; json_path=None resolves lazily to the legacy
        # settings path so test-time settings patches still apply.
        self.underlying = (underlying or settings.FNO_UNDERLYING).upper()
        self.segment = segment.upper()
        self._json_path = json_path
        self.refreshed_on: Optional[date] = None   # IST date of last refresh
        self.by_key: Dict[Tuple[str, str, float, str], Contract] = {}
        self.by_symbol: Dict[str, Contract] = {}
        self.option_expiries: List[date] = []
        self.future_expiries: List[date] = []
        self._lot_size: int = 0
        self._strike_step: float = 0.0

    # ------------------------------------------------------------------
    # refresh / persistence
    # ------------------------------------------------------------------

    def _path(self) -> str:
        return self._json_path or settings.FNO_INSTRUMENTS_JSON_PATH

    async def refresh(self, kite) -> bool:
        """Fetch + parse the segment dump. Returns True on success. On
        failure the previous in-memory book (if any) is kept -- stale beats
        empty intraday, and the staleness guard in ready() still gates
        entries."""
        raw = await kite.get_instruments_dump(self.segment)
        if not raw:
            logger.error(
                "fno_instruments_refresh_failed reason=empty_dump "
                "FIX=check Kite auth + VERIFY-6 (plan must include %s)",
                self.segment,
            )
            return False
        return self.load_from_raw(raw)

    def load_from_raw(self, raw: str) -> bool:
        """Parse + load + persist from an already-fetched dump CSV.
        Split out of refresh() so fno_underlyings.refresh_all can feed
        one NFO dump to both the NIFTY and BANKNIFTY books."""
        contracts = self._parse_csv(raw)
        if not contracts:
            logger.error(
                "fno_instruments_refresh_failed reason=no_%s_rows_in_dump",
                self.underlying,
            )
            return False
        self._load_contracts(contracts)
        self.refreshed_on = datetime.now(IST).date()
        self._persist()
        # Rule 55 companion summary: surface the inputs, loudly.
        logger.info(
            "fno_instruments_refreshed underlying=%s contracts=%d lot_size=%d "
            "strike_step=%.0f nearest_opt_expiry=%s future_expiries=%d",
            self.underlying, len(contracts), self._lot_size, self._strike_step,
            self.option_expiries[0].isoformat() if self.option_expiries else "none",
            len(self.future_expiries),
        )
        return True

    def _parse_csv(self, raw: str) -> List[Contract]:
        out: List[Contract] = []
        reader = csv.DictReader(io.StringIO(raw))
        for rec in reader:
            try:
                if (rec.get("name") or "").strip().upper() != self.underlying:
                    continue
                itype = (rec.get("instrument_type") or "").strip().upper()
                if itype not in ("CE", "PE", "FUT"):
                    continue
                expiry_raw = (rec.get("expiry") or "").strip()
                if not expiry_raw:
                    continue
                out.append(Contract(
                    token=int(rec["instrument_token"]),
                    tradingsymbol=(rec.get("tradingsymbol") or "").strip().upper(),
                    name=self.underlying,
                    expiry=date.fromisoformat(expiry_raw[:10]),
                    strike=float(rec.get("strike") or 0.0),
                    instrument_type=itype,
                    lot_size=int(rec.get("lot_size") or 0),
                    tick_size=float(rec.get("tick_size") or settings.FNO_TICK_SIZE),
                ))
            except (KeyError, ValueError, TypeError):
                continue  # malformed row; skip silently like the equity parser
        return out

    def _load_contracts(self, contracts: List[Contract]) -> None:
        self.by_key.clear()
        self.by_symbol.clear()
        opt_expiries = set()
        fut_expiries = set()
        lot_sizes: Dict[int, int] = {}
        for c in contracts:
            self.by_key[(c.name, c.expiry.isoformat(), c.strike, c.instrument_type)] = c
            self.by_symbol[c.tradingsymbol] = c
            if c.instrument_type in ("CE", "PE"):
                opt_expiries.add(c.expiry)
                lot_sizes[c.lot_size] = lot_sizes.get(c.lot_size, 0) + 1
            else:
                fut_expiries.add(c.expiry)
        self.option_expiries = sorted(opt_expiries)
        self.future_expiries = sorted(fut_expiries)
        # lot_size: modal value across option rows (defensive against a
        # few in-transition rows after a SEBI lot revision).
        self._lot_size = max(lot_sizes, key=lot_sizes.get) if lot_sizes else 0
        self._strike_step = self._derive_strike_step()

    def _derive_strike_step(self) -> float:
        if not self.option_expiries:
            return 0.0
        nearest = self.option_expiries[0].isoformat()
        strikes = sorted({
            k[2] for k in self.by_key
            if k[1] == nearest and k[3] == "CE" and k[2] > 0
        })
        diffs = [b - a for a, b in zip(strikes, strikes[1:]) if b - a > 0]
        return min(diffs) if diffs else 0.0

    def _persist(self) -> None:
        """Best-effort disk snapshot for same-day rehydration."""
        try:
            path = self._path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            payload = {
                "underlying": self.underlying,
                "refreshed_on": self.refreshed_on.isoformat() if self.refreshed_on else None,
                # by_key is the authoritative map: iterating by_symbol
                # would silently drop contracts if two rows ever shared a
                # tradingsymbol.
                "contracts": [
                    {
                        "token": c.token, "tradingsymbol": c.tradingsymbol,
                        "expiry": c.expiry.isoformat(), "strike": c.strike,
                        "instrument_type": c.instrument_type,
                        "lot_size": c.lot_size, "tick_size": c.tick_size,
                    }
                    for c in self.by_key.values()
                ],
            }
            with open(path, "w") as f:
                json.dump(payload, f)
        except Exception as exc:
            logger.warning("fno_instruments_persist_failed err=%s", str(exc))

    def load_from_disk(self) -> bool:
        """Rehydrate if the snapshot is from TODAY (IST). A yesterday
        snapshot is refused: expiries/tokens may have rolled overnight."""
        try:
            path = self._path()
            if not os.path.exists(path):
                return False
            with open(path) as f:
                payload = json.load(f)
            snap_day = payload.get("refreshed_on")
            if snap_day != datetime.now(IST).date().isoformat():
                logger.info(
                    "fno_instruments_disk_snapshot_stale snap=%s today=%s -- "
                    "waiting for the 08:00 refresh", snap_day,
                    datetime.now(IST).date().isoformat(),
                )
                return False
            contracts = [
                Contract(
                    token=int(c["token"]), tradingsymbol=c["tradingsymbol"],
                    name=self.underlying, expiry=date.fromisoformat(c["expiry"]),
                    strike=float(c["strike"]), instrument_type=c["instrument_type"],
                    lot_size=int(c["lot_size"]), tick_size=float(c["tick_size"]),
                )
                for c in payload.get("contracts", [])
            ]
            if not contracts:
                return False
            self._load_contracts(contracts)
            self.refreshed_on = date.fromisoformat(snap_day)
            logger.info(
                "fno_instruments_rehydrated_from_disk contracts=%d lot_size=%d",
                len(contracts), self._lot_size,
            )
            return True
        except Exception as exc:
            logger.warning("fno_instruments_rehydrate_failed err=%s", str(exc))
            return False

    # ------------------------------------------------------------------
    # queries
    # ------------------------------------------------------------------

    def ready(self, today_ist: date) -> bool:
        """Fresh book from today. Entries are gated on this."""
        return bool(self.by_key) and self.refreshed_on == today_ist

    @property
    def lot_size(self) -> int:
        return self._lot_size

    @property
    def strike_step(self) -> float:
        return self._strike_step

    def nearest_option_expiry(self, today_ist: date) -> Optional[date]:
        for e in self.option_expiries:
            if e >= today_ist:
                return e
        return None

    def is_expiry_day(self, today_ist: date) -> bool:
        return today_ist in self.option_expiries

    def front_future(self, today_ist: date) -> Optional[Contract]:
        for e in self.future_expiries:
            if e >= today_ist:
                return self.by_key.get((self.underlying, e.isoformat(), 0.0, "FUT"))
        return None

    def option(self, expiry: date, strike: float, opt_type: OptionType) -> Optional[Contract]:
        return self.by_key.get(
            (self.underlying, expiry.isoformat(), float(strike), opt_type.value)
        )

    def atm_strike(self, forward: float) -> float:
        if self._strike_step <= 0:
            return 0.0
        return round(forward / self._strike_step) * self._strike_step

    def strikes_window(self, forward: float, window: int) -> List[float]:
        """ATM +/- window strikes that actually exist for the nearest expiry."""
        atm = self.atm_strike(forward)
        if atm <= 0:
            return []
        return [atm + i * self._strike_step for i in range(-window, window + 1)]


# Module-level singleton, mirroring the penny universe pattern.
_instruments: Optional[FnoInstruments] = None


def get_fno_instruments() -> FnoInstruments:
    global _instruments
    if _instruments is None:
        _instruments = FnoInstruments()
        _instruments.load_from_disk()
    return _instruments
