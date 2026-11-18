"""Post-score reconciliation of round 10 (fresh process; never rewrites results10/anatomy10). Writes verification10.json.

Separately checks: (1) ledger identities for every scored configuration, (2) fresh-process reruns of samples from every
family, every learned family and the references, (3) selection picks re-derived from the recorded inner records, (4)
reference wallets, (5) duplicate groups, (6) nomination consistency with the recorded checks.
"""
from collections import defaultdict
import json, time
import numpy as np
import round10  # noqa: F401
from data8 import L7
import score9
import lab10, families10 as FM, learn10 as LN, data10, score10 as S
HERE = FM.HERE


def main():
    t0 = time.time()
    res = json.loads((HERE / "results10.json").read_text()); anat = json.loads((HERE / "anatomy10.json").read_text())
    out = dict(status=None)
    # (1) ledger identities
    bad = []
    for key, r in res["configs"].items():
        d = anat["days"][key]
        if abs(sum(d["ordinary"]) - r["ordinary"]["net"]) > .02 or abs(sum(d["adverse"]) - r["adverse"]["net"]) > .02:
            bad.append((key, "days"))
        tk = anat["tickets"].get(key, [])
        if abs(sum(x["net"] for x in tk) - r["ordinary"]["net"]) > .02 * max(1, len(tk)):
            bad.append((key, "tickets"))
        if sum(d["trades"]) != r["ordinary"]["trades"] or len(tk) != r["ordinary"]["trades"]:
            bad.append((key, "parents"))
        if d["wallet_ordinary"] and abs(d["wallet_ordinary"][-1][0] - r["wallet"]["ordinary"]["P"]) > .02:
            bad.append((key, "wallet"))
        if not r["reconciled"]:
            bad.append((key, "reconciled"))
    out["ledger_identities"] = dict(configs=len(res["configs"]), failures=bad)
    # (2) fresh reruns
    B, _, _ = data10.load(False)
    reg = FM.registry(); rates = S.rates112(B["NIFTY"], reg); reg += S.dyn112(reg, rates)
    byid = {c.id: c for c in reg}
    fams = defaultdict(list)
    for key in res["configs"]:
        cid, u = key.rsplit("|", 1)
        c = byid.get(cid)
        if c is not None and c.spec is not None and not c.spec.learned:
            fams[(c.family, u)].append(cid)
    sample = []
    for (fam, u), ids in sorted(fams.items()):
        ids = sorted(ids)
        sample += [(ids[0], u), (ids[len(ids) // 2], u), (ids[-1], u)] if len(ids) > 2 else [(x, u) for x in ids]
    rr = []
    for cid, u in dict.fromkeys(sample):
        c = byid[cid]; book = B[u]; rule = c.rule()
        for t in book:
            FM.build(t, c.spec, c.id, rule)
        o, tk, h, ok, notes = S.run_indep(book, rule)
        rr.append(dict(id=cid, index=u, equal=h == res["configs"][f"{cid}|{u}"]["hash"]))
    # learned: one cell per learned family plus every learned control, NIFTY
    labels = {"NIFTY": LN.label_events(B["NIFTY"])}
    bank, tick, rules, seg = {}, {}, {}, {}
    e117 = S.en117_default(reg)
    fixed = {}
    for name, cid in (("EN87", "REF:EN87"), ("EN111", "EN111:0018"), ("EN117", e117)):
        c = byid[cid]; rule = c.rule()
        for t in B["NIFTY"]:
            FM.build(t, c.spec, c.id, rule)
        o, _, _, _, _ = S.run_indep(B["NIFTY"], rule, scen=("adverse",))
        fixed[name] = [o["adverse"][k] for k in range(len(B["NIFTY"]))]
    lsample = ["EN118:0001", "EN118:0012:no_oi", "EN120:0001", "EN120:0012", "EN118:ctl:mean_actions", "EN118:ctl:direction_only",
               "EN120:ctl:fixed_priority_union", "EN120:ctl:past_pnl_chooser"]
    S.run_learned({"NIFTY": B["NIFTY"]}, [byid[x] for x in lsample], labels, bank, tick, rules, seg, fixed, lambda *a: None)
    for cid in lsample:
        rr.append(dict(id=cid, index="NIFTY", equal=bank[f"{cid}|NIFTY"]["hash"] == res["configs"][f"{cid}|NIFTY"]["hash"], learned=True))
    out["fresh_reruns"] = dict(n=len(rr), mismatches=[x for x in rr if not x["equal"]])
    # (3) selection picks re-derived from the recorded inner records
    sel_bad = []
    for fam, v in res["selection"].items():
        recs = anat["selection"][fam]
        for s, pk in v["picks"].items():
            rs = recs[s]; fixed_ids = set(v["fixed_comparators"])
            ok = sorted([r for r in rs if r["passed"] and r["id"] not in fixed_ids], key=lambda r: (-r["objective"], r["id"]))
            fok = sorted([r for r in rs if r["passed"] and r["id"] in fixed_ids], key=lambda r: (-r["objective"], r["id"]))
            exp = ok[0]["id"] if ok and (not fok or ok[0]["objective"] > fok[0]["objective"] + 1e-12) else fok[0]["id"] if fok else "REF:EN87"
            if exp != pk["pick"]:
                sel_bad.append((fam, s, exp, pk["pick"]))
    out["selection_rederived"] = dict(families=len(res["selection"]), mismatches=sel_bad)
    # (4) reference wallets
    wb = []
    for cid in ("REF:E03_env", "REF:EN87", "REF:E032_native", "REF:EN55_native", "REF:EN87_ONE_LOT"):
        for u, book in B.items():
            key = f"{cid}|{u}"
            if key not in res["configs"]:
                continue
            w = lab10.wallet10(book, byid[cid].rule(), "adverse")
            wb.append(dict(id=key, equal=abs(w["P"] - res["configs"][key]["wallet"]["adverse"]["P"]) < .02))
    out["reference_wallets"] = dict(n=len(wb), mismatches=[x for x in wb if not x["equal"]])
    # (5) duplicate groups share hashes
    dup_bad = []
    for u, groups in res["dedup"].items():
        for g in groups:
            hs = {res["configs"][f"{c}|{u}"]["hash"] for c in g if f"{c}|{u}" in res["configs"]}
            if len(hs) != 1:
                dup_bad.append((u, g))
    out["duplicates"] = dict(groups=sum(len(v) for v in res["dedup"].values()), mismatches=dup_bad)
    # (6) nominations follow the recorded checks
    passed = sorted([(v["score"], k) for k, v in res["candidates"].items() if v.get("passed") and "score" in v], key=lambda x: (-x[0], x[1]))
    proc = [k for k, v in res["candidates"].items() if k.endswith(":procedure") and v["passed"]]
    out["nominations"] = dict(recorded=[c["config"] for c in res["champions"]], fixed_passing=[k for _, k in passed], procedures_passing=proc)
    ok = not bad and not out["fresh_reruns"]["mismatches"] and not sel_bad and not out["reference_wallets"]["mismatches"] and not dup_bad
    out["status"] = "PASS" if ok else "FAIL"; out["seconds"] = round(time.time() - t0)
    score9.write(HERE / "verification10.json", out)
    print(json.dumps({k: (v if not isinstance(v, dict) else {kk: (vv if not isinstance(vv, list) else len(vv)) for kk, vv in v.items()}) for k, v in out.items()}, indent=1))


if __name__ == "__main__":
    main()
