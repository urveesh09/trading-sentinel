"""Compare the round-nine calendar decision with the November 5 receipt."""
import json

from round9_data import HERE, LOCAL, get, parse, relative
from anatomy import read

DAY = "2026-11-05"
PREVIOUS = "2026-11-04"


def main():
    path = HERE / "round9-nov5.json"
    closes = read(HERE / "nov5-capital-results.json")
    sources = {}
    for exchange in ("NSE", "BSE"):
        job = exchange, PREVIOUS
        _, _, status = get(job)
        assert status in ("saved", "cached"), (exchange, status)
        sha, options, futures = parse(exchange, LOCAL / relative(*job), PREVIOUS)
        nearest = next(expiry for expiry in options if expiry >= DAY)
        sources[exchange] = {"sha256": sha, "front_option_expiry": nearest,
                             "front_future_expiry": next((x for x in futures if x >= DAY), None)}
    allowed = sources["NSE"]["front_option_expiry"] == DAY and sources["BSE"]["front_option_expiry"] > DAY
    assert not allowed, sources
    assert closes["held_exit_parity"] == 3
    result = {
        "day": DAY, "before_session_exchange_report_date": PREVIOUS,
        "sources": sources, "calendar_sleeve_eligible": allowed, "additional_sleeve_orders": 0,
        "recorded_nifty_single_net": closes["paper_singles"],
        "separate_recorded_defined_risk_net": closes["paper_defined_risk_recorded"],
        "scope": "Fixed observed opening state and date eligibility. Historical strategy cash carries not substituted.",
    }
    with path.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, sort_keys=True)
        handle.write("\n")
    print(result)


if __name__ == "__main__":
    main()
