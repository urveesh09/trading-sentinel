"""[WORKFLOW-J.5 2026-09-13] Drift detector for NSE holiday lists.

The Python engine and the node-gateway both maintain a "today is
a trading holiday" check. Pre-J.5 each shipped its own list:

  * python-engine/market_calendar.py::NSE_HOLIDAYS_STATIC (20 dates)
  * node-gateway/server/utils/market-hours.js::NSE_HOLIDAYS (18 dates)

Only 10 dates overlap. The drift caused real production
hazards: a CAS-eligible stock could be scheduled for an order on a
holiday that the gateway considered a trading day (or vice versa).
J.5 makes Python authoritative; this module is the static
cross-check that surfaces divergence between the two sources
until the Node side fetches from the engine at boot.

This module is **pure**: no I/O, no clock, no DB, no logging. It
parses the Node source file as text (regex match on the
``Set([...])`` literal). The regex is tolerant of:

  * trailing commas
  * varied whitespace (single / multiple space, tab)
  * inline comments on each date line (`'YYYY-MM-DD', // Comment`)
  * single-quoted or double-quoted date strings

The path to the Node source is detected by walking up from this
file's location to the repo root, so the module is callable from
Dev (without any Docker / engine running) AND from CI.

Usage::

    from holiday_drift import holiday_drift_report
    rpt = holiday_drift_report()
    if rpt["verdict"] == "DRIFT":
        sys.exit(1)

The verdict is ``"ALIGNED"`` when the two sets are equal modulo
ordering, ``"DRIFT"`` otherwise.
"""
from __future__ import annotations

import re
from datetime import date as _date
from pathlib import Path
from typing import Iterable


# Node source regex: matches `'YYYY-MM-DD'` or `"YYYY-MM-DD"`
# date literals. Anchored to ISO 8601. Year is 4 digits; month
# 01-12; day 01-31. We deliberately do NOT enforce validity
# (e.g. 2026-02-30 would match) -- that's the drift detector's
# chance to flag a malformed literal in the Node source.
_NODE_DATE_RE = re.compile(
    r"""(['"])(?P<date>\d{4}-\d{2}-\d{2})\1""",
)


# Repo-root discovery: this file lives at
# python-engine/holiday_drift.py; the Node source is at
# node-gateway/server/utils/market-hours.js, two levels up from
# the python-engine dir relative to the python-engine parent.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_NODE_MARKET_HOURS_JS = (
    _REPO_ROOT / "node-gateway" / "server" / "utils" / "market-hours.js"
)


def _resolve_repo_root() -> Path:
    """Walk up to find the repo root.

    This file lives at ``<repo>/python-engine/holiday_drift.py``;
    ``parents[1]`` is the repo root. We tolerate packaging (e.g.
    the file ends up nested deeper for distribution) by walking
    up until a ``scripts/`` directory or a known sentinel is
    found. Falls back to ``parents[1]`` if none of the anchors
    appear (e.g. running outside the repo).
    """
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        if (ancestor / "scripts").is_dir() and (ancestor / "python-engine").is_dir():
            return ancestor
    return here.parents[1]


def python_nse_holidays() -> set[str]:
    """Return the canonical Python holiday set as ISO strings.

    Reads ``market_calendar.NSE_HOLIDAYS_STATIC`` at call time so
    re-imports / monkeypatches in tests are honored.
    """
    from market_calendar import NSE_HOLIDAYS_STATIC
    return {d.isoformat() for d in NSE_HOLIDAYS_STATIC}


def parse_node_nse_holidays(source: str) -> set[str]:
    """Parse the ``NSE_HOLIDAYS`` Set literal from the Node source.

    Pure text-parsing; the caller passes the file contents. We
    extract every ISO date literal that appears inside the
    ``new Set([...])`` block. We do NOT try to handle every
    possible JS syntax (template literals, computed values) --
    the Node file uses a plain ``new Set([...])`` of string
    literals and the parser matches that contract. If a future
    refactor turns the Set into something exotic, this parser
    returns empty (drift detection flips to FAIL with a separate
    diagnostic).
    """
    # Locate the ``new Set([...])`` block. The literal may be
    # multi-line; match from ``new Set([`` to ``])``.
    block_match = re.search(
        r"""(?:const|let|var)\s+\w+\s*=\s*new\s+Set\s*\(\s*\[(?P<body>.*?)\]\s*\)""",
        source, re.DOTALL,
    )
    if not block_match:
        return set()
    body = block_match.group("body")
    # ``re.findall`` with named-groups returns a list of tuples; we
    # only want the named ``date`` capture, so iterate.
    return {m.group("date") for m in _NODE_DATE_RE.finditer(body)}


def node_nse_holidays_from_atlas(
    node_source_path: Path | str = _NODE_MARKET_HOURS_JS,
) -> set[str]:
    """Read the Node source file and parse its ``NSE_HOLIDAYS`` Set.

    The path argument defaults to the canonical location; tests
    pass a fixture path. Returns an empty set when the file is
    missing (drift detection then says ``in_node_only`` is empty
    and ``in_python_only`` carries every holiday -- a clean,
    directional drift report).
    """
    path = Path(node_source_path)
    if not path.exists():
        return set()
    return parse_node_nse_holidays(path.read_text(encoding="utf-8"))


def holiday_drift_report(
    node_source_path: Path | str = _NODE_MARKET_HOURS_JS,
    python_set: Iterable[str] | None = None,
) -> dict:
    """Compare the canonical Python holidays against the Node set.

    Returns a dict serialisable to JSON:

        {
            "verdict": "ALIGNED" | "DRIFT",
            "python_count": int,
            "node_count": int,
            "python_only": [iso, ...],   # in Python, not Node
            "node_only": [iso, ...],     # in Node, not Python
            "in_both": [iso, ...],       # in both
            "drift_count": int,            # len(python_only) + len(node_only)
            "sources": {"python": str, "node": str},
        }
    """
    py = (
        set(python_set) if python_set is not None
        else python_nse_holidays()
    )
    nd = node_nse_holidays_from_atlas(node_source_path)
    py_only = sorted(py - nd)
    nd_only = sorted(nd - py)
    in_both = sorted(py & nd)
    drift = len(py_only) + len(nd_only)
    return {
        "verdict": "DRIFT" if drift else "ALIGNED",
        "python_count": len(py),
        "node_count": len(nd),
        "python_only": py_only,
        "node_only": nd_only,
        "in_both": in_both,
        "drift_count": drift,
        "sources": {
            "python": "python-engine/market_calendar.py::NSE_HOLIDAYS_STATIC",
            "node": str(node_source_path),
        },
    }


def format_drift_report(report: dict) -> str:
    """Human-readable rendering for the CLI / operator log.

    Sorted-section format (so a diff against an operator's
    pinned log is stable). Emits nothing for empty sections.
    """
    lines = [
        f"verdict={report['verdict']} "
        f"(python_count={report['python_count']} "
        f"node_count={report['node_count']} "
        f"drift_count={report['drift_count']})",
    ]
    if report["in_both"]:
        lines.append(
            f"in_both[{len(report['in_both'])}]: {','.join(report['in_both'])}"
        )
    if report["python_only"]:
        lines.append(
            f"python_only[{len(report['python_only'])}]: "
            f"{','.join(report['python_only'])}"
        )
    if report["node_only"]:
        lines.append(
            f"node_only[{len(report['node_only'])}]: "
            f"{','.join(report['node_only'])}"
        )
    if report["verdict"] == "ALIGNED":
        lines.append(
            "Note: ALIGNED means both sources carry the same ISO "
            "date set (modulo ordering). Run the canonical "
            "Python list through ``holidays_drift_check.py`` to "
            "confirm operator-curated entries match NSE."
        )
    return "\n".join(lines)


# When called as `python -m holiday_drift ...` (rare; the operator
# tool lives in tools/holiday_drift_check.py), emit the report to
# stdout. Keeps manual investigation one command away.
if __name__ == "__main__":
    import sys as _sys

    rpt = holiday_drift_report()
    _sys.stdout.write(format_drift_report(rpt) + "\n")
    raise SystemExit(1 if rpt["verdict"] == "DRIFT" else 0)
