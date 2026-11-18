"""Post-score reporting fix (not a re-score): EN58's fill-price markouts were NaN in results6.json because rows with a
missing later quote propagate NaN through the mean. This reruns the frozen, deterministic pk6.en58 and reports the
same quantities with missing values skipped, plus their counts. Writes post6-en58.json."""
import json, math, sys
from collections import defaultdict
from pathlib import Path
import numpy as np
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import pk6

P = pk6.decode(); T1 = pk6.tape(); pk6.L6.KEEP6.append(T1)
intents, rows = pk6.en58(T1, P)
g = defaultdict(list)
for r in rows:
    g[f'{r["tag"]}|{r["policy"]}|{r["proxy"]}'].append(r)
out = {}
for k, rs in sorted(g.items()):
    fl = [r for r in rs if r.get("filled")]
    def nm(key, xs):
        v = [x.get(key) for x in xs if x.get(key) is not None and not (isinstance(x.get(key), float) and math.isnan(x.get(key)))]
        return (round(float(np.mean(v)), 4) if v else None, len(v))
    out[k] = dict(n=len(rs), filled=len(fl), fill60=nm("fill60", fl), fill180=nm("fill180", fl), cost_vs_mid=nm("cost_vs_mid", fl),
                  net_8min_sum=round(sum(r["net"] for r in rs), 2), net_8min_filled_mean=nm("net", fl))
(HERE / "post6-en58.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
for k, v in out.items():
    print(k, v)
