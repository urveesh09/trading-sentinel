"""Consistent snapshot: source SQLite URI is read-only; all outputs must be in Dev."""
import argparse
import json
import sqlite3
from pathlib import Path


def main():
    cli=argparse.ArgumentParser();cli.add_argument("--source",required=True);cli.add_argument("--out",required=True)
    args=cli.parse_args();out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    target=out/"expiry.sqlite"
    assert not target.exists(),"preserve prior snapshots"
    with sqlite3.connect(Path(args.source).as_uri()+"?mode=ro",uri=True,timeout=5) as src:
        with sqlite3.connect(target) as dst:
            src.backup(dst,pages=128)
    with sqlite3.connect(target.as_uri()+"?mode=ro",uri=True) as c:
        assert c.execute("pragma quick_check").fetchone()[0]=="ok"
        rows=c.execute("select day,underlying,count(*),min(ts),max(ts) from expiry_paper_ticks group by day,underlying order by day").fetchall()
        states=[]
        for day,u,state in c.execute("select day,underlying,state from expiry_paper_days order by day"):
            s=json.loads(state)
            states.append({"day":day,"underlying":u,"keys":list(s),"rules":s.get("rules"),"versions":{k:v for k,v in s.items() if 'version' in k}})
        payload={"sessions":rows,"states":states,"tables":c.execute("select name from sqlite_master where type='table'").fetchall()}
        (out/"inventory.json").write_text(json.dumps(payload,indent=2)+"\n",encoding="utf-8")
        print(json.dumps({"snapshot":str(target),"sessions":rows}))


if __name__=="__main__":
    main()
