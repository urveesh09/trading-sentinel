"""EN01 sanity check on real data: E03.2 through the CURRENT Dev engine (EN01 + EN02 code) on the 10 Production
expiry recordings (Oct 6 - Nov 5 2026, 10-second ticks, 5-level books; copy in 2026-11-05-fno-expiry-followup/_local),
one fresh Rs 25,000 book per session, against the Nov 5 receipt (engine b6b0dbf). Ticks start 12:59 in these
recordings, so EN02's warm-up cannot show here. No decision is taken from this (about two tickets)."""
import json, sqlite3, sys, tempfile
from pathlib import Path
HERE = Path(__file__).resolve().parent
F = HERE.parent / "2026-11-05-fno-expiry-followup"
sys.path.insert(0, str(F))
import expiry_study as S  # noqa: E402  (master(), e032(), summary(); reads the followup's _local copies)

def main():
    marks = json.loads((S.LOCAL / "expiry-masters.json").read_bytes())
    old = json.loads((F / "expiry-results.json").read_bytes())
    src = sqlite3.connect((S.LOCAL / "expiry-input.sqlite").as_uri() + "?mode=ro", uri=True); src.row_factory = sqlite3.Row
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        for day, u in src.execute("select day,underlying from expiry_paper_days order by day").fetchall():
            ticks = src.execute("select day,underlying,ts,spot,fut,quotes from expiry_paper_ticks where day=? and underlying=? order by ts", (day, u)).fetchall()
            first = json.loads(ticks[0]["quotes"])
            if not isinstance(next(iter(first.get("legs", {}).values()), None), dict):
                out[day] = dict(underlying=u, coverage="NO_FIVE_LEVEL_PACKET"); continue
            pos, counts, risk = S.e032(ticks, S.master(marks[day], u, day), day, Path(tmp))
            s = S.summary(pos); prev = old[day]["E032"]
            out[day] = dict(underlying=u, now=dict(net=s["net"], closed=s["closed"], unresolved=s["unresolved"],
                            trades=[(t["symbol"], t["entry_ts"], t["lots"], t["entry_price"], t["net_pnl"], [ev["action"] for ev in t["_events"]]) for t in s["trades"]]),
                            nov5=dict(net=prev["net"], closed=prev["closed"]), same=abs(s["net"] - prev["net"]) < .01 and s["closed"] == prev["closed"],
                            signal=counts.get("signal", {}))
            print(day, u, out[day]["now"]["net"], out[day]["nov5"]["net"], "same" if out[day]["same"] else "DIFFERENT", out[day]["now"]["trades"], flush=True)
    (HERE / "replay2026.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
