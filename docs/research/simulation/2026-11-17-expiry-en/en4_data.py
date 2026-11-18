"""PLAN4.md section 1: the Nov 18 expiry-afternoon export (NIFTY 2026, SENSEX Jul 2025 - Nov 2026) and its tapes.

    python en4_data.py export   copies selected rows read-only from the Breeze history database into
                                _local/exam2026.sqlite once, cross-checks them against the download zip, and writes
                                data-binding4.json (hashes, per-day counts, cohort labels)
    python en4_data.py check    proves the tape builder equals exam2023.build_tapes on seen NIFTY 2024 and that the
                                export matches its binding; prints counts only

Rows: the index all day (09:15-15:29), the dated front future (nearest expiry on or after the day) all day, the
expiring options 12:00-15:29. Tapes are built exactly as exam2023.build_tapes builds 2023-25; only the symbol names
carry the index. No Breeze call is made; the download folder is only read."""
from __future__ import annotations
import csv, hashlib, io, json, pickle, sqlite3, sys, zipfile
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
BASE = Path.home() / "sentinel-operations/breeze-history-20261029"
SOURCE = BASE / "data/breeze-history.sqlite"
ZIP = BASE / "data/expiry-afternoons-1minute-20261118.zip"
RECEIPT = BASE / "run-logs/RUN_RECEIPT_AFTERNOONS_20261118.json"
LOCAL = HERE / "_local"
EXPORT = LOCAL / "exam2026.sqlite"
BINDING = HERE / "data-binding4.json"
COLS = "kind,underlying,expiry,strike,opt,datetime,open,high,low,close,volume,oi"
NO_INDEX = {("NIFTY", "2026-11-03"), ("NIFTY", "2026-11-09"), ("NIFTY", "2026-11-17"),
            ("SENSEX", "2026-10-29"), ("SENSEX", "2026-11-05"), ("SENSEX", "2026-11-12")}


def cohort(und, day):
    if und == "NIFTY":
        return "N-X1" if day <= "2026-09-08" else "N-X2"
    return "S-X1" if day <= "2026-09-03" else "S-X2"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while b := f.read(1 << 20):
            h.update(b)
    return h.hexdigest()


def src():
    return sqlite3.connect(SOURCE.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)


def candidates():
    """(und, day) for every file in the zip whose contract requests all resolved (coverage.json)."""
    z = zipfile.ZipFile(ZIP); cov = json.loads(z.read("coverage.json"))
    out = []
    for und in ("NIFTY", "SENSEX"):
        for d in cov["books"][und]["details"]:
            cs = d["contracts"]
            out.append(dict(und=und, day=d["date"], contracts=len(cs), resolved=sum(c["resolved"] for c in cs),
                            missing_minutes=sum(c.get("missing_minutes") or 0 for c in cs)))
    return sorted(out, key=lambda r: (r["und"], r["day"]))


def export():
    LOCAL.mkdir(parents=True, exist_ok=True)
    assert not EXPORT.exists() and not BINDING.exists(), "the export is sealed once"
    z = zipfile.ZipFile(ZIP)
    meta = dict(source=str(SOURCE), source_read_only=True, requests_calls=0, zip=str(ZIP), zip_sha256=sha(ZIP),
                receipt_sha256=sha(RECEIPT), days=[], excluded=[])
    with sqlite3.connect(EXPORT) as dst, src() as s:
        dst.execute("CREATE TABLE candles(kind TEXT,underlying TEXT,expiry TEXT,strike REAL,opt TEXT,datetime TEXT,"
                    "open REAL,high REAL,low REAL,close REAL,volume REAL,oi REAL)")
        for c in candidates():
            und, day = c["und"], c["day"]
            if c["resolved"] != 42 or c["contracts"] != 42:
                meta["excluded"].append(dict(und=und, day=day, reason=f"contracts resolved {c['resolved']} of {c['contracts']}")); continue
            ix = s.execute("SELECT COUNT(*) FROM candles WHERE kind='index' AND underlying=? AND interval='1minute' AND datetime BETWEEN ? AND ?",
                           (und, day + " 12:00:00", day + " 15:29:00")).fetchone()[0]
            front = s.execute("SELECT MIN(expiry) FROM candles WHERE kind='future' AND underlying=? AND expiry>=? AND interval='1minute' "
                              "AND datetime BETWEEN ? AND ?", (und, day, day + " 09:15:00", day + " 15:29:00")).fetchone()[0]
            fu = s.execute("SELECT COUNT(*) FROM candles WHERE kind='future' AND underlying=? AND expiry=? AND interval='1minute' AND datetime BETWEEN ? AND ?",
                           (und, front, day + " 12:00:00", day + " 15:29:00")).fetchone()[0] if front else 0
            if ix < 200 or fu < 200:
                assert (und, day) in NO_INDEX or fu < 200, (und, day, ix, fu)
                meta["excluded"].append(dict(und=und, day=day, reason=f"index minutes {ix}, future minutes {fu} (12:00-15:29)")); continue
            counts = {}
            for kind, expiry, t0 in (("index", None, "09:15:00"), ("future", front, "09:15:00"), ("option", day, "12:00:00")):
                sql = f"SELECT {COLS} FROM candles WHERE kind=? AND underlying=? AND interval='1minute' "
                args = [kind, und]
                if expiry:
                    sql += "AND expiry=? "; args.append(expiry)
                sql += "AND datetime BETWEEN ? AND ?"; args += [day + " " + t0, day + " 15:29:00"]
                rows = s.execute(sql, args).fetchall()
                dst.executemany("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows); counts[kind] = len(rows)
            # cross-check against the zip: every zip row <= 15:29 is in the export with the same OHLCV
            zr = list(csv.DictReader(io.StringIO(z.read(f"{und.lower()}/{day}.csv").decode())))
            got = {(r[3], r[4], r[5]): r[6:11] for r in dst.execute(
                "SELECT kind,underlying,expiry,strike,opt,datetime,open,high,low,close,volume FROM candles WHERE kind='option' AND underlying=? AND expiry=?",
                (und, day))}
            zin = [r for r in zr if r["datetime_ist"] <= day + " 15:29:00"]
            bad = sum(1 for r in zin if (float(r["strike"]), r["right"], r["datetime_ist"]) not in got or
                      any(abs(a - float(r[k])) > 1e-6 for a, k in zip(got[(float(r["strike"]), r["right"], r["datetime_ist"])],
                                                                    ("open", "high", "low", "close", "volume"))))
            assert bad == 0 and len(zin) == counts["option"], (und, day, bad, len(zin), counts["option"])
            meta["days"].append(dict(und=und, day=day, front=front, rows=counts, zip_rows_matched=len(zin), cohort=cohort(und, day),
                                     missing_option_minutes=c["missing_minutes"]))
            dst.commit()
        dst.execute("CREATE INDEX k ON candles(underlying,datetime,kind)")
        assert dst.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    meta["export_sha256"] = sha(EXPORT)
    meta["cohorts"] = {k: sum(d["cohort"] == k for d in meta["days"]) for k in ("N-X1", "N-X2", "S-X1", "S-X2")}
    BINDING.write_text(json.dumps(meta, indent=1) + "\n", encoding="utf-8")
    print("EXPORTED", meta["cohorts"], "excluded", len(meta["excluded"]))


# ---------------------------------------------------------------- tapes
def _binding():
    b = json.loads(BINDING.read_text(encoding="utf-8"))
    assert sha(EXPORT) == b["export_sha256"], "export changed"
    return b


def _D():
    sys.path.insert(0, str(HERE.parent / "2026-11-03-expiry-e02"))
    import data as D
    return D


def build(con, und, day, D):
    """exam2023.build_tapes' construction for one day (symbols carry the index)."""
    rows = con.execute("SELECT * FROM candles WHERE underlying=? AND datetime BETWEEN ? AND ? ORDER BY datetime",
                       (und, day + " 09:15:00", day + " 15:29:00")).fetchall()
    opts = sorted({(r["strike"], r["opt"]) for r in rows if r["kind"] == "option"})
    lookup = {v: j for j, v in enumerate(opts)}
    x = np.full((375, 4), np.nan); f = x.copy(); q = np.full((375, len(opts), 5), np.nan); bad = 0
    for r in rows:
        k = (int(r["datetime"][11:13]) - 9) * 60 + int(r["datetime"][14:16]) - 15
        if not 0 <= k < 375:
            continue
        vals = [r[n] for n in ("open", "high", "low", "close")]
        if not all(v is not None and np.isfinite(v) and v > 0 for v in vals) or not vals[2] <= min(vals[0], vals[3]) <= max(vals[0], vals[3]) <= vals[1]:
            bad += 1; continue
        if r["kind"] == "index":
            x[k] = vals
        elif r["kind"] == "future":
            f[k] = vals
        elif r["kind"] == "option":
            assert r["expiry"] == day
            if r["volume"] is None or r["volume"] < 0:
                bad += 1; continue
            q[k, lookup[r["strike"], r["opt"]]] = vals + [r["volume"]]
    now = [datetime.fromisoformat(day + "T09:15:00").replace(tzinfo=D.EP.IST) + timedelta(minutes=i + 1) for i in range(375)]
    t = D.Tape(day, x, f, q, np.array([k for k, o in opts]), np.array([1 if o == "CE" else -1 for k, o in opts]),
               [f"{und}-{day}-{k:g}-{o}" for k, o in opts], now, np.arange(556, 931), bad)
    t.und = und
    return t


_T = {}


def tapes():
    """{'N-X1': [...], 'N-X2': [...], 'S-X1': [...], 'S-X2': [...]} in day order; cached by export + builder hash."""
    if _T:
        return _T
    b = _binding(); D = _D()
    cache = LOCAL / f"tapes4-{b['export_sha256'][:12]}-{sha(Path(__file__))[:12]}.pkl"
    if cache.exists():
        _T.update(pickle.loads(cache.read_bytes()))
        return _T
    con = sqlite3.connect(EXPORT.resolve().as_uri() + "?mode=ro", uri=True); con.row_factory = sqlite3.Row
    out = {k: [] for k in ("N-X1", "N-X2", "S-X1", "S-X2")}
    for d in b["days"]:
        out[d["cohort"]].append(build(con, d["und"], d["day"], D))
    con.close()
    for k in out:
        out[k].sort(key=lambda t: t.day)
    cache.write_bytes(pickle.dumps(out))
    _T.update(out)
    return _T


_FV = {}


def futvol(t):
    """Futures volume per bar from the new export (keyed by index and day)."""
    key = (t.und, t.day)
    if key not in _FV:
        con = sqlite3.connect(EXPORT.resolve().as_uri() + "?mode=ro", uri=True)
        v = np.full(375, np.nan)
        for stamp, vol in con.execute("SELECT datetime, volume FROM candles WHERE kind='future' AND underlying=? AND datetime BETWEEN ? AND ?",
                                      (t.und, t.day + " 09:15:00", t.day + " 15:29:00")):
            k = (int(stamp[11:13]) - 9) * 60 + int(stamp[14:16]) - 15
            if 0 <= k < 375 and vol is not None and vol >= 0:
                v[k] = vol
        con.close(); _FV[key] = v
    return _FV[key]


def leader_future(day, und="NIFTY"):
    """EN33: the leader's dated front future close per bar (read-only from the Breeze database), NaN where missing."""
    with src() as s:
        front = s.execute("SELECT MIN(expiry) FROM candles WHERE kind='future' AND underlying=? AND expiry>=? AND interval='1minute' "
                          "AND datetime BETWEEN ? AND ?", (und, day, day + " 09:15:00", day + " 15:29:00")).fetchone()[0]
        v = np.full(375, np.nan)
        if front:
            for stamp, c in s.execute("SELECT datetime, close FROM candles WHERE kind='future' AND underlying=? AND expiry=? AND interval='1minute' "
                                      "AND datetime BETWEEN ? AND ?", (und, front, day + " 09:15:00", day + " 15:29:00")):
                k = (int(stamp[11:13]) - 9) * 60 + int(stamp[14:16]) - 15
                if 0 <= k < 375 and c and c > 0:
                    v[k] = c
    return v


def check():
    import exam2023 as A
    D = _D()
    # 1. the builder equals exam2023.build_tapes on seen 2024 (same sealed export, same rows)
    con = sqlite3.connect(A.SEALED.resolve().as_uri() + "?mode=ro", uri=True); con.row_factory = sqlite3.Row
    ref = A.build_tapes(2024)[0]
    con.create_function("noop", 0, lambda: 0)
    for t in ref:
        rows = con.execute("SELECT 'NIFTY' AS underlying, * FROM candles WHERE datetime BETWEEN ? AND ? ORDER BY datetime",
                           (t.day + " 09:15:00", t.day + " 15:29:00")).fetchall()
        mem = sqlite3.connect(":memory:"); mem.row_factory = sqlite3.Row
        mem.execute("CREATE TABLE candles(underlying TEXT,kind TEXT,expiry TEXT,strike REAL,opt TEXT,datetime TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL,oi REAL)")
        mem.executemany("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", [tuple(r) for r in rows])
        u = build(mem, "NIFTY", t.day, D)
        assert np.array_equal(np.nan_to_num(u.x, nan=-1), np.nan_to_num(t.x, nan=-1)) and np.array_equal(np.nan_to_num(u.f, nan=-1), np.nan_to_num(t.f, nan=-1))
        assert np.array_equal(np.nan_to_num(u.q, nan=-1), np.nan_to_num(t.q, nan=-1)) and list(u.strikes) == list(t.strikes) and u.invalid == t.invalid
        mem.close()
    con.close()
    # 2. the export matches its binding; cohorts and coverage, counts only
    b = _binding(); T = tapes()
    cov = {k: dict(days=len(v), contracts_min=min(len(t.strikes) for t in v), index_min=int(min(np.isfinite(t.x[165:, 3]).sum() for t in v)),
                   future_min=int(min(np.isfinite(t.f[165:, 3]).sum() for t in v)), invalid=int(sum(t.invalid for t in v)))
           for k, v in T.items()}
    assert {k: v["days"] for k, v in cov.items()} == b["cohorts"]
    print("CHECK_OK en4_data: builder == exam2023.build_tapes on 2024 (", len(ref), "days ); export hash matches binding")
    print("cohorts (counts only):", cov, "excluded:", [(e["und"], e["day"]) for e in b["excluded"]])


if __name__ == "__main__":
    {"export": export, "check": check}[sys.argv[1]]()
