"""Final fixed-SHA consistency packet, not retrospective preregistration."""
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "python-engine").is_dir())
LOCAL = HERE / "_local"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(expected):
    helper = Path("C:/Users/Urveesh/.codex/skills/sentinel-trading-simulation/scripts/simulation_evidence.py")
    spec = importlib.util.spec_from_file_location("e01_evidence", helper)
    H = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(H)
    assert H.git(ROOT, "rev-parse", "HEAD") == expected
    freeze = read(HERE / "freeze-round1-v2.json")
    for name, value in freeze["sources"].items():
        assert digest(LOCAL / "frozen-source" / name) == value, name
    for name, value in freeze["inputs"].items():
        assert digest(ROOT / name) == value, name
    assert read(HERE / "native-parity-final.json")["passed"]
    assert read(HERE / "audit-results.json")["passed"]
    out = LOCAL / "evidence-report-final"
    modules = {f"expiry_{arm}_{index.lower()}": (arm, index)
               for arm in ("v3", "e01") for index in ("NIFTY", "SENSEX")}
    H.initialize(ROOT, ROOT.parent / "Production_Trading-sentinel", out,
                 "2026-10-06", "2026-10-29", "2026-11-02", list(modules))

    def copy(source, target):
        target = out / target
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)

    tracked = H.git(ROOT, "ls-files", HERE.relative_to(ROOT).as_posix()).splitlines()
    for name in tracked:
        copy(ROOT / name, Path("study") / Path(name).relative_to(HERE))
    copy(HERE / "configuration.json", "configuration.json")
    copy(ROOT / "docs/EXPIRY_RESEARCH_E01.md", "ANALYSIS.md")
    for name in freeze["inputs"]:
        copy(ROOT / name, Path("original-inputs") / name)
    for name in freeze["sources"]:
        copy(LOCAL / "frozen-source" / name, Path("original-source") / name)
    for path in (LOCAL / "evals").glob("*.json"):
        copy(path, Path("private-evals") / path.name)
    for name in ("final-focused-tests.log", "final-native-parity.log", "command-round1.json",
                 "command-round1.log", "final-binding-tests.log"):
        path = LOCAL / name
        if path.exists():
            copy(path, Path("private-commands") / name)
    verification = dict(passed=True, original_source="cbbdebb", integrated_source=expected,
                        source_files=len(freeze["sources"]), input_files=len(freeze["inputs"]),
                        full_hash_tree_verified=True, post_run_packaging=True, not_preregistration=True)
    (out / "input-verification.json").write_text(json.dumps(verification, indent=2) + "\n", encoding="utf-8")
    sealed = H.seal(out, [p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()
                         and p.name not in ("request.json", "policy-freeze.json")
                         and "modules" not in p.relative_to(out).parts])
    for module, (arm, underlying) in modules.items():
        policy = "BASE" if arm == "v3" else "NATIVE_E01_FINAL"
        plays = ("A", "B", "C") if arm == "v3" else ("A", "B", "CE01")
        cases = [read(p) for p in sorted((LOCAL / "evals").glob(f"*-{underlying}-{policy}-ordinary.json"))]
        assert len(cases) == 4
        daily = {}
        for case in cases:
            positions = [p for p in case["positions"] if p["play"] in plays]
            assert all(p["status"] != "OPEN" for p in positions)
            net = round(sum(p["net_pnl"] + (p["assumed_pnl"] or 0) for p in positions), 2)
            daily[case["day"]] = (net, len(positions))
        total = round(sum(v[0] for v in daily.values()), 2)
        row = read(out / "modules" / f"{module}.json")
        row.update(status="PARTIAL", coverage="PARTIAL", fidelity="QUOTE_LIFECYCLE", population="SHADOW",
                   reason="Bounded native quote replay on four archived index sessions; gaps, auction fills and assumed settlement retained.",
                   inputs=list(sealed), artifacts=["ANALYSIS.md", "study/VERIFICATION.md", "study/results-round1.json",
                     "study/control-parity.json", "study/native-parity-final.json", "study/audit-results.json", "input-verification.json"],
                   metrics=dict(closed_trades=sum(v[1] for v in daily.values()), signals=None,
                                filled_fee_pnl=0.0, assumed_pnl=total, modeled_net=total, unresolved=0),
                   assumptions=["Independent Rs2500 per-play/day paper experiments, not a shared finite broker account.",
                     "E01 substitutes CE01 for C; C and CE01 are never added as one strategy's profit.",
                     "All reported money is simulated; broker-filled P&L is zero. Separate native paper-fill/settlement components are in ANALYSIS and raw receipts.",
                     "Closed-trade count is position legs; a two-leg strangle is not two independent strategy observations.",
                     "Original pre-score research freeze cbbdebb is distinct from final integrated source and this post-run packet."],
                   limitations=["All eight sessions already seen; no pristine holdout or reliable profitability estimate.",
                     "October6 index/future clock reconstructed from recorded observed values; one option depth level only.",
                     "Recorded gaps retained; auction execution unverified and sampled-index settlement assumed.",
                     "Current instrument catalogue reconstructed only within archived eligible sessions; full dated master not available.",
                     "No broker orders, new data acquisition, Production edit/restart/deployment or N11 change."])
        row["daily_results"] = []
        current = date(2026, 10, 6)
        while current <= date(2026, 10, 29):
            day = current.isoformat()
            value = daily.get(day)
            row["daily_results"].append(dict(date=day, status="PARTIAL" if value is not None else "UNAVAILABLE",
                reason="Archived eligible expiry, bounded quote replay; all money modeled." if value is not None
                       else "No archived eligible index session in this scope; not a guessed holiday or zero return.",
                metrics=dict(closed_trades=value[1] if value is not None else None,
                             filled_fee_pnl=0.0 if value is not None else None,
                             assumed_pnl=value[0] if value is not None else None,
                             modeled_net=value[0] if value is not None else None)))
            current += timedelta(days=1)
        (out / "modules" / f"{module}.json").write_text(json.dumps(row, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    report = H.render(out)
    errors = H.verify(out)
    proof = dict(validation=report["validation"], verification_errors=errors, git_sha=expected,
                 post_run_packaging=True, not_preregistration=True, whole_system_profit_available=False,
                 modules=len(modules), sealed_files=len(sealed))
    (out / "VERIFIED.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    assert report["validation"] == "EVIDENCE_CHECKS_PASSED" and not errors, errors
    print(json.dumps(proof), flush=True)


if __name__ == "__main__":
    main(sys.argv[1])
