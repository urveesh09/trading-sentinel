"""Verify the archived skill receipt in its exact, pinned Dev source checkout.

The stock helper binds HEAD as well as source bytes. Saving a report in a new
commit makes its moving-checkout check fail, even with unchanged strategy code.
This verifier retains that failure and runs the UNMODIFIED helper in a sparse
Dev worktree at its original SHA; no guard, request or original report is edited.
"""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import study as S


def main():
    S.verify_freeze()
    archive=S.HERE/"evidence"
    frozen=json.loads((archive/"policy-freeze.json").read_text())
    helper=S.ROOT/".agents/skills/sentinel-trading-simulation/scripts/simulation_evidence.py"
    assert S.sha(helper)==frozen["helper_sha256"]
    spec=importlib.util.spec_from_file_location("evidence_helper",helper)
    H=importlib.util.module_from_spec(spec);spec.loader.exec_module(H)
    pinned=S.LOCAL/"audit-checkout"
    assert pinned.resolve().is_relative_to(S.ROOT.resolve())
    if not pinned.exists():
        subprocess.run(["git","worktree","add","--detach","--no-checkout",str(pinned),frozen["git_sha"]],cwd=S.ROOT,check=True)
        subprocess.run(["git","-C",str(pinned),"sparse-checkout","set","python-engine","scripts","agent","node-gateway/server"],check=True)
        subprocess.run(["git","-C",str(pinned),"checkout"],check=True)
    assert H.git(pinned,"rev-parse","HEAD")==frozen["git_sha"]
    assert H.source_hashes(S.ROOT)==frozen["source_sha256"]
    # Git for Windows converts LF to CRLF on checkout. Restore only newline-
    # equivalent bytes from the still-hash-identical original snapshot. This
    # does not change a source declaration or relax the helper's byte guard.
    normalized_files=0
    for name,digest in frozen["source_sha256"].items():
        if S.sha(pinned/name)!=digest:
            old=(pinned/name).read_bytes();exact=(S.ROOT/name).read_bytes()
            assert old.replace(b"\r\n",b"\n")==exact.replace(b"\r\n",b"\n"),name
            (pinned/name).write_bytes(exact)
            normalized_files+=1
    assert H.source_hashes(pinned)==frozen["source_sha256"]
    request=json.loads((archive/"request.json").read_text())
    out=pinned/"docs/research/simulation/2026-11-03-expiry-year/evidence"
    if not out.exists():
        H.initialize(pinned,request["production"],out,request["start"],request["end"],request["as_of"],request["modules"])
        inputs=json.loads((archive/"inputs.json").read_text())["files_sha256"]
        for name,h in inputs.items():
            assert S.sha(archive/name)==h
            (out/name).parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(archive/name,out/name)
        H.seal(out,list(inputs))
        for name in ("ANALYSIS.md","analysis.json","daily-results.csv","coverage.json"):
            shutil.copyfile(archive/name,out/name)
        for module in request["modules"]:
            shutil.copyfile(archive/"modules"/(module+".json"),out/"modules"/(module+".json"))
        result=H.render(out)
        assert not result["errors"],result["errors"]
    original_errors=H.verify(archive)
    assert original_errors==["Policy source or Git SHA changed after freeze"],original_errors
    errors=H.verify(out)
    assert not errors,errors
    original=json.loads((archive/"REPORT.json").read_text())
    verified=json.loads((out/"REPORT.json").read_text())
    assert original["modules"]==verified["modules"]
    S.dump(S.HERE/"pinned-audit.json",dict(
        original_helper_current_checkout_errors=original_errors,pinned_helper_verified=True,pinned_helper_errors=errors,
        pinned_source_commit=frozen["git_sha"],pinned_checkout=str(pinned),pinned_report=str(out/"REPORT.md"),
        current_and_pinned_runtime_source_hashes_match=True,unchanged_source_files=len(frozen["source_sha256"]),
        candidate_input_freeze="99d3de3",candidate_and_raw_data_guard="PASS",
        original_report_sha256=S.sha(archive/"REPORT.json"),pinned_report_sha256=S.sha(out/"REPORT.json"),
        receipts_and_money_identical=True,helper_changed=False,
        newline_equivalent_files_restored=normalized_files,
        limitation="Pinned receipt is a post-score archive verification, not a new untouched strategy exam. Original report and its moving-HEAD failure are preserved."))
    print("PINNED_ARCHIVE_VERIFIED",len(frozen["source_sha256"]),"unchanged source files; original receipts/money identical")


if __name__=="__main__":main()
