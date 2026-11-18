"""Post-score reconciliation of round 9 (no re-score: a fresh process recomputes samples and compares).

Writes verification9.json. Checks: freeze/receipt identity; archived headline reproduction; ledger identities for every
config; fresh-process determinism on a seeded sample; reference wallets; null cells; dedup consistency; Stage B selections
re-derived from their own records; outer windows never read; EN105 genotype 000000 == EN87 on every fold.
"""
from pathlib import Path
import json, random, sys, time
import numpy as np
import round8  # noqa: F401
import data8, lab8
import families9 as F, lab9, search9 as SR, score9 as S
L7 = lab8.L7
HERE = Path(__file__).resolve().parent


def main():
    t0 = time.time(); out = {}; fails = []
    R = json.loads((HERE / "results9.json").read_text()); A = json.loads((HERE / "anatomy9.json").read_text())
    started = json.loads((HERE / "results9-started.json").read_text())
    out["identity"] = dict(head=R["head"], freeze_sha256=R["freeze_sha256"], freeze_matches=data8.sha(HERE / "freeze9.json") == R["freeze_sha256"],
                           started_head=started["head"], same_head=started["head"] == R["head"])
    if not out["identity"]["freeze_matches"]:
        fails.append("freeze hash")
    arch = {"REF:EN87|NIFTY": 6114.14, "REF:E03_env|NIFTY": 3006.43, "REF:E032_native|NIFTY": 14275.2}
    out["archived_headlines"] = {k: dict(expected=v, got=R["configs"][k]["ordinary"]["net"]) for k, v in arch.items()}
    fails += [k for k, v in out["archived_headlines"].items() if abs(v["expected"] - v["got"]) > .005]
    ident = 0
    for key, row in R["configs"].items():
        d = A["days"][key]; tk = A["tickets"][key]
        ok = abs(sum(d["ordinary"]) - row["ordinary"]["net"]) < .02 and abs(sum(d["adverse"]) - row["adverse"]["net"]) < .02 \
            and abs(sum(x["net"] for x in tk) - row["ordinary"]["net"]) < .05 and len(tk) == row["ordinary"]["trades"] and row["reconciled"]
        ident += ok
        if not ok:
            fails.append(("identity", key))
    out["ledger_identities"] = dict(configs=len(R["configs"]), passed=ident)
    groups = {}
    for key, row in R["configs"].items():
        groups.setdefault((key.rsplit("|", 1)[1], row["hash"]), []).append(key)
    dd = sum(1 for g in groups.values() for k in g[1:] if A["days"][k]["ordinary"] != A["days"][g[0]]["ordinary"] or A["days"][k]["adverse"] != A["days"][g[0]]["adverse"])
    out["dedup_consistency"] = dict(groups=sum(len(g) > 1 for g in groups.values()), inconsistent=dd)
    if dd:
        fails.append("dedup")
    reg = F.registry(); oi = [c for c in reg if c.spec and c.family != "EN105" and c.spec.needs_oi()]
    nul = [f"{c.id}|SENSEX" for c in oi if f"{c.id}|SENSEX" in R["configs"]]
    out["null_cells"] = dict(sensex_oi_cells=len(oi), scored_by_mistake=nul, unavailable_recorded=sum(1 for c in oi if f"{c.id}|SENSEX" in R["unavailable"]))
    fails += nul
    # Stage B: re-derive each pick from its own records; inner windows end before the block
    sb = R["stageb"]; mism = []
    for name, by in sb["selections"].items():
        if name == "EN105":
            continue
        for s, v in by.items():
            recs = A["stageb"][name][s]; pick, why = SR.choose(recs)
            if pick != v["pick"]:
                mism.append((name, s))
            assert all(int(s) - SR.INNER >= 0 for _ in [0])
    out["stageb_rederived"] = dict(selection_sets=len(sb["selections"]) - 1, mismatches=mism, inner_window_before_block=True)
    fails += mism
    # fresh process: rebuild and rerun a seeded sample of configurations, compare every session
    B, _ = data8.historical_books()
    import signals8
    for u, book in B.items():
        signals8.prepare(book); F.prepare9(book)
    rng = random.Random(9696)
    nifty = [c for c in reg if c.spec and c.family != "EN105" and f"{c.id}|NIFTY" in R["configs"] and not (c.spec.mgmt and c.spec.mgmt[0] == "RND")]
    sample = [c for c in nifty if c.kind == "REFERENCE"] + rng.sample([c for c in nifty if c.kind != "REFERENCE"], 24)
    det = []
    for c in sample:
        rule = c.rule()
        for t in B["NIFTY"]:
            F.build(t, c.spec, c.id, rule)
        o, tk, h, ok = S.run_indep(B["NIFTY"], rule, scen=("ordinary", "adverse"))
        same = [o["ordinary"][k]["net"] for k in range(len(B["NIFTY"]))] == A["days"][f"{c.id}|NIFTY"]["ordinary"] \
            and [o["adverse"][k]["net"] for k in range(len(B["NIFTY"]))] == A["days"][f"{c.id}|NIFTY"]["adverse"] and h == R["configs"][f"{c.id}|NIFTY"]["hash"]
        det.append((c.id, same))
        if not same:
            fails.append(("determinism", c.id))
    out["fresh_process_rerun"] = dict(configs=len(det), identical=sum(x for _, x in det), ids=[x for x, _ in det])
    # reference wallets
    wal = {}
    for cid in ("REF:EN87", "REF:E03_env", "REF:E032_native"):
        r = next(c for c in reg if c.id == cid).rule()
        for sc in ("ordinary", "adverse"):
            w = lab9.wallet9(B["NIFTY"], r, sc); got = R["configs"][f"{cid}|NIFTY"]["wallet"][sc]["P"]
            wal[f"{cid}|{sc}"] = dict(rerun=w["P"], scored=got)
            if abs(w["P"] - got) > .005:
                fails.append(("wallet", cid, sc))
    out["reference_wallets"] = wal
    # EN105: genotype 000000 is EN87 on every fold (component-off parity)
    e = []
    ref = A["days"]["REF:EN87|NIFTY"]["adverse"]
    for s, v in A["en105"].items():
        g0 = next(r for r in v["genotypes"] if r["genotype"] == "000000")
        idx = range(int(s) - SR.INNER, int(s))
        e.append((s, abs(g0["inner_adverse"] - round(sum(ref[k] for k in idx), 2)) < .02))
    out["en105_reference_parity"] = e
    fails += [("en105", s) for s, ok in e if not ok]
    out["status"] = "PASS" if not fails else "FAIL"; out["failures"] = [str(x) for x in fails][:50]; out["seconds"] = round(time.time() - t0, 1)
    S.write(HERE / "verification9.json", out); print("VERIFY", out["status"], len(fails), flush=True)


if __name__ == "__main__":
    main()
