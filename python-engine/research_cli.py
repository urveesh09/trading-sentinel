"""Operator commands for immutable research preservation (no broker actions)."""
from __future__ import annotations

import argparse
import json
import sys

from config import settings
from research_archive import export_operational_fno_evidence


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sentinel read-only research evidence tools")
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export-fno", help="read-only export of operational NIFTY/SENSEX OI snapshots")
    export.add_argument("--source-db", default=settings.DB_PATH)
    export.add_argument("--archive-root", default=settings.RESEARCH_ARCHIVE_PATH)
    export.add_argument("--underlyings", default=settings.RESEARCH_ARCHIVE_UNDERLYINGS,
                        help="comma-separated underlying names; default NIFTY,SENSEX")
    args = parser.parse_args(argv)
    if args.command == "export-fno":
        try:
            result = export_operational_fno_evidence(
                args.source_db, args.archive_root,
                [name.strip() for name in args.underlyings.split(",") if name.strip()],
            )
        except Exception as exc:
            print(json.dumps({"exported": False, "error": str(exc)}), file=sys.stderr)
            return 1
        print(json.dumps({"exported": True, "path": result["path"], "coverage": result["coverage"]}, sort_keys=True))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
