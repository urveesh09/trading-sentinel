"""Erratum support: per-expiry EN55 - E03.2 differences on the seen development books (fixed-cap, ordinary)."""
import sys, json, math, time
from pathlib import Path
LAB = str(Path(__file__).resolve().parent)
sys.path.insert(0, LAB)
import numpy as np
import en_lab5 as L5
t0 = time.time()
L5.install(); B = L5.books()
out = {}
for name, book in B.items():
    a = L5.run_fixed(book, L5.ARMS["E032_30k"]); b = L5.run_fixed(book, L5.ARMS["EN55"])
    da = np.array([d["net"] for d in a["days"]]); db = np.array([d["net"] for d in b["days"]])
    ta = np.array([d["trades"] for d in a["days"]]); tb = np.array([d["trades"] for d in b["days"]])
    diff = db - da; aff = int(np.sum(np.abs(diff) > .005))
    sd = float(np.std(diff, ddof=1)); sdb = float(np.std(db, ddof=1))
    z = 1.6449 + 0.8416
    out[name] = dict(sessions=len(book), e032_net=round(float(da.sum()),2), en55_net=round(float(db.sum()),2),
                     en55_parents=int(tb.sum()), en55_parent_rate=round(float(tb.sum())/len(book),3), e032_parents=int(ta.sum()),
                     sessions_with_en55_ticket=int(np.sum(tb>0)), affected_sessions=aff, affected_rate=round(aff/len(book),3),
                     diff_mean=round(float(diff.mean()),2), diff_sd=round(sd,2), en55_sd=round(sdb,2),
                     n_for_50_per_expiry_diff=math.ceil((z*sd/50)**2), n_for_50_per_expiry_abs=math.ceil((z*sdb/50)**2),
                     sessions_for_20_parents=math.ceil(20/(float(tb.sum())/len(book))))
print(json.dumps(out, indent=1)); print("secs", round(time.time()-t0))
(Path(LAB) / "power-erratum.json").write_text(json.dumps(out, indent=1) + chr(10), encoding="utf-8")
