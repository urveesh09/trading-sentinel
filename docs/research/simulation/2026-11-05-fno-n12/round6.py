"""N012 round six. Measure the value of extra paper premium capacity."""
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import subprocess

import round1 as r
from capital_audit import paper_exposure
from config import settings
from fno_costs import calc_fno_costs
from fno_n11 import parent_loss_at_stop

HERE = Path(__file__).resolve().parent
ENTRY = r.Y.BookReplay._entry


def books():
    base = r.books()["N11T"]
    wide = copy.deepcopy(base)
    wide["label"] = "N12|CAP20"
    wide["cfg"]["FNO_MAX_OPEN_PREMIUM_PCT"] = .20
    locked = copy.deepcopy(base)
    locked.update(label="N12|CAP_LOCKED", n12="CAP_LOCKED")
    return {"CAP20": wide, "CAP_LOCKED": locked}


def parent_is_funded(engine, leg, obs, now):
    if not leg.trail_active or leg.trail_stop_underlying is None or r.f.T.open_children(leg):
        return False
    quote = obs.options.get(leg.token)
    if quote is None or quote.bid <= 0 or quote.bid_quantity < leg.qty or quote.last_trade_time is None:
        return False
    if not 0 <= (now - quote.last_trade_time).total_seconds() <= settings.FNO_MAX_QUOTE_AGE_SEC:
        return False
    side = 1 if leg.direction == "LONG" else -1
    risk = abs(leg.entry_underlying - leg.stop_underlying)
    locked = side * (leg.trail_stop_underlying - leg.entry_underlying)
    if risk <= 0 or locked < .5 * risk or obs.future.ltp <= 0:
        return False
    estimated_loss = parent_loss_at_stop(
        leg.direction, obs.future.ltp, quote.bid, leg.delta_at_entry,
        leg.trail_stop_underlying, leg.entry_premium, leg.premium_stop, leg.qty,
        r.f.T.R.extra_cost(engine.book["cost"], leg.lots), calc_fno_costs,
    )
    return estimated_loss <= 0.


def entry(self, book, obs, frame, day, now):
    if self.book.get("n12") != "CAP_LOCKED" or len(book.open) != 1:
        return ENTRY(self, book, obs, frame, day, now)
    parent = next(iter(book.open.values()))
    if not parent_is_funded(self, parent, obs, now):
        return ENTRY(self, book, obs, frame, day, now)
    cap = settings.FNO_MAX_OPEN_PREMIUM_PCT
    previous_id = book.next_id
    settings.FNO_MAX_OPEN_PREMIUM_PCT = .20
    try:
        result = ENTRY(self, book, obs, frame, day, now)
        if book.next_id > previous_id:
            total = sum(leg.entry_premium * leg.qty for leg in book.open.values())
            if total > cap * book.equity:
                self.notes["n12_above_native_cap_admission"] += 1
        return result
    finally:
        settings.FNO_MAX_OPEN_PREMIUM_PCT = cap


r.Y.BookReplay._entry = entry


def main():
    spec = HERE / "round6-freeze.json"
    rel = spec.relative_to(r.ROOT).as_posix()
    cfg = json.loads(spec.read_bytes())
    assert cfg == json.loads(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=r.ROOT))
    assert all(hashlib.sha256((HERE / name).read_bytes()).hexdigest() == sha for name, sha in cfg["files"].items())
    r.verify_freeze()
    variants = books()
    r.f.Z.N.run_books(variants, 2)
    manifest = json.loads((r.DATASETS[r.YEAR] / "manifest.json").read_bytes())
    out = {}
    for key, book in variants.items():
        raw = r.raw_for(book)
        row = r.metrics(raw)
        days = [d for d in manifest["sessions"] if raw["window"][0] <= d <= raw["window"][1]
                and d not in manifest["weekly_expiry_calendar"]]
        row["exposure"] = paper_exposure(raw["trades"], days) if row["unresolved"] == 0 else None
        out[key] = row
        print(r.YEAR, key, row["net"], row["worst_day"], row["drawdown_pct"],
              row["exposure"], flush=True)
    with (HERE / f"round6-{r.YEAR}.json").open("x", encoding="utf-8") as file:
        json.dump(out, file, indent=2, sort_keys=True)
        file.write("\n")


if __name__ == "__main__":
    main()
