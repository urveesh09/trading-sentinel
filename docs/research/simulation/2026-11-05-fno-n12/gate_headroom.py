"""Attribute historical low-volatility gate headroom using fixed outcomes only."""
from datetime import datetime
import json
from pathlib import Path

from anatomy import trades
import round1 as r

HERE = Path(__file__).resolve().parent


def summarize(rows):
    return {"count": len(rows), "winners": sum(net > 0. for net in rows),
            "net": round(sum(rows), 2), "positive_only": round(sum(max(net, 0.) for net in rows), 2),
            "losses_removed_oracle": round(sum(max(-net, 0.) for net in rows), 2)}


def main():
    r.verify_freeze()
    _, reference = trades(r.YEAR, "N11T")
    assert r.money(reference) == r.money(r.raw_for(r.books()["N11T"]))
    native = [row for row in reference["trades"] if row["status"] == "CLOSED"]
    all_nets = [row["net_pnl"] for row in native]
    low, above = [], []
    for row in native:
        at = datetime.fromisoformat(row["entry_time"])
        (above if r.f.L.vol_at(at, .9) else low).append(row["net_pnl"])
    shadow_stood_aside = []
    for _, row in r.f.L.U.paper_rows():
        at = datetime.fromisoformat(row["entry_time"])
        if not r.WINDOW[0] <= at.date().isoformat() <= r.WINDOW[1]:
            continue
        if r.f.L.R.stand_aside(r.f.L.vol_at(at, .9), r.f.L.paper_before(at), 20):
            shadow_stood_aside.append(row["net_pnl"])
    out = {"scope": "Fixed outcomes and sizing, no reallocation, counterfactual or incremental account replay",
           "n11t_all": summarize(all_nets), "n11t_at_or_above_vol_line": summarize(above),
           "n11t_below_or_unknown_vol_line": summarize(low),
           "shadow_entries_with_native_stand_aside_reading": summarize(shadow_stood_aside)}
    with (HERE / f"gate-headroom-{r.YEAR}.json").open("x", encoding="utf-8") as handle:
        json.dump(out, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(r.YEAR, out, flush=True)


if __name__ == "__main__":
    main()
