"""EN85: the forward cohort machine (PLAN7.md). Every registered round-7 arm, scored once per new eligible expiry,
into an append-only ledger, with the frozen code only.

    python fwd7.py status     the registry, the dated calendar, what has been scored, what is due or MISSING
    python fwd7.py run        score each new eligible expiry once (refuses changed code; never rewrites a row)
    python fwd7.py dryrun     the same machinery on the last 8 NIFTY and 4 SENSEX historical expiries plus one known
                              MISSING session, into _local/fwd-dryrun.jsonl, flagged DRY_RUN: a rehearsal, never evidence

Rules (PLAN7 s.5, EN85): the cohort starts SENSEX 2026-11-19 and NIFTY 2026-11-23 (the dated catalogue; Nov 24 is an
NSE F&O holiday). An expiry is ELIGIBLE when the Breeze history holds its index and front-future minutes and the
expiring chain 12:00-15:29; otherwise it is MISSING with the missing inputs named, and it still counts in the
calendar - never a zero-P&L no-trade day. The scheduled review is the first 40 eligible expiries per index; the cohort
continues to 100 if support (20 executed parents over >= 10 traded expiries per index) is short. Classification at
review uses score7.classify on forward rows only. The wallet is recomputed over the forward sequence from Rs 30,000."""
from __future__ import annotations
import hashlib, json, sqlite3, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
COHORT_START = {"SENSEX": "2026-11-19", "NIFTY": "2026-11-23"}
CALENDAR = {"SENSEX": ["2026-11-19", "2026-11-26", "2026-12-03"], "NIFTY": ["2026-11-23", "2026-12-01"]}   # dated catalogue (errata A1)
LEDGER = HERE / "forward7" / "ledger.jsonl"
DRY = HERE / "_local" / "fwd-dryrun.jsonl"
REVIEW_AT, CONTINUE_TO = 40, 100
SC = ("ordinary", "adverse", "catastrophe")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def frozen_ok():
    fz = json.loads((HERE / "freeze7.json").read_text())
    import score7
    paths, _ = score7._paths()
    bad = [k for k, p in paths.items() if fz["files"].get(k) != sha(p)]
    assert not bad, f"code changed since the freeze: {bad} - a change needs a new registration"
    return fz


def _src():
    import fut7
    return sqlite3.connect(fut7.DB.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)


def coverage(und, day):
    """What the Breeze history holds for this expiry: (eligible, missing inputs)."""
    c = _src(); miss = []
    nx = c.execute("SELECT count(*) FROM candles WHERE kind='index' AND underlying=? AND interval='1minute' AND datetime BETWEEN ? AND ?",
                   (und, day + " 12:00:00", day + " 15:29:00")).fetchone()[0]
    nf = c.execute("SELECT count(*) FROM candles WHERE kind='future' AND underlying=? AND interval='1minute' AND datetime BETWEEN ? AND ?",
                   (und, day + " 12:00:00", day + " 15:29:00")).fetchone()[0]
    no = c.execute("SELECT count(*) FROM candles WHERE kind='option' AND underlying=? AND expiry=? AND interval='1minute' AND datetime BETWEEN ? AND ?",
                   (und, day, day + " 12:00:00", day + " 15:29:00")).fetchone()[0]
    c.close()
    if nx < 150:
        miss.append(f"index minutes {nx}/210")
    if nf < 150:
        miss.append(f"front-future minutes {nf}/210")
    if no < 1000:
        miss.append(f"expiring-chain option minutes {no}")
    return not miss, miss


def discover(und, through=None):
    """Expiries on or after the cohort start that the history (or the dated calendar) knows about."""
    c = _src(); days = set(CALENDAR[und])
    for (e,) in c.execute("SELECT DISTINCT expiry FROM candles WHERE kind='option' AND underlying=? AND expiry>=?", (und, COHORT_START[und])):
        days.add(e)
    c.close()
    today = through or time.strftime("%Y-%m-%d")
    return sorted(d for d in days if d <= today)


def build_tape(und, day):
    """The expiring session's tape from the Breeze history, by the frozen builder (en4_data.build)."""
    import en_lab7 as L7
    c = _src(); m = sqlite3.connect(":memory:"); m.row_factory = sqlite3.Row
    m.execute("CREATE TABLE candles(kind TEXT,underlying TEXT,expiry TEXT,strike REAL,opt TEXT,datetime TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL,oi REAL)")
    front = c.execute("SELECT MIN(expiry) FROM candles WHERE kind='future' AND underlying=? AND expiry>=? AND interval='1minute' AND datetime BETWEEN ? AND ?",
                      (und, day, day + " 09:15:00", day + " 15:29:00")).fetchone()[0]
    rows = c.execute("SELECT kind, underlying, expiry, strike, opt, datetime, open, high, low, close, volume, oi FROM candles WHERE underlying=? AND interval='1minute' "
                     "AND datetime BETWEEN ? AND ? AND (kind='index' OR (kind='future' AND expiry=?) OR (kind='option' AND expiry=? AND datetime>=?))",
                     (und, day + " 09:15:00", day + " 15:29:00", front, day, day + " 12:00:00")).fetchall()
    c.close()
    m.executemany("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    t = L7.D4.build(m, und, day, L7.D4._D()); m.close(); L7.KEEP7.append(t)
    return t


def score_sessions(hist, fwd, ledger_rows, dry):
    """Prepare (history + forward tapes, causal), run every registered arm on each forward tape not yet in the ledger."""
    import en_lab7 as L7, prep7 as P7, alloc7  # noqa: F401  (alloc7 registers EN60_env)
    B = {u: hist[u] + fwd[u] for u in hist}
    sig = HERE / "_local" / ("n11-dry.json" if dry else "n11-forward.json")
    days = [[u, t.day] for u in fwd for t in fwd[u]]
    if days:
        (HERE / "_local" / "n11-fwd-days.json").write_text(json.dumps(days))
        subprocess.run([sys.executable, "-I", "-B", str(HERE / "n11x.py"), str(HERE / "_local" / "n11-fwd-days.json"), str(sig)], check=True,
                       capture_output=True)
        P7.n11(sig, {u: fwd[u] for u in fwd})
    for u, book in B.items():
        for t in fwd[u]:
            P7.syn75(t); P7.basis78(t)
        if u == "NIFTY":
            P7.oi83(book)
        P7.ridge73(book)
    done = {(r["und"], r["day"]) for r in ledger_rows}; new = []
    for u in fwd:
        for t in fwd[u]:
            if (u, t.day) in done:
                continue
            arms = {}
            for name, arm in L7.ARMS.items():
                if name.startswith("EN83") and u == "SENSEX":
                    continue
                arms[name] = {sc: {k: v for k, v in L7.day7(t, arm, sc, 30000., L7.budget_of(arm), False).items()
                                   if k in ("net", "trades", "fees", "unresolved", "marked_worst", "intents", "minutes_in")} for sc in SC}
            new.append(dict(und=u, day=t.day, status="ELIGIBLE", arms=arms, dry_run=dry))
    return new


def append(path, rows):
    path.parent.mkdir(exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, default=float) + "\n")


def read(path):
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()] if path.exists() else []


def run(dry=False):
    fz = frozen_ok()
    import en_lab7 as L7
    L7.L5.install(); B = L7.L6.books()
    path = DRY if dry else LEDGER; rows = read(path); done = {(r["und"], r["day"]) for r in rows}
    if dry:
        fwd = {"NIFTY": B["NIFTY"][-8:], "SENSEX": B["SENSEX"][-4:]}
        hist = {"NIFTY": B["NIFTY"][:-8], "SENSEX": B["SENSEX"][:-4]}
        missing = [("NIFTY", "2026-11-17")]                                   # Breeze has no NIFTY future after Oct 28
    else:
        hist = B; fwd = {"NIFTY": [], "SENSEX": []}; missing = []
        for u in ("NIFTY", "SENSEX"):
            for d in discover(u):
                if (u, d) in done:
                    continue
                ok, miss = coverage(u, d)
                if ok:
                    fwd[u].append(build_tape(u, d))
                else:
                    missing.append((u, d, miss))
    miss_rows = []
    for x in missing:
        u, d = x[0], x[1]
        if (u, d) in done:
            continue
        ok, miss = coverage(u, d) if len(x) == 2 else (False, x[2])
        miss_rows.append(dict(und=u, day=d, status="MISSING", missing=miss, dry_run=dry))
    new = score_sessions(hist, fwd, rows, dry)
    for r in new + miss_rows:
        r["freeze_sha256"] = sha(HERE / "freeze7.json"); r["code_head"] = fz["head"]
    append(path, sorted(new + miss_rows, key=lambda r: (r["day"], r["und"])))
    print(("DRY_RUN " if dry else "") + f"appended {len(new)} eligible + {len(miss_rows)} missing -> {path.name}")
    return new, miss_rows


def idempotence():
    """A second dry run appends nothing; recomputing the dry-run sessions reproduces the ledger to the paisa."""
    before = read(DRY); run(dry=True); after = read(DRY)
    assert len(after) == len(before), "a scored session was scored twice"
    import en_lab7 as L7
    B = L7.L6.books(); fwd = {"NIFTY": B["NIFTY"][-8:], "SENSEX": B["SENSEX"][-4:]}; hist = {"NIFTY": B["NIFTY"][:-8], "SENSEX": B["SENSEX"][:-4]}
    again = {(r["und"], r["day"]): r for r in score_sessions(hist, fwd, [], True)}
    for r in before:
        if r["status"] == "ELIGIBLE":
            assert again[(r["und"], r["day"])]["arms"] == r["arms"], (r["und"], r["day"])
    return f"IDEMPOTENT_OK {len(before)} dry-run rows; rerun appended nothing; recomputation identical"


def power(dev):
    """Expected forward expiries to the support floor from the development activity (parents and traded expiries per
    expiry), per arm and index: a planning number, not evidence."""
    out = {}
    for key, v in dev.items():
        m = v["ordinary"]; s = max(1, m["sessions"])
        rp, re = m["tickets"] / s, m["traded_expiries"] / s
        need = max(20 / rp if rp else float("inf"), 10 / re if re else float("inf"))
        out[key] = dict(parents_per_expiry=round(rp, 3), traded_share=round(re, 3), expiries_to_support=round(need, 1) if need != float("inf") else None,
                        reaches_by_100=bool(need <= 100))
    return out


def status():
    rows = read(LEDGER)
    out = dict(cohort_start=COHORT_START, dated_calendar=CALENDAR, scored=len([r for r in rows if r["status"] == "ELIGIBLE"]),
               missing=[(r["und"], r["day"], r["missing"]) for r in rows if r["status"] == "MISSING"])
    for u in ("NIFTY", "SENSEX"):
        el = [r for r in rows if r["und"] == u and r["status"] == "ELIGIBLE"]
        out[u] = dict(eligible=len(el), review_due=len(el) >= REVIEW_AT, unscored_known=[d for d in discover(u) if d not in {r["day"] for r in rows if r["und"] == u}])
    print(json.dumps(out, indent=1))
    return out


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "status":
        status()
    elif cmd == "run":
        run()
    elif cmd == "dryrun":
        run(dry=True); print(idempotence())
