"""Attribution for fno-entry-t2 (NOT the frozen decision): the same arms on the same sessions with the 15%
drawdown halt removed (FNO_MAX_DRAWDOWN_PCT = 1.0), every other rule as live, so the halt cliff cannot pass for a
rule's effect (lesson of Oct 8). Run from python-engine/ after the study was scored:

    python ../docs/research/fno/2026-10-24-entry-arms/halt_attribution.py

Writes halt_attribution.json next to this file.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3] / "python-engine"))

from config import settings  # noqa: E402
from fno_policy_replay import run_replay  # noqa: E402

WINDOWS = {"development": ("2026-09-10", "2026-10-09"), "untouched": ("2026-10-12", "2026-10-23")}
ARMS = {"BASELINE": "CURRENT", "FNO_SIG_CONTINUATION": "FNO_SIG_CONTINUATION", "FNO_SIG_OR_45": "FNO_SIG_OR_45",
        "FNO_SIG_OR_20": "FNO_SIG_OR_20", "FNO_SIG_CONFIRM_1": "FNO_SIG_CONFIRM_1"}


def main() -> None:
    settings.FNO_MAX_DRAWDOWN_PCT = 1.0
    out = {"note": "attribution only: the drawdown halt removed; not the pre-registered decision", "results": {}}
    for window, (start, end) in WINDOWS.items():
        for arm, policy in ARMS.items():
            summary = run_replay(HERE / "_local", start=start, end=end, policy=policy)["summary"]
            out["results"].setdefault(window, {})[arm] = summary
            print(window, arm, json.dumps({k: summary.get(k) for k in (
                "closed", "net_pnl", "net_excluding_best_winner", "max_drawdown", "win_rate_pct")}), flush=True)
    (HERE / "halt_attribution.json").write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
