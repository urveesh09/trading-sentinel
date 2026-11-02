"""Before any freeze: is September usable? Snapshot, data checks, proxy quality, which breaks have a ticket.

Prints no ticket path, no exit, no rupee result. Run once before the plan is frozen, and its output is committed.
"""
import hashlib
import json
import shutil
from pathlib import Path

import e011_lab as L
import sept as Z
from e011_lab import EP

Z.SNAPSHOT.mkdir(parents=True, exist_ok=True)
hashes = {}
for day in Z.DAYS:
    name = f"NIFTY-{day}-ATM-CE-PE-10second.csv"
    target = Z.SNAPSHOT / name
    if not target.exists():
        shutil.copyfile(Z.SOURCE / name, target)
    hashes[name] = hashlib.sha256(target.read_bytes()).hexdigest()
    assert hashes[name] == hashlib.sha256((Z.SOURCE / name).read_bytes()).hexdigest()
spreads = Z.build_spreads()
print("spreads", spreads)
checks = Z.validate()
print(json.dumps(checks, indent=0))

minutes = json.loads((L.LOCAL / "index-minutes.json").read_text())
report = {"hashes": hashes, "spreads": spreads, "checks": checks, "days": {}}
for day in Z.DAYS:
    S = Z.Sept(day)
    index = {r[0][11:19]: r[4] for r in minutes[day]}
    diffs = []
    for i in range(S.n):
        t = S.now[i].strftime("%H:%M:%S")
        # A minute candle stamped HH:MM closes at HH:MM+1, which is this tick's clock when the seconds are zero.
        if t.endswith(":00") and S.clock[i] < EP.AUCTION_START:
            stamp = (S.now[i] - L.timedelta(minutes=1)).strftime("%H:%M:00")
            if stamp in index:
                diffs.append(S.spot[i] - index[stamp])
    mean = sum(diffs) / len(diffs)
    mad = sum(abs(x - mean) for x in diffs) / len(diffs)
    state, signals = L.signal_stream(S)
    box = state["box"]
    width = box["hi"] - box["lo"]
    rows = []
    for i, d in signals:
        strike = EP.pick_lottery_strike(S.quoted_chain(i), d, S.spot[i], S.now[i])
        rows.append(dict(at=S.clock[i].isoformat()[:8], dir=d, ticket_available=strike is not None))
    entry = dict(strike=S.strike, proxy_minus_index_mean=round(mean, 2), proxy_abs_dev=round(mad, 2), minutes_compared=len(diffs),
                 box_bp=round(width / box["hi"] * 1e4, 1), box_status=state["box_status"], signals=rows)
    report["days"][day] = entry
    print(day, json.dumps(entry))
(L.HERE / "preflight-sept.json").write_text(json.dumps(report, indent=1) + "\n")
