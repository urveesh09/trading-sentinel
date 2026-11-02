"""O30c Tier 2 - cases suggested by the investigation (diagnose_c.py). Research only; no runtime module imports this.

These were FOUND BY LOOKING at both NIFTY years, so their scores on 2025 + 2026 are in-sample and prove nothing. They
are frozen here with the rule for the clean test they still need (NIFTY 2024, never used; then the forward panel).
What the investigation showed (diagnosis.json):
  * the two breakout strategies (SHIPPED, OR20) made money with the daily trend direction and lost against it in
    both years (DMI and 20-day EMA); TPB and EFF flipped between years, so a direction rule on all four failed;
  * TPB made most of its 2025 money on the days the ADX gate kept it out (Tier 1's tpb_all_days, which missed the
    rule by Rs 680 in 2026);
  * the four strategies lost on entries before 10:00 and after 14:00 in both years;
  * of the day features, only a larger-than-usual 20-day move (ret20_abs HIGH) was better in all four half-years.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lab_c as C  # noqa: E402  (the year setup, the direction sides, Tier 1's routing)

Y, G, replay, ROUTER = C.Y, C.G, C.replay, C.ROUTER
BREAKOUTS = ("SHIPPED", "OR20")
WINDOW_MIN = (600, 840)          # a signal bar ending at 10:00 .. 13:55 (entries 10:00 - 13:59)


def route(self, frame, regime, now):
    case = self.book.get("case")
    if not case or self.warm or case in C.CASES:
        return C.route(self, frame, regime, now)
    rules = set(case.split("+"))
    bar_ts = replay._last_closed_bar(frame, now)
    if "window_10_14" in rules and bar_ts:
        end = int(bar_ts[11:13]) * 60 + int(bar_ts[14:16]) + 5
        if not WINDOW_MIN[0] <= end < WINDOW_MIN[1]:
            return G.MomSignal(bar_ts=bar_ts, reject_reason="case:outside_10_14")
    row = self.table.get(now.date().isoformat())
    allow = C.wanted("dmi", row)
    for i, m in enumerate(self.members):
        if not ROUTER.allowed(m["gate"], row):
            continue
        sig = self._signal(i, frame, regime, now, bar_ts)
        if sig.direction is None:
            continue
        if "dmi_breakouts" in rules and m["name"] in BREAKOUTS and sig.direction != allow:
            self.notes["case_breakout_against_trend"] += 1
            continue
        self._fired = i
        return sig
    return G.MomSignal(bar_ts=bar_ts or "", reject_reason="book:no_member")


Y.BookReplay.route = route


def books() -> dict:
    live, union = C.four(lambda c: C.ADX), C.four(lambda c: "ALWAYS")
    tpb_days = C.four(lambda c: "ALWAYS" if c == "TPB" else C.ADX)
    return {"LIVE": C.book(live),
            "LIVE+tpb_all_days": C.book(tpb_days),
            "LIVE+breakouts_with_trend": C.book(live, "dmi_breakouts"),
            "LIVE+tpb_all_days+breakouts_with_trend": C.book(tpb_days, "dmi_breakouts"),
            "LIVE+tpb_all_days+10_to_14": C.book(tpb_days, "window_10_14"),
            "LIVE+tpb_all_days+breakouts_with_trend+10_to_14": C.book(tpb_days, "dmi_breakouts+window_10_14"),
            "UNION+breakouts_with_trend": C.book(union, "dmi_breakouts"),
            "UNION|ret20_abs:HIGH": C.book(C.four(lambda c: "ret20_abs:HIGH"))}


RULE = {
    "status": "IN-SAMPLE: found by looking at 2025 + 2026; their scores there are description, not proof",
    "clean_test": "on NIFTY 2024 (unseen; once downloaded) a case is confirmed only if, per lot, it beats LIVE "
                  "(UNION_ADX) over the year and is not worse in either half; the same test applies to Tier 1's "
                  "tpb_all_days; then the forward panel",
    "no_change": "nothing in the system changes on this result; the owner decides",
}


def bindings() -> dict:
    out = C.year_bindings()
    for p in (HERE / "lab_c2.py", HERE / "test_lab_c2.py"):
        out["sources"][p.relative_to(C.ROOT).as_posix()] = Y.grid._sha(p)
    return out


def freeze() -> None:
    parts = {}
    for year in ("2025", "2026"):
        out = subprocess.check_output([sys.executable, str(HERE / "lab_c2.py"), "bindings"], cwd=C.ROOT,
                                      env={**C.os.environ, "O30C_YEAR": year})
        parts[year] = json.loads(out.decode("utf-8").strip().splitlines()[-1])
    Y.write_new(HERE / "freeze-tier2.json", {"schema": "o30c_tier2_v1", "bindings": parts, "books": books(),
                                             "rule": RULE, "qualification": "NOT_ASSESSED", "can_place_orders": False})
    print("frozen", len(books()), "tier 2 books")


def run(jobs: int) -> None:
    frozen = json.loads((HERE / "freeze-tier2.json").read_text(encoding="utf-8"))
    assert frozen["bindings"][C.YEAR] == json.loads(json.dumps(bindings(), default=str)), "inputs changed"
    rel = (HERE / "freeze-tier2.json").relative_to(C.ROOT).as_posix()
    assert json.loads(subprocess.check_output(["git", "show", f"HEAD:{rel}"], cwd=C.ROOT)) == frozen, "not committed"
    C.O27F.deny_network()
    C.table("year")
    all_books = books()
    with ProcessPoolExecutor(max_workers=jobs, initializer=C._init) as ex:
        runner = Y.Runner(ex, jobs)
        runner.run(list(all_books.values()), source="year", window=C.WINDOW)
    Y.write_new(C.LOCAL / f"results-raw-tier2-{C.YEAR}.json", {
        "freeze_sha256": Y.grid._sha(HERE / "freeze-tier2.json"), "year": C.YEAR,
        "books": {n: Y.task_key(b, "year", C.WINDOW) for n, b in all_books.items()}, "trades": runner.trades})
    print("DONE tier 2", C.YEAR, len(runner.trades), flush=True)


def analyze() -> None:
    sys.path.insert(0, str(C.ROOT / "docs/research/fno/2026-10-29-why-study"))
    import analyze_g as AG
    sys.path.insert(0, str(HERE))
    import analyze_c as A
    days = A.sessions()
    trades = {}
    for y in A.YEARS:
        raw = json.loads((C.LOCAL / f"results-raw-tier2-{y}.json").read_text(encoding="utf-8"))
        assert raw["freeze_sha256"] == Y.grid._sha(HERE / "freeze-tier2.json")
        trades[y] = {n: raw["trades"][k] for n, k in raw["books"].items()}
    spans = {f"{y}_{h}": (y, s) for y in A.YEARS for h, s in zip(("H1", "H2"), C.HALVES[y])}
    m = {}
    for n in trades["2025"]:
        row = {y: AG.per_lot(trades[y][n], C.WINDOWS[y], days[y]) for y in A.YEARS}
        row.update({k: AG.per_lot(trades[y][n], s, days[y]) for k, (y, s) in spans.items()})
        row["both"] = AG.per_lot(trades["2025"][n] + trades["2026"][n], A.BOTH, days["2025"] + days["2026"])
        row["weeks"] = AG.one_lot_weeks(trades["2025"][n] + trades["2026"][n], days["2025"] + days["2026"])
        m[n] = row
    Y.write_new(HERE / "results-tier2.json", {"schema": "o30c_tier2_results_v1", "rule": RULE, "metrics_per_lot": m,
                                              "freeze_sha256": Y.grid._sha(HERE / "freeze-tier2.json")})
    print(f"{'book (per lot, IN-SAMPLE)':50} {'2025':>7} {'2026':>7} {'both':>7} {'t':>4} {'worst':>6} {'dd':>6} "
          f"{'mo g/r':>6} halves(25H1,25H2,26H1,26H2) one-lot weeks")
    for n in sorted(m, key=lambda n: -m[n]["both"]["net"]):
        b = m[n]["both"]
        print(f"{n:50} {m[n]['2025']['net']:7} {m[n]['2026']['net']:7} {b['net']:7} {b['trades']:4} {b['worst_day']:6} "
              f"{b['dd']:6} {b['green_months']:2}/{b['red_months']:<2} {[m[n][k]['net'] for k in spans]} {m[n]['weeks']}")


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=["bindings", "freeze", "run", "analyze"])
    cli.add_argument("--jobs", type=int, default=4)
    a = cli.parse_args()
    if a.action == "bindings":
        print(json.dumps(bindings(), default=str))
    else:
        {"freeze": freeze, "run": lambda: run(a.jobs), "analyze": analyze}[a.action]()
