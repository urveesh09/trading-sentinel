"""Post-score reporting fixes (not a re-score; the frozen verdicts in results7.json stand). Writes post7-fixes.json.

(a) EN82's SENSEX cell.

The frozen prep7.n11 filled the ADX gate only from NIFTY records (`if r["und"] == "NIFTY"`). SENSEX expiry dates are
never NIFTY sessions in the N11 file, so EN82 on SENSEX found no ADX and never traded. PLAN7 says SENSEX reads NIFTY's
ADX, and every SENSEX record in n11-signals.json carries exactly that value (n11x computes it from NIFTY's daily bars
for every underlying). This reruns the frozen EN82 arms on SENSEX with the gate read from those records, nothing else
changed, and reports the cell next to its frozen result.
(b) EN71's paired-side share (the audit's F2 reproduction): frontier7.paired_side_share was fed library rows pooled over
all sessions without the session key, so rows from different days collided. Recomputed per session.
(c) Descriptive only: how much EN75 and EN83 (NIFTY) overlap - same session and side - and the correlation of their
per-session nets. No combination is formed or scored."""
import json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import score7 as S  # noqa: E402

L7, P7 = S.L7, S.P7
L7.L5.install(); B = L7.L6.books()
P7.prepare(B)
missing_before = sum(1 for t in B["SENSEX"] if ("ADX", t.day) not in L7.GATE7)
for t in B["SENSEX"]:
    r = L7.N11.get(("SENSEX", t.day))
    if r and not r.get("missing") and ("ADX", t.day) not in L7.GATE7:
        L7.GATE7[("ADX", t.day)] = r["adx"]
by = S.S6.daymap(B); out = dict(sensex_sessions_without_adx_in_frozen_run=missing_before)
keep = {}
for name in ("E03_env", "EN82", "EN82_adx25_diag", "EN82_inv_ctl"):
    res, kp = S.run_arm(name, L7.ARMS[name], B["SENSEX"], by); keep[name] = kp
    out[name] = {k: res[k] for k in ("ordinary", "adverse", "wallet|ordinary")}
st = S.paired(keep["EN82"]["ordinary"], keep["E03_env"]["ordinary"], 20000, S._seed("EN82|SENSEX"))
st["tail_wins"] = len({d["day"] for d in keep["EN82"]["ordinary"] if d["net"] >= 2500})
fr = json.loads((HERE / "results7.json").read_text())
st["holm_note"] = "Holm is not recomputed: the frozen family's adjusted values stand; this cell's raw p is shown"
out["paired_vs_E03_env"] = st
out["frozen_verdict"] = fr["hypotheses"]["EN82|SENSEX"]["verdict"]
st["holm"] = 1.
out["verdict_with_gate"] = S.classify("EN82|SENSEX", out["EN82"]["ordinary"], out["EN82"]["adverse"], st, out["E03_env"]["ordinary"],
                                      dict(liq_dd=out["EN82"]["wallet|ordinary"]["liq_dd"]), out["E03_env"]["wallet|ordinary"])
import numpy as np
from collections import defaultdict
tot = dict(rows=0, in_pairs=0)
for t in B["NIFTY"]:
    keys = defaultdict(set)
    rows = [r for r in L7.L6.library(t) if r[4] == 2500. and r[7] == 8 and r[6] == L7.L6.ST["FILLED"]]
    for r in rows:
        keys[(r[0], r[3])].add(r[2])
    tot["rows"] += len(rows); tot["in_pairs"] += sum(len(v) for v in keys.values() if len(v) == 2)
tot["share"] = round(tot["in_pairs"] / max(1, tot["rows"]), 4)
out["EN71_paired_side_NIFTY_per_session"] = tot
A = json.loads((HERE / "anatomy7.json").read_text())["days"]
x = [d["net"] for d in A["EN75|NIFTY"]]; y = [d["net"] for d in A["EN83|NIFTY"]]
same = both = 0
for t in B["NIFTY"]:
    a = L7.PRE7[("SYNF75", "NIFTY", t.day)]; b = L7.PRE7[("OI83", "NIFTY", t.day)]
    w = (t.minute >= 780) & (t.minute < 870)
    sa = {int(v) for v in a[w] if v}; sb = {int(v) for v in b[w] if v}
    both += bool(sa and sb); same += bool(sa & sb)
out["EN75_EN83_overlap_NIFTY"] = dict(sessions_both_signal=both, sessions_same_side=same, net_correlation=round(float(np.corrcoef(x, y)[0, 1]), 3))
(HERE / "post7-fixes.json").write_text(json.dumps(out, indent=1, default=float) + "\n", encoding="utf-8")
print("F2", tot, out["EN75_EN83_overlap_NIFTY"])
print(json.dumps({k: (v["ordinary"]["net"], v["ordinary"]["tickets"]) if isinstance(v, dict) and "ordinary" in v else v for k, v in out.items()
                  if k != "paired_vs_E03_env"}, default=str))
print("EN82|SENSEX paired", {k: st[k] for k in ("diff_per_session", "ci", "p_vs_control")})
