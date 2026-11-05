"""Replay the lead trend arm with the existing N11T doubled-stress control."""
import json
from pathlib import Path

import regular_annual as annual

HERE=Path(__file__).resolve().parent

def main():
    year=annual.f.YEAR
    control=annual.f.fpanel_books()["DOUBLE"]
    candidate=annual.books()["TREND"]
    candidate["label"]+="|DOUBLE"
    candidate["cost"]=control["cost"]
    annual.f.Z.N.run_books({"TREND_DOUBLE":candidate},1)
    saved=json.loads((annual.OLD/f"keys-fpanel-{year}.json").read_bytes())["DOUBLE"]
    assert annual.Y.task_key(control,"year",annual.f.B.C.WINDOW)==saved
    new=annual.Y.task_key(candidate,"year",annual.f.B.C.WINDOW)
    source={"N11T_DOUBLE":annual.OLD/"evals"/f"{saved}.json",
            "TREND_DOUBLE":annual.Y.EVALS/f"{new}.json"}
    result={name:annual.metrics(json.loads(path.read_bytes())) for name,path in source.items()}
    with (HERE/f"regular-stress-{year}.json").open("x",encoding="utf-8") as f:
        json.dump(result,f,indent=2,sort_keys=True)
        f.write("\n")
    print(year,*(x["net"] for x in result.values()),flush=True)

if __name__=="__main__":
    main()
