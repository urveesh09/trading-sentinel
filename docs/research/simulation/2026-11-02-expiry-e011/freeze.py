"""Hash what the frozen run depends on. `freeze` writes once; `verify` is what score.py calls first."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys

import e011_lab as L
import sept as Z

TARGET = L.HERE / "freeze.json"
FILES = ["PLAN.md", "arms.py", "panel.py", "sept.py", "e011_lab.py", "seen_table.py", "test_e011.py", "spreads.json",
         "preflight-sept.json", "parity.py", "score.py"]


def sha(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current() -> dict:
    out = {name: sha(L.HERE / name) for name in FILES}
    out["python-engine/expiry_paper.py"] = sha(L.ROOT / "python-engine/expiry_paper.py")
    out["E01 archived sessions"] = sha(L.SOURCE)
    for day in Z.DAYS:
        name = f"NIFTY-{day}-ATM-CE-PE-10second.csv"
        out[name] = sha(Z.SNAPSHOT / name)
    return out


def freeze() -> None:
    assert not TARGET.exists(), "the freeze is written once"
    TARGET.write_text(json.dumps(current(), indent=1) + "\n")
    print("frozen", len(FILES))


def verify() -> dict:
    """The frozen hashes must match the working tree, and the freeze must already be committed."""
    frozen = json.loads(TARGET.read_text())
    raw = subprocess.check_output(["git", "show", f"HEAD:{TARGET.relative_to(L.ROOT).as_posix()}"], cwd=L.ROOT)
    assert json.loads(raw) == frozen, "the freeze must be committed before September is read"
    now = current()
    wrong = [k for k in frozen if frozen[k] != now.get(k)]
    assert not wrong, wrong
    return frozen


if __name__ == "__main__":
    freeze() if sys.argv[1:] == ["freeze"] else print(len(verify()), "hashes match")
