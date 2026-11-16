"""SN301 / SN303 / SN300a / SN315: the verified archive, Gold's day labels and the amended forward verdict (PLAN.md,
frozen at 94c772cd). Replaces sn286/fwd.py's collect (which stays unchanged, unused). Research only: Production's tick
folders and SN Gold tables are read (docker cp / read-only sqlite), never written; nothing prints money before the verdict.

  python fwd2.py collect           every closed session >= 2026-11-17 not yet archived: copy to a temporary folder, verify
                                   every manifest chunk (bytes, SHA-256), publish to _local/archive/<day>, write the receipt
                                   (hashes, completeness, events, SN289 coverage, Gold's day label), then score the day once
                                   with the original fw.run and the amended fw2.run into _local/forward2/<day>.json.
                                   Prints counts only. A failed copy is discarded and retried on the next run.
  python fwd2.py recheck DAY       copy DAY again and compare every hash with its receipt.
  python fwd2.py dev FOLDER        run fw2 on a development folder; counts only.
  python fwd2.py verdict           once 20 sessions are verified and qualified: SN300a (decides) and the original verdict
                                   (superseded), with SN305-SN309 and the SN315 block length; writes results-sn300a.json once.
"""
from __future__ import annotations

import collections
import datetime as dt
import hashlib
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import pytz

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import fw2  # noqa: E402

fw = fw2.fw
tk = fw2.tk
LOCAL = HERE / "_local"
ARCH, TMP, REC, FWD = LOCAL / "archive", LOCAL / "tmp", LOCAL / "receipts", LOCAL / "forward2"
START = "2026-11-17"
N_SESSIONS = 20
CAS_FROM = "2026-12-07"
CONTAINER = "python-engine"
IST = pytz.timezone("Asia/Kolkata")
RESERVE = 15000.0


def now_ist():
    return dt.datetime.now(IST)


def sh(cmd, check=True):
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def recorded_days():
    r = sh(["docker", "exec", "-u", "quantuser", CONTAINER, "sh", "-c", "ls /data/research/ticks"])
    return sorted(x for x in r.stdout.split() if len(x) == 10 and x >= START)


def closed(day):
    n = now_ist()
    return day < n.date().isoformat() or (day == n.date().isoformat() and n.time() >= dt.time(15, 50))


def copy_verified(day):
    """(folder, receipt) of a fresh verified copy in TMP, or (None, reason)."""
    TMP.mkdir(parents=True, exist_ok=True)
    tmp = TMP / f"{day}-{int(now_ist().timestamp())}"
    if tmp.exists():
        shutil.rmtree(tmp)
    r = sh(["docker", "cp", f"{CONTAINER}:/data/research/ticks/{day}", str(tmp)], check=False)
    if r.returncode != 0:
        return None, "copy_failed"
    try:
        man = json.loads((tmp / "manifest.json").read_text(encoding="utf-8"))
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        return None, "no_manifest"
    bad = []
    for c in man.get("chunks", []):
        p = tmp / c["file"]
        if not p.exists() or p.stat().st_size != int(c["bytes"]) or sha(p) != c["sha256"]:
            bad.append(c["file"])
    listed = {c["file"] for c in man.get("chunks", [])}
    extra = sorted(p.name for p in tmp.glob("chunk-*") if p.name not in listed)
    if bad or not man.get("chunks"):
        shutil.rmtree(tmp, ignore_errors=True)
        return None, f"hash_mismatch:{len(bad)}" if bad else "no_chunks"
    ev = (tmp / "events.jsonl").read_text(encoding="utf-8").splitlines() if (tmp / "events.jsonl").exists() else []
    kinds = collections.Counter(json.loads(x).get("event", "?") for x in ev if x.strip())
    rec = {"day": day, "copied_at": now_ist().isoformat(), "complete": bool(man.get("complete")), "chunks": len(listed),
           "bytes": sum(int(c["bytes"]) for c in man["chunks"]), "records": sum(int(c.get("records", 0)) for c in man["chunks"]),
           "unlisted_files": extra, "events": dict(kinds),
           "hashes": {p.name: sha(p) for p in sorted(tmp.iterdir()) if p.is_file()}}
    return tmp, rec


GOLD_Q = ("import json,sqlite3,sys; d=sys.argv[1]; c=sqlite3.connect('file:/data/cache.db?mode=ro', uri=True); "
          "r=c.execute('SELECT trades,net,wallet_before,closed_at FROM sn_gold_days WHERE session_date=?',(d,)).fetchone(); "
          "p=c.execute('SELECT entry_time,exit_time,status FROM sn_gold_positions WHERE session_date=?',(d,)).fetchall(); "
          "print(json.dumps({'row': None if r is None else {'trades': r[0], 'wallet_before': r[2], 'closed_at': r[3]}, 'positions': p}))")


def gold_label(day):
    """SN303: GOLD / FLAT / UNKNOWN from Production's day-close row and positions (read-only)."""
    r = sh(["docker", "exec", "-u", "quantuser", CONTAINER, "python", "-c", GOLD_Q, day], check=False)
    if r.returncode != 0:
        return {"label": "UNKNOWN", "why": "query_failed"}
    g = json.loads(r.stdout)
    row, pos = g["row"], g["positions"]
    if row is None:
        return {"label": "UNKNOWN", "why": "no_close_row", "positions": pos}
    if row["trades"] > 0 and len(pos) == row["trades"] and all(p[2] == "CLOSED" for p in pos):
        lab = "GOLD"
    elif row["trades"] == 0 and not pos:
        lab = "FLAT"
    else:
        lab = "UNKNOWN"
    return {"label": lab, "trades": row["trades"], "wallet_before": row["wallet_before"], "closed_at": row["closed_at"], "positions": pos}


def score(folder):
    loaded = fw2.load_day(folder)
    v2 = fw2.run(folder, loaded)
    orig_loader = tk.load_day
    tk.load_day = lambda _folder, keep=None: loaded          # the original scorer gets the same decoded arrays
    try:
        orig = fw.run(folder)
    finally:
        tk.load_day = orig_loader
    return {"orig": orig, "v2": v2}


def collect():
    for p in (ARCH, REC, FWD):
        p.mkdir(parents=True, exist_ok=True)
    for day in recorded_days():
        if not closed(day):
            continue
        if not (ARCH / day).exists():
            tmp, rec = copy_verified(day)
            if tmp is None:
                with open(REC / "rejects.jsonl", "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"day": day, "at": now_ist().isoformat(), "why": rec}) + "\n")
                print("rejected", day, rec, flush=True)
                continue
            rec["gold"] = gold_label(day)
            tmp.rename(ARCH / day)
            (REC / f"{day}.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
        rec = json.loads((REC / f"{day}.json").read_text(encoding="utf-8"))
        if rec.get("gold", {}).get("label") == "UNKNOWN":
            rec["gold"] = gold_label(day)
            (REC / f"{day}.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
        if not (FWD / f"{day}.json").exists():
            res = score(ARCH / day)
            (FWD / f"{day}.json").write_text(json.dumps(res, default=float), encoding="utf-8")
            q = res["v2"]["qualify"]
            rec["qualify"] = {k: q.get(k) for k in ("ok", "future_minute_coverage", "future_max_gap_s", "atm_minute_coverage", "expiry_day")}
            (REC / f"{day}.json").write_text(json.dumps(rec, indent=1), encoding="utf-8")
        q = rec.get("qualify", {})
        print("archived", day, "complete", rec["complete"], "chunks", rec["chunks"], "qualified", q.get("ok"),
              "gold", rec.get("gold", {}).get("label"), flush=True)


def recheck(day):
    rec = json.loads((REC / f"{day}.json").read_text(encoding="utf-8"))
    tmp, rec2 = copy_verified(day)
    if tmp is None:
        raise SystemExit(f"recheck copy failed: {rec2}")
    same = {k: rec["hashes"].get(k) == v for k, v in rec2["hashes"].items() if k.startswith("chunk-")}
    shutil.rmtree(tmp, ignore_errors=True)
    print(day, "chunks identical:", all(same.values()), len(same), "listed in receipt:", sum(k.startswith("chunk-") for k in rec["hashes"]))


def dev(folder):
    res = fw2.run(Path(folder))
    cnt = lambda rows: dict(collections.Counter("filled" if not r.get("missed") else r.get("why") for r in rows))  # noqa: E731
    print("qualify", {k: res["qualify"].get(k) for k in ("ok", "future_minute_coverage", "atm_minute_coverage")}, "offset", res["offset_s"])
    for slot in ("SN291", "SN293"):
        if slot in res:
            print(slot, {k: cnt(v) for k, v in res[slot].items() if isinstance(v, list) and k != "pairs"}, "pairs", len(res[slot]["pairs"]))


# ---- the verdict ------------------------------------------------------------------------------------------------------
def executed(rows):
    return [r for r in rows if not r.get("missed")]


def slot_verdict(slot, q, res, labels):
    by_day = {d: executed(res[d]["v2"][slot]["candidate"]) for d in q}
    nets = {d: sum(r["net205"] for r in rs) for d, rs in by_day.items()}
    n400 = sum(r["net400"] for rs in by_day.values() for r in rs)
    trades = sum(len(rs) for rs in by_day.values())
    sess = sum(1 for rs in by_day.values() if rs)
    tot = sum(nets.values())
    best = max(nets.values()) if nets else 0.0
    flat = [d for d in q if labels[d]["label"] == "FLAT"]
    flat_net = sum(nets[d] for d in flat)
    pairs = [p for d in q for p in res[d]["v2"][slot]["pairs"] if not p.get("cand_missed", True) and not p.get("ctrl_missed", True)
             and p.get("cand205") is not None and p.get("ctrl205") is not None]
    diffs = [p["cand205"] - p["ctrl205"] for p in pairs]
    # SN299 / SN305: the one-wallet contract on FLAT sessions (debit <= wallet - 15,000; a full stop must fit the 20% room)
    wallet_net, adm, blocked, strict = 0.0, 0, collections.Counter(), 0
    for d in q:
        w = float(labels[d].get("wallet_before") or 30000.0)
        pos = labels[d].get("positions") or []
        realized = 0.0
        for r in sorted(by_day[d], key=lambda x: x["fill_t"]):
            strict += r["debit"] <= 3000.0
            if r["debit"] > w - RESERVE:
                blocked["debit_over_wallet_contract"] += 1
                continue
            if pos and gold_overlap(d, pos, r):
                blocked["gold_open_or_entering"] += 1
                continue
            if 0.2 * w + realized < fw2.STOP:
                blocked["day_room_used"] += 1
                continue
            realized += r["net205"]
            adm += 1
            if labels[d]["label"] == "FLAT":
                wallet_net += r["net205"]
    out = {"trades": trades, "sessions_with_trades": sess, "net205": round(tot), "net400": round(n400),
           "without_best_session": round(tot - best), "flat_sessions": len(flat), "flat_net": round(flat_net),
           "per_flat_session": round(flat_net / len(flat)) if flat else None, "pairs": len(pairs),
           "pair_mean_diff205": round(sum(diffs) / len(diffs), 1) if diffs else None,
           "pairs_candidate_better": sum(x > 0 for x in diffs),
           "wallet_flat_net": round(wallet_net), "wallet_admitted": adm, "wallet_blocks": dict(blocked),
           "fits_strict_3000_debit": strict,
           "status": dict(collections.Counter(r["status"] for rs in by_day.values() for r in rs)),
           "missed": dict(collections.Counter(r.get("why") for d in q for r in res[d]["v2"][slot]["candidate"] if r.get("missed"))),
           "cas": {k: round(sum(nets[d] for d in q if (d >= CAS_FROM) == (k == "from_dec7"))) for k in ("before_dec7", "from_dec7")}}
    unknown = [d for d in q if labels[d]["label"] == "UNKNOWN"]
    if unknown or len(flat) < 8 or trades < 30 or sess < 10 or len(pairs) < 20:
        out["verdict"] = "INSUFFICIENT"
        out["insufficient_because"] = {"unknown_gold_days": unknown, "flat_sessions": len(flat), "trades": trades, "sessions": sess, "pairs": len(pairs)}
    else:
        ok = tot > 0 and n400 > 0 and sum(diffs) / len(diffs) > 0 and tot - best > 0 and flat_net > 0 and wallet_net > 0
        out["verdict"] = "PASS" if ok else "FAIL"
    # SN306 / SN307 diagnostics on the same decisions
    ex = [r for rs in by_day.values() for r in rs]
    out["SN306_entry_latency"] = {L: round(sum(r["entry_lat"].get(L) or 0.0 for r in ex if "entry_lat" in r)) for L in map(str, fw2.LAT_GRID)}
    out["SN306_exit_latency"] = {L: round(sum(r["exit_lat"].get(L) or 0.0 for r in ex if "exit_lat" in r)) for L in map(str, fw2.LAT_GRID)}
    out["SN306_entry_misses"] = {L: sum(1 for r in ex if "entry_lat" in r and r["entry_lat"].get(L, 0.0) is None) for L in map(str, fw2.LAT_GRID)}
    out["SN307_capped"] = {"net205": round(sum(r.get("capped205", 0.0) for r in ex)), "skipped": sum(r.get("capped_skip", False) for r in ex)}
    return out, nets


def gold_overlap(day, positions, r):
    t0 = IST.localize(dt.datetime.fromisoformat(day + "T09:15:00"))
    for entry, exit_, _st in positions:
        a = (dt.datetime.fromisoformat(entry) - t0).total_seconds()
        b = (dt.datetime.fromisoformat(exit_) - t0).total_seconds() if exit_ else 1e9
        if a <= r["tx"] and b >= r["fill_t"] - 3:
            return True
    return False


def original_verdict(q, res):
    """sn286/fwd.py's verdict rules on the same days (superseded: Gold days from positions only; raw control totals)."""
    gd = {d for d in q if (json.loads((REC / f"{d}.json").read_text(encoding="utf-8")).get("gold", {}).get("positions"))}
    out = {}
    for slot, ctl in (("SN291", "control"), ("SN293", "control")):
        rows = {d: res[d]["orig"].get(slot, {}) for d in q}
        cn = {d: sum(x["net205"] for x in r.get("candidate", []) if x.get("net205") is not None) for d, r in rows.items()}
        c4 = sum(x["net400"] for r in rows.values() for x in r.get("candidate", []) if x.get("net400") is not None)
        kn = sum(x["net205"] for r in rows.values() for x in r.get(ctl, []) if x.get("net205") is not None)
        ct = sum(1 for r in rows.values() for x in r.get("candidate", []) if x.get("net205") is not None)
        cs = sum(1 for d, r in rows.items() if any(x.get("net205") is not None for x in r.get("candidate", [])))
        tot = sum(cn.values())
        gap = sum(cn[d] for d in q if d not in gd)
        best = max(cn.values()) if cn else 0.0
        v = "INSUFFICIENT" if ct < 30 or cs < 10 else ("PASS" if tot > 0 and c4 > 0 and tot > kn and tot - best > 0 and gap > 0 else "FAIL")
        out[slot] = {"verdict_superseded": v, "net205": round(tot), "net400": round(c4), "control205": round(kn), "trades": ct, "gap_net": round(gap)}
    return out


def verdict():
    out = HERE / "results-sn300a.json"
    if out.exists():
        raise SystemExit("SN300a is scored once")
    days = sorted(p.stem for p in FWD.glob("*.json") if p.stem >= START)
    res = {d: json.loads((FWD / f"{d}.json").read_text(encoding="utf-8")) for d in days}
    q = [d for d in days if res[d]["v2"]["qualify"]["ok"]][:N_SESSIONS]
    if len(q) < N_SESSIONS:
        raise SystemExit(f"only {len(q)} verified qualified sessions: SN300a waits for {N_SESSIONS}")
    labels = {}
    for d in q:
        rec = json.loads((REC / f"{d}.json").read_text(encoding="utf-8"))
        lab = rec.get("gold") or {"label": "UNKNOWN"}
        if lab["label"] == "UNKNOWN":
            lab = gold_label(d)
        labels[d] = lab
    result = {"sessions": q, "labels": {d: labels[d]["label"] for d in q}, "candidates": {}, "frozen_plan": "94c772cd"}
    for slot in ("SN291", "SN293"):
        result["candidates"][slot], _nets = slot_verdict(slot, q, res, labels)
    c291 = [r for d in q for r in executed(res[d]["v2"]["SN291"]["candidate"])]
    for arm in ("ofi", "ofi_and_static", "premise_exit", "control_all"):
        ex = [r for d in q for r in executed(res[d]["v2"]["SN291"][arm])]
        result[f"SN291_{arm}"] = {"trades": len(ex), "net205": round(sum(r["net205"] for r in ex)),
                                  "per_trade": round(sum(r["net205"] for r in ex) / len(ex), 1) if ex else None,
                                  "worst": round(min((r["net205"] for r in ex), default=0.0))}
    result["SN291_candidate_reference"] = {"trades": len(c291), "per_trade": round(sum(r["net205"] for r in c291) / len(c291), 1) if c291 else None,
                                           "worst": round(min((r["net205"] for r in c291), default=0.0))}
    result["original_verdict_superseded"] = original_verdict(q, res)
    passed = [s for s, r in result["candidates"].items() if r["verdict"] == "PASS"]
    if passed:
        rate = min(result["candidates"][s]["trades"] for s in passed) / len(q)
        result["SN315_next_block_sessions"] = min(40, max(20, math.ceil(30 / rate))) if rate > 0 else 40
    print(json.dumps(result, indent=1), flush=True)
    out.write_text(json.dumps(result, indent=1, default=float), encoding="utf-8")


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "collect":
        collect()
    elif cmd == "recheck":
        recheck(sys.argv[2])
    elif cmd == "dev":
        dev(sys.argv[2])
    elif cmd == "verdict":
        verdict()
    else:
        raise SystemExit(__doc__)
