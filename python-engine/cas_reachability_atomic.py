"""[WORKFLOW-J.10.WRITE_ATOMIC 2026-09-14] Atomic-write helpers for the J.10 gate.

The J.10 gate's audit trail is the JSON report persisted via
``write_report``. Today the function uses ``Path.write_text``,
which is a non-atomic overwrite: a crash between truncate and
write leaves a partial / empty file, and a concurrent reader
sees a torn write.

The F5 ``reconciliation_cli._write_output_atomic`` (per
``docs/2026-09-13-fg-independent-correction-plan.md``) solves
this with a write-to-tempfile + ``os.link`` discipline:
  1. Write the encoded bytes to a sibling tempfile.
  2. ``fsync`` to flush to disk.
  3. ``os.link`` the tempfile to the target path -- this is
     atomic on POSIX and on Windows (NTFS) for files that do
     not yet exist. If the target already exists, the link
     fails with ``FileExistsError``; we compare bytes and
     refuse to overwrite a different-content file.
  4. Unlink the tempfile in ``finally``.

This module exposes ``write_report_atomic`` that mirrors the
F5 helper for the J.10 gate. The contract:
  - byte-identical retries produce identical files,
  - ``allow_nan=False`` prevents ``NaN``/``Infinity`` in JSON,
  - the target is NOT clobbered if a different-content file
    already exists at the path (defensive against the operator
    running two CLI invocations against different captures
    directories).
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_report_atomic(report: dict[str, Any], out_path: Path) -> None:
    """Persist ``report`` as JSON, atomically + byte-identically.

    Mirrors ``reconciliation_cli._write_output_atomic`` (F5
    discipline). Pure / total / never silently clobbers an
    existing different-content file.

    Args:
        report: The bounded gate report dict. Must be JSON-
            serialisable; ``allow_nan=False`` ensures the encoder
            refuses ``NaN`` / ``Infinity`` rather than emitting
            the JSON-spec-violating literals that some downstream
            consumers reject.
        out_path: Where to persist the report. The parent
            directory is created if missing. The target file is
            created via ``os.link`` from a sibling tempfile --
            atomic on POSIX and on Windows NTFS.

    Raises:
        ValueError: if a file already exists at ``out_path`` with
            different content. The gate's report is a stable
            shape -- two runs against the same captures
            directory must produce byte-identical output. A
            different-content pre-existing file means the
            operator has run the CLI against a DIFFERENT
            captures directory; we refuse to clobber rather
            than silently overwriting their audit trail.
        OSError: filesystem-level errors (no disk space,
            permission denied, etc.) propagate.
    """
    out_path = Path(out_path)
    encoded = json.dumps(
        report,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=".j10_report-", dir=out_path.parent
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, out_path)
        except FileExistsError:
            existing = out_path.read_bytes()
            if existing != encoded:
                raise ValueError(
                    f"output already exists with different content: "
                    f"{out_path}. Refusing to overwrite. The gate's "
                    f"report is a stable shape; a different-content "
                    f"pre-existing file means the operator is "
                    f"writing to the wrong path or has stale output "
                    f"from a different captures directory."
                ) from None
            # Same content -- ``os.link`` failed because the
            # target already exists. The existing file IS the
            # report; nothing to do.
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


__all__ = ["write_report_atomic"]
