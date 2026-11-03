"""The closing-auction drift on expiry days (PLAN.md). Read-only on every source; no provider call.

    python auction.py smoke    October 6 only (the day that suggested the hypothesis), printed, nothing written
    python auction.py freeze   writes freeze.json once (hashes of this script, the plan and every source)
    python auction.py score    refuses unless the freeze is committed and every hash matches -> results.json
"""
from __future__ import annotations
import csv, hashlib, json, math, os, re, sqlite3, statistics as st, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIM = HERE.parent
REPO = next(p for p in HERE.parents if (p / "python-engine").is_dir())
sys.path.insert(0, str(REPO / "python-engine"))
import expiry_paper as EP  # noqa: E402  (native fees, depth walk and exercise STT only)

PROD = [SIM / "2026-11-02-expiry-e01/_local/export/expiry.sqlite", SIM / "2026-11-03-expiry-e03/_local/native-extra.sqlite"]
OPS = Path(os.path.expanduser("~")) / "sentinel-operations/breeze-history-20261029/data"
EXPORT = OPS / "expiry-10second-20261103"
BREEZE = OPS / "breeze-history.sqlite"
SEEN = {("NIFTY", "2026-10-06")}
CAS_START = "2026-08-03"
LOT = {"NIFTY": 65, "SENSEX": 20}
T_STAR = 15 * 3600 + 22 * 60
THETA = 0.0004
LIMIT = 1.08
FRESH_PROD, FRESH_EXPORT = 20, 30
GRID = ["15:16", "15:18", "15:20", "15:22", "15:25", "15:27", "15:29"]
SYM = re.compile(r"^(NIFTY|SENSEX)\d{2}([1-9OND]\d{2}|[A-Z]{3})(\d+)(CE|PE)$")
FREEZE, OUT = HERE / "freeze.json", HERE / "results.json"


def secs(hhmmss):
    h, m, s = (int(x) for x in hhmmss[:8].split(":"))
    return h * 3600 + m * 60 + s


def clock(t):
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}"


# ---------------------------------------------------------------- sources

def production_days():
    out = {}
    for path in PROD:
        c = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        for day, u, ts, spot, fut, q in c.execute("SELECT day, underlying, ts, spot, fut, quotes FROM expiry_paper_ticks ORDER BY day, ts"):
            q = json.loads(q); legs = {}
            for sym, v in (q.get("legs") or {}).items():
                m = SYM.match(sym)
                if not m or not v:
                    continue
                if isinstance(v, list):          # the October 6 format: [bid, bid qty, ask, ask qty, last, ts]
                    bids = [(v[0], v[1])] if v[0] and v[1] else []
                    asks = [(v[2], v[3])] if v[2] and v[3] else []
                    lts = v[5]
                else:
                    bids = [(float(p), int(n)) for p, n in v.get("b") or [] if p and n and p > 0 and n > 0]
                    asks = [(float(p), int(n)) for p, n in v.get("a") or [] if p and n and p > 0 and n > 0]
                    lts = v.get("ts")
                legs[(float(m.group(3)), m.group(4))] = dict(bids=bids, asks=asks, ts=secs(lts[11:19]) if lts else None)
            out.setdefault((u, day), []).append(dict(t=secs(ts[11:19]), spot=spot, fut=fut, legs=legs))
        c.close()
    return out


def export_days():
    out = {}
    for folder in ("nifty", "sensex"):
        for name in sorted(os.listdir(EXPORT / folder)):
            u, day = name.split("-")[0], "-".join(name.split("-")[1:4])
            if day < CAS_START or (name.endswith("PARTIAL.csv") and any(n.startswith(f"{u}-{day}-ATM-10second.csv") for n in os.listdir(EXPORT / folder))):
                continue
            bars = {"CE": {}, "PE": {}}; strike = None
            with open(EXPORT / folder / name, encoding="utf-8") as f:
                for r in csv.DictReader(f):
                    strike = float(r["strike"])
                    bars[r["opt"]][secs(r["datetime_ist"][11:19]) + 10] = float(r["close"])   # keyed by bar END
            out[(u, day)] = dict(strike=strike, bars=bars, file=name)
    return out


def index_minutes(u, day):
    c = sqlite3.connect(BREEZE.resolve().as_uri() + "?mode=ro", uri=True)
    rows = {}
    for kind in ("index", "future"):
        rows[kind] = {secs(dt[11:19]): close for dt, close in c.execute(
            "SELECT datetime, close FROM candles WHERE kind=? AND underlying=? AND interval='1minute' AND datetime BETWEEN ? AND ? ORDER BY datetime",
            (kind, u, f"{day} 15:00:00", f"{day} 15:39:00"))}
    daily = c.execute("SELECT close FROM candles WHERE kind='daily' AND underlying=? AND substr(datetime,1,10)=?", (u, day)).fetchone()
    c.close()
    return rows["index"], rows["future"], daily[0] if daily else None


# ---------------------------------------------------------------- measures

def mid(leg):
    return (leg["bids"][0][0] + leg["asks"][0][0]) / 2 if leg and leg["bids"] and leg["asks"] else None


def prod_synthetic(snap, s0):
    vals = []
    for k in sorted({k for k, _ in snap["legs"]}, key=lambda k: abs(k - s0)):
        c, p = snap["legs"].get((k, "CE")), snap["legs"].get((k, "PE"))
        fresh = all(x and x["ts"] is not None and snap["t"] - x["ts"] <= FRESH_PROD for x in (c, p))
        if fresh and mid(c) is not None and mid(p) is not None:
            vals.append(k + mid(c) - mid(p))
        if len(vals) == 3:
            break
    return st.median(vals) if vals else None


def at(snaps, t):
    """The last snapshot taken at or before t."""
    best = None
    for s in snaps:
        if s["t"] <= t:
            best = s
    return best


def prod_day(u, day, snaps):
    s0s = at(snaps, secs("15:20:00"))
    after = [s for s in snaps if s["t"] >= secs("15:31:00")]
    if not s0s or not after:
        return dict(unavailable="no 15:20 or 15:31 snapshot")
    s0, f = s0s["spot"], after[0]["spot"]
    frozen = len({s["spot"] for s in snaps if secs("15:16:00") <= s["t"] < secs("15:29:00")}) == 1
    basis = st.median(s["fut"] - s["spot"] for s in snaps if secs("15:00:00") <= s["t"] < secs("15:15:00") and s["fut"] and s["spot"])
    path = {}
    for g in GRID:
        s = at(snaps, secs(g + ":00"))
        y = prod_synthetic(s, s0) if s and secs(g + ":00") - s["t"] <= FRESH_PROD else None
        path[g] = dict(y=y, fut_drift=round(s["fut"] - basis - s0, 2) if s and s["fut"] else None)
    return dict(source="production", s0=s0, settle=f, move=round(f - s0, 2), frozen=frozen, path=path)


def export_day(u, day, rec):
    idx, fut, daily = index_minutes(u, day)
    if secs("15:20:00") not in idx or secs("15:35:00") not in idx:
        return dict(unavailable="index minutes missing")
    s0, f = idx[secs("15:20:00")], idx[secs("15:35:00")]
    frozen = len({idx[t] for t in idx if secs("15:16:00") <= t <= secs("15:28:00")}) == 1
    pre = [fut[t] - idx[t] for t in idx if secs("15:00:00") <= t < secs("15:15:00") and t in fut]
    basis = st.median(pre) if pre else None
    path = {}
    for g in GRID:
        t = secs(g + ":00"); y = None
        legs = []
        for o in ("CE", "PE"):
            done = [e for e in rec["bars"][o] if t - FRESH_EXPORT <= e <= t]
            legs.append(rec["bars"][o][max(done)] if done else None)
        if None not in legs:
            y = rec["strike"] + legs[0] - legs[1]
        m = t - 60                                         # the minute bar that closed at t
        path[g] = dict(y=y, fut_drift=round(fut[m] - basis - s0, 2) if basis is not None and m in fut else None)
    return dict(source="export", file=rec["file"], s0=s0, settle=f, move=round(f - s0, 2), frozen=frozen,
                daily_close=daily, settle_matches_daily=None if daily is None else abs(daily - f) < .01, path=path)


def finish(row):
    """Drift D and remaining move R at each grid time."""
    if "unavailable" in row:
        return row
    for g, p in row["path"].items():
        if p["y"] is None:
            p.update(d=None, r=None); continue
        d = p["y"] - row["s0"]
        p.update(y=round(p["y"], 2), d=round(d, 2), r=round((row["settle"] - p["y"]) * (1 if d > 0 else -1 if d < 0 else 0), 2))
    p = row["path"]["15:22"]
    row["signal"] = p["d"] is not None and abs(p["d"]) >= THETA * row["s0"]
    return row


# ---------------------------------------------------------------- the trade (Production days)

def walk(levels, lot):
    whole, price = EP.walk(tuple(levels), 1, lot)
    return price if whole == 1 else None


def trade(u, day, snaps, row, flip=False, hold=False):
    lot, fees = LOT[u], EP.fee_schedule("NFO" if u == "NIFTY" else "BFO")
    i = next((n for n, s in enumerate(snaps) if s["t"] >= T_STAR), None)
    if i is None or i + 1 >= len(snaps):
        return dict(result="unavailable", why="no decision snapshot")
    dec, nxt = snaps[i], snaps[i + 1]
    y = prod_synthetic(dec, row["s0"])
    if y is None:
        return dict(result="unavailable", why="no synthetic at decision")
    d = y - row["s0"]
    if abs(d) < THETA * row["s0"]:
        return dict(result="no_signal", d=round(d, 2))
    side = (1 if d > 0 else -1) * (-1 if flip else 1)
    opt = "CE" if side > 0 else "PE"
    ks = sorted(k for k, o in dec["legs"] if o == opt and dec["legs"][(k, o)]["asks"])
    pick = max((k for k in ks if k <= y), default=None) if opt == "CE" else min((k for k in ks if k >= y), default=None)
    if pick is None:
        return dict(result="unavailable", why="no strike on that side")
    leg = dec["legs"][(pick, opt)]
    if leg["ts"] is None or dec["t"] - leg["ts"] > FRESH_PROD:
        return dict(result="unavailable", why="stale decision quote")
    limit = round(leg["asks"][0][0] * LIMIT, 2)
    nleg = nxt["legs"].get((pick, opt))
    entry = walk(nleg["asks"], lot) if nleg and nleg["ts"] is not None and nxt["t"] - nleg["ts"] <= FRESH_PROD and nleg["asks"] else None
    if entry is None or entry > limit:
        return dict(result="refused", strike=pick, opt=opt, d=round(d, 2), limit=limit, next_ask=entry)
    buy_fee = EP.buy_charges(entry, lot, fees)
    exit_price = exit_t = None
    if not hold:
        for s in snaps[i + 2:]:
            if s["t"] < secs("15:31:00"):
                continue
            leg2 = s["legs"].get((pick, opt))
            if leg2 and leg2["ts"] is not None and s["t"] - leg2["ts"] <= FRESH_PROD and leg2["bids"]:
                exit_price = walk(leg2["bids"], lot)
                if exit_price is not None:
                    exit_t = s["t"]; break
    intrinsic = max(0., row["settle"] - pick) if opt == "CE" else max(0., pick - row["settle"])
    if exit_price is not None:
        net = (exit_price - entry) * lot - buy_fee - EP.sell_charges(exit_price, lot, fees)
        how = "SOLD"
    else:
        net = (intrinsic * (1 - EP.EXERCISE_STT_PCT) - entry) * lot - buy_fee
        how = "SETTLED"
    return dict(result="traded", side=opt, strike=pick, d=round(d, 2), y=round(y, 2), decision=clock(dec["t"]), entry_at=clock(nxt["t"]),
                entry=entry, limit=limit, exit=exit_price, exit_at=clock(exit_t) if exit_t else None, intrinsic=round(intrinsic, 2),
                how=how, net=round(net, 2), premium=round(entry * lot, 2))


# ---------------------------------------------------------------- outputs

def summary(rows, label):
    sig = [r for r in rows if r.get("signal")]
    d = [r["path"]["15:22"]["d"] for r in sig]; rr = [r["path"]["15:22"]["r"] for r in sig]
    agree = [math.copysign(1, r["path"]["15:22"]["d"]) == math.copysign(1, r["move"]) for r in sig if r["move"]]
    out = dict(label=label, days=len(rows), signalled=len(sig),
               unavailable=sum(1 for r in rows if "unavailable" in r or r["path"]["15:22"]["d"] is None),
               h1_agree=round(sum(agree) / len(agree), 3) if agree else None,
               r_mean=round(st.mean(rr), 2) if rr else None, r_median=round(st.median(rr), 2) if rr else None,
               r_positive=round(sum(x > 0 for x in rr) / len(rr), 3) if rr else None, d_mean_abs=round(st.mean(abs(x) for x in d), 2) if d else None)
    out["h1_pass"] = bool(out["signalled"] >= 12 and out["h1_agree"] is not None and out["h1_agree"] >= .7)
    out["h2_pass"] = bool(rr and out["r_mean"] > 0 and out["r_median"] > 0 and out["r_positive"] >= .6)
    return out


def collect(only_seen=False):
    prod = production_days(); rows = {}
    for (u, day), snaps in prod.items():
        if only_seen and (u, day) not in SEEN:
            continue
        rows[(u, day)] = finish(prod_day(u, day, snaps))
    if not only_seen:
        for (u, day), rec in export_days().items():
            if (u, day) not in rows:
                rows[(u, day)] = finish(export_day(u, day, rec))
    return prod, rows


def run(only_seen):
    prod, rows = collect(only_seen)
    trades = {}
    for key, snaps in prod.items():
        if key in rows and "unavailable" not in rows[key]:
            trades[key] = {name: trade(*key, snaps, rows[key], **kw) for name, kw in
                           (("drift", {}), ("opposite", dict(flip=True)), ("drift_hold", dict(hold=True)))}
    return rows, trades


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 22):
            h.update(chunk)
    return h.hexdigest()


def git(*a):
    return subprocess.run(["git", *a], cwd=REPO, capture_output=True, text=True, check=True).stdout.strip()


def files():
    fs = [HERE / "auction.py", HERE / "PLAN.md", *PROD]
    fs += [EXPORT / f / n for f in ("nifty", "sensex") for n in sorted(os.listdir(EXPORT / f)) if "-".join(n.split("-")[1:4]) >= CAS_START]
    return fs


def freeze():
    assert not FREEZE.exists(), "written once"
    FREEZE.write_text(json.dumps(dict(head=git("rev-parse", "HEAD"), written_before_scoring=True, seen=sorted(map(list, SEEN)),
                                      files={str(p): sha(p) for p in files()}, breeze_db_bytes=BREEZE.stat().st_size, breeze_db_sha256=sha(BREEZE),
                                      t_star="15:22:00", theta=THETA, limit=LIMIT), indent=2) + "\n", encoding="utf-8")
    print("FROZEN")


def verify():
    frozen = json.loads(FREEZE.read_text(encoding="utf-8"))
    for p, digest in frozen["files"].items():
        assert sha(p) == digest, f"changed after the freeze: {p}"
    rel = str(FREEZE.relative_to(REPO)).replace("\\", "/")
    assert git("log", "-1", "--format=%H", "--", rel), "commit the freeze first"
    assert not git("status", "--porcelain", "--", rel, str((HERE / "auction.py").relative_to(REPO)).replace("\\", "/"))
    return frozen


def score():
    frozen = verify()
    rows, trades = run(False)
    unseen = [r for k, r in rows.items() if k not in SEEN and "unavailable" not in r]
    out = dict(freeze_head=frozen["head"],
               h=summary(unseen, "26 unseen closing-auction expiry days"),
               h_by_index={u: summary([r for k, r in rows.items() if k not in SEEN and k[0] == u and "unavailable" not in r], u) for u in ("NIFTY", "SENSEX")},
               h_by_source={s: summary([r for k, r in rows.items() if k not in SEEN and r.get("source") == s], s) for s in ("production", "export")},
               seen_day={f"{k[0]} {k[1]}": r for k, r in rows.items() if k in SEEN},
               days={f"{k[0]} {k[1]}": r for k, r in sorted(rows.items())},
               trades={f"{k[0]} {k[1]}": v for k, v in sorted(trades.items())})
    tr = [v["drift"] for k, v in trades.items() if k not in SEEN and v["drift"]["result"] == "traded"]
    nets = [x["net"] for x in tr]
    out["trade"] = dict(days=len([k for k in trades if k not in SEEN]), traded=len(tr), total=round(sum(nets), 2),
                        mean=round(st.mean(nets), 2) if nets else None, without_best=round(sum(nets) - max(nets), 2) if nets else None,
                        wins=sum(x > 0 for x in nets),
                        opposite_total=round(sum(v["opposite"]["net"] for k, v in trades.items() if k not in SEEN and v["opposite"]["result"] == "traded"), 2),
                        hold_total=round(sum(v["drift_hold"]["net"] for k, v in trades.items() if k not in SEEN and v["drift_hold"]["result"] == "traded"), 2))
    out["trade"]["pass"] = bool(nets and out["trade"]["total"] > 0 and out["trade"]["mean"] > 0 and out["trade"]["without_best"] > 0)
    OUT.write_text(json.dumps(out, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(dict(h=out["h"], by_index=out["h_by_index"], trade=out["trade"]), indent=1))


def smoke():
    rows, trades = run(True)
    for k, r in rows.items():
        print(k, {x: r[x] for x in ("s0", "settle", "move", "frozen", "signal")})
        for g, p in r["path"].items():
            print("  ", g, p)
        print("  trades", json.dumps(trades.get(k), default=str))


if __name__ == "__main__":
    {"smoke": smoke, "freeze": freeze, "score": score}[sys.argv[1]]()
