"""SN79 - the ONE unseen test of the 1-second book (frozen before scoring, Nov 13, 2026).

Owner: "use the data of today on training ... and testing on yesterday's data".
  train: nifty-daily-1second-20261113.zip, 77 sessions Apr 6 - Jul 27, 2026 (seen by SN78);
  test:  nifty-daily-1second-20261112.zip (sealed copy, sha256 in _local/zip-1112.sha256), sessions AFTER Jul 27:
         75 sessions Jul 28 - Nov 12, 2026, never opened by any SN rule before this script.
Candidates, fixed here:
  C1 SN78's +Rs100 pick (TWAP break 1 ATR, stop 20%, target 30%, 45 min, 1 a day);
  C2 SN78's +Rs0 pick (2-bar momentum z 1.5, stop 20%, target 15%, 45 min, 3 a day);
  C3 the SN78 procedure re-run on ALL 77 training days (Gold-free days, +Rs100, >= 15 trades, best net);
  N  the same procedure on random entries.
Scored once on the test sessions at +Rs100 and +Rs0: all sessions, and Gold-free sessions where the rule is known
(an expiry day, or yesterday's ADX < 30 from the sealed year data, which ends Oct 28).
PASS for a candidate: test net > 0 at +Rs100 AND above the random pick's test net. Anything else: NOT PROVEN.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sec_data as SD  # noqa: E402
import sn78 as S8  # noqa: E402

C1 = {"fam": {"kind": "TWAPX", "buf": 1.0}, "stop": 0.2, "target": 0.3, "act": 0.0, "give": 0.5, "time": 45, "max_trades": 1}
C2 = {"fam": {"kind": "MOMO", "k": 2, "z": 1.5}, "stop": 0.2, "target": 0.15, "act": 0.0, "give": 0.5, "time": 45, "max_trades": 3}


def load_test():
    SD.ZIP = HERE / "_local" / "nifty-daily-1second-20261112.zip"
    SD.CACHE = HERE / "_local" / "seconds-1112.pkl"
    sha = hashlib.sha256(SD.ZIP.read_bytes()).hexdigest()
    assert sha == (HERE / "_local" / "zip-1112.sha256").read_text().strip()
    if not SD.CACHE.exists():
        (HERE / "_local" / "zip.sha256").read_text()
        orig = SD.build.__globals__["HERE"]
        # sec_data.build checks the zip against _local/zip.sha256; point that check at this archive's hash
        txt = (HERE / "_local" / "zip.sha256").read_text()
        (HERE / "_local" / "zip.sha256").write_text(sha)
        try:
            SD.build()
        finally:
            (HERE / "_local" / "zip.sha256").write_text(txt)
    return SD.load()["days"]


def make_days(raw, gd, adx, after=None):
    out = []
    for d, r in sorted(raw.items()):
        if after and d <= after:
            continue
        if "PE" in r["series"] and "CE" in r["series"]:
            out.append(S8.Day(d, r, bool(gd.get(d, {}).get("trades")), (adx.get(d) or {}).get("adx")))
    return out


def pick(days, fams, stress):
    best, cfg_best = None, None
    for fam, ex, mt in itertools.product(fams, S8.EXITS, (1, 3)):
        cfg = {"fam": fam, **ex, "max_trades": mt}
        s = S8.summary(S8.evaluate(days, cfg, stress, "gold_free"))
        if s["trades"] >= 15 and (best is None or s["net"] > best["net"]):
            best, cfg_best = s, cfg
    return cfg_best, best


if __name__ == "__main__":
    out_path = HERE / "results-sn79.json"
    if out_path.exists():
        raise SystemExit("SN79 is scored once")
    gd = {r["day"]: r for r in json.loads((HERE.parent / "2026-11-13-sn76" / "_local" / "days.json").read_text(encoding="utf-8"))}
    adx = json.loads((HERE.parent / "2026-11-12-sn06" / "_local" / "daily.json").read_text(encoding="utf-8"))
    train = make_days(SD.load()["days"], gd, adx)
    rng = random.Random(79)
    nulls = [{"kind": "RANDOM", "p": p, "seed": rng.randrange(1, 10 ** 6)} for p in (0.01, 0.02, 0.05) for _ in range(9)]
    C3, c3_train = pick(train, S8.ENTRY, 100.0)
    N, n_train = pick(train, nulls, 100.0)
    test = make_days(load_test(), gd, adx, after="2026-07-27")
    known = [D for D in test if D.expiry or D.adx is not None]
    res = {"train_days": len(train), "test_days": len(test), "test_gold_free_known": sum(D.gold_free() for D in known),
           "C3": C3, "C3_train": c3_train, "N": N, "N_train": n_train, "scores": {}}
    for name, cfg in (("C1", C1), ("C2", C2), ("C3", C3), ("N", N)):
        for stress in (100.0, 0.0):
            res["scores"][f"{name}|{int(stress)}|all"] = S8.summary(S8.evaluate(test, cfg, stress, "all"))
            res["scores"][f"{name}|{int(stress)}|gold_free"] = S8.summary(S8.evaluate(known, cfg, stress, "gold_free"))
    n100 = res["scores"]["N|100|all"]["net"]
    res["verdict"] = {c: ("PASS" if res["scores"][f"{c}|100|all"]["net"] > 0 and res["scores"][f"{c}|100|all"]["net"] > n100 else "NOT PROVEN")
                      for c in ("C1", "C2", "C3")}
    out_path.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k != "scores"}, indent=0)[:1500])
    for k, v in res["scores"].items():
        print(k, v)
