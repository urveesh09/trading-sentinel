"""Integration parity against already frozen results; no new strategy selection."""
import asyncio
import hashlib
import json
from pathlib import Path

import replay as R


def key(p):return p["play"],p["symbol"],p["entry_ts"]


def economics(p):
    result={k:p.get(k) for k in ("symbol","token","lot_size","lots","lots_open","entry_ts","entry_price","max_loss","peak","stop","banked","exit_pending","status","gross","costs","net_pnl","assumed_pnl","bank_pending","side","width","execution","fee_snapshot")}
    result["events"]=[{k:v for k,v in e.items() if k not in ("e01_version","paired_primary_id")} for e in p["events"]]
    return result


async def main():
    # The original application was archived BEFORE integration. Never silently
    # re-freeze its changed working-tree files or rewrite past results.
    f=json.loads((R.HERE/"freeze-round1-v2.json").read_text())
    for name,h in f["sources"].items():
        assert hashlib.sha256((R.LOCAL/"frozen-source"/name).read_bytes()).hexdigest()==h,name
    for name,h in f["inputs"].items():assert hashlib.sha256((R.ROOT/name).read_bytes()).hexdigest()==h,name
    R.disable_network();checks=[]
    for adverse in (False,True):
        for day,u in R.sessions():
            suffix="adverse" if adverse else "ordinary"
            result=await R.run_one(day,u,policy="NATIVE_E01_FINAL",adverse=adverse)
            baseline=json.loads((R.LOCAL/"evals"/f"{day}-{u}-BASE-{suffix}.json").read_text())
            candidate=json.loads((R.LOCAL/"evals"/f"{day}-{u}-CSTOP_30-{suffix}.json").read_text())
            old={key(p):economics(p) for p in baseline["positions"] if p["play"] in ("A","B","C")}
            new={key(p):economics(p) for p in result["positions"] if p["play"] in ("A","B","C")}
            assert new==old,("primary changed",day,adverse)
            selected={p["entry_ts"]:economics(p) for p in candidate["positions"] if p["play"]=="C"}
            shadows={p["entry_ts"]:economics(p) for p in result["positions"] if p["play"]=="CE01"}
            assert shadows==selected,("E01 differs from frozen CSTOP30",day,adverse)
            primaries={p["id"]:p for p in result["positions"] if p["play"]=="C"}
            for p in result["positions"]:
                if p["play"]=="CE01":
                    twin=primaries[p["events"][0]["paired_primary_id"]]
                    assert (p["symbol"],p["entry_ts"],p["lots"],p["entry_price"])==(twin["symbol"],twin["entry_ts"],twin["lots"],twin["entry_price"])
                    assert p["max_loss"]==twin["max_loss"]<=2500
            assert result["provider_calls"]==baseline["provider_calls"],"extra quote request"
            e01whole=sum(p["net_pnl"]+(p.get("assumed_pnl") or 0) for p in result["positions"] if p["play"] in ("A","B","CE01"))
            assert abs(e01whole-candidate["primary"]["modeled_net"])<.02
            checks.append(dict(day=day,underlying=u,adverse=adverse,main_unchanged=True,e01_exact=True,provider_calls_unchanged=True,shadow_entries=len(shadows)))
    (R.HERE/"native-parity-final.json").write_text(json.dumps({"passed":True,"cases":checks,"original_source":"cbbdebb","new_model_selection":False},indent=2)+"\n",encoding="utf-8")
    print("NATIVE_PARITY_PASS",len(checks),"cases",sum(c["shadow_entries"] for c in checks),"paired entries",flush=True)


if __name__=="__main__":asyncio.run(main())
