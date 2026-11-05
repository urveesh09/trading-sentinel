"""Disaggregate the frozen straddle price refusal without changing any admission."""
import hashlib
import json
import math
from pathlib import Path

import round16 as s

HERE = Path(__file__).resolve().parent


class AuditReplay(s.StraddleReplay):
    def __init__(self, *args):
        super().__init__(*args)
        self.refusals = []

    def _entry(self, book, obs, frame, day, now):
        before = self.notes["straddle_price_refused"]
        super()._entry(book, obs, frame, day, now)
        if self.notes["straddle_price_refused"] == before:
            return
        expiry = next(e for e in self.data.option_expiries()[0] if e >= now.date())
        atm = 50 * math.floor(obs.future.ltp / 50 + .5)
        asks = {q.contract.instrument_type: self.mark(obs, token, now, buying=True)
                for token, q in obs.options.items()
                if q.contract.expiry == expiry and q.contract.strike == atm and q.contract.lot_size == s.LOT}
        width = s.width_after_compression(frame, day, now)
        debit = sum(asks[side] for side in ("CE", "PE"))
        reserve = s.reserve(asks[side] for side in ("CE", "PE"))
        cap = min(9000., s.settings.FNO_MAX_OPEN_PREMIUM_PCT * book.equity)
        width_failed, cash_failed = debit > width, reserve > cap
        assert width_failed or cash_failed
        self.refusals.append({"at": now.isoformat(), "expiry": expiry.isoformat(), "strike": atm,
                              "opening_width": width, "pair_ask": debit, "full_reserve": reserve,
                              "wallet_bound": cap, "width_failed": width_failed, "cash_failed": cash_failed})


def main():
    s.r.verify_freeze()
    cfg = json.loads((HERE / "round16-freeze.json").read_bytes())
    for name, digest in cfg["files"].items():
        assert hashlib.sha256((HERE / name).read_text(encoding="utf-8").encode()).hexdigest() == digest
    dataset = s.r.DATASETS[s.r.YEAR]
    manifest = json.loads((dataset / "manifest.json").read_bytes())
    with (dataset / "breeze.sqlite").open("rb") as handle:
        assert hashlib.file_digest(handle, "sha256").hexdigest() == manifest["files_sha256"]["breeze.sqlite"]
    original_path = HERE / f"round16-{s.r.YEAR}.json"
    original = json.loads(original_path.read_bytes())[s.NAME]
    s.r.f.Z.N.B.O27F.deny_network()
    s.r.f.Z.N.B.L._init()
    with s.Y.ROUTER.dispatch():
        engine = AuditReplay(s.Y.dataset("year"), s.book_for_run(), s.Y.table("year"), "year")
        data = engine.run(*s.r.WINDOW)
    for row in data["trades"]:
        row.setdefault("status", "CLOSED" if row.get("net_pnl") is not None else "UNRESOLVED")
    assert s.r.metrics(data) == original
    assert len(engine.refusals) == original["notes"]["straddle_price_refused"]
    out = {"source_receipt_sha256": hashlib.sha256(original_path.read_bytes()).hexdigest(),
           "refusals": engine.refusals}
    with (HERE / f"round16-audit-{s.r.YEAR}.json").open("x", encoding="utf-8") as handle:
        json.dump(out, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(s.r.YEAR, len(engine.refusals), flush=True)


if __name__ == "__main__":
    main()
