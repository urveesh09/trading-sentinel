"""Check price eligibility behind the original full debit ceiling without scoring a new arm."""
import json
import math
from pathlib import Path

import round19 as study

HERE = Path(__file__).resolve().parent


class PairAudit(study.VolPairReplay):
    def __init__(self, *args):
        super().__init__(*args)
        self.debits = []

    def _entry(self, book, obs, frame, day, now):
        before = self.notes["vol_pair_cash_refused"]
        super()._entry(book, obs, frame, day, now)
        if self.notes["vol_pair_cash_refused"] == before:
            return
        expiry = next(d for d in self.data.option_expiries()[0] if d >= now.date())
        future = obs.future.ltp
        strike = 50 * math.floor(future / 50 + .5)
        quotes = {q.contract.instrument_type: q for q in obs.options.values()
                  if q.contract.expiry == expiry and q.contract.strike == strike and q.contract.lot_size == study.straddle.LOT}
        pair = (quotes["CE"], quotes["PE"])
        asks = {q.contract.token: self.mark(obs, q.contract.token, now, buying=True) for q in pair}
        reserve = study.straddle.reserve(asks.values())
        economics = study.price_test(pair, asks, future, now, study.forecasts()[day][1])
        self.debits.append({"day": day, "required_reserve": reserve,
                            "worst_scenario_net": min(economics[1]) if economics else None})


def main():
    study.verify()
    source = json.loads((HERE / f"round19-{study.r.YEAR}.json").read_bytes())
    study.r.f.Z.N.B.O27F.deny_network()
    study.r.f.Z.N.B.L._init()
    with study.Y.ROUTER.dispatch():
        engine = PairAudit(study.Y.dataset("year"), study.books()[study.PAIR], study.Y.table("year"), "year")
        result = engine.run(*study.r.WINDOW)
    for row in result["trades"]:
        row.setdefault("status", "CLOSED" if row.get("net_pnl") is not None else "UNRESOLVED")
    assert study.r.metrics(result) == source[study.PAIR]
    assert json.loads(json.dumps(study.r.money(result))) == source["economic_tuples"][study.PAIR]
    cases = engine.debits
    assert len(cases) == source[study.PAIR]["notes"]["vol_pair_cash_refused"]
    passes = [row for row in cases if row["worst_scenario_net"] is not None and row["worst_scenario_net"] >= 350.]
    out = {"cash_rejections": len(cases), "pricing_hurdle_passes": len(passes),
           "pricing_hurdle_passes_at_15000_full_reserve": sum(row["required_reserve"] <= 15000. for row in passes),
           "cases": cases}
    with (HERE / f"round19-pair-audit-{study.r.YEAR}.json").open("x", encoding="utf-8") as handle:
        json.dump(out, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(study.r.YEAR, {k: v for k, v in out.items() if k != "cases"}, flush=True)


if __name__ == "__main__":
    main()
