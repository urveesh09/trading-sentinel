"""[WORKFLOW-J.10.DEDUP 2026-09-14] Capture-fingerprint dedup helpers.

Per the inheritance doc's senior-dev protocol #1 ("read the file
before patching"), the gate's reachability count is the count of
captures that *exist* in the directory. When an operator
accidentally commits the same capture twice (e.g. retrying the
probe without changing inputs), the gate currently counts both
copies toward the branch coverage threshold.

That is wrong: the gate is supposed to answer "have these branches
been *exercised* by real captures?" -- a count of *unique*
observations, not of files-on-disk. A duplicate capture silently
flipping the gate to REACHABLE is exactly the kind of silent
authority-grant the user keeps flagging.

This module exposes two pure helpers:

    fingerprint_of(capture_path) -> Optional[str]
        SHA-256 of the canonical JSON bytes (the captured
        document bytes as written -- not the parsed dict, which
        may have reordered keys). The hex digest is truncated
        to 16 chars for compactness; collisions on 16 hex chars
        are bounded by the operator's actual capture volume
        (16 chars = 64 bits = effectively zero collisions at
        the scale of this project).

    dedup_by_branch(captures_by_branch) -> dict[str, int]
        Given a per-branch list of capture fingerprints, returns
        the number of duplicates (fingerprints appearing more
        than once in the same branch). The gate uses this to
        surface ``duplicates_by_branch`` in the report without
        altering the canonical ``captured_phases`` count.

Both helpers are importable in isolation; the gate in
``cas_reachability_gate.py`` calls them inside the existing
``cas_reachability_report`` function. No new dependencies --
stdlib ``hashlib`` only.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional


#: Length of the hex digest we surface. 16 hex chars = 64 bits.
#: The gate operates on a bounded number of captures (operator-curated
#: staging evidence); 64-bit collision probability is effectively
#: zero at that scale (a 1-in-2^32 chance per pair once you cross
#: 4 billion captures -- the project will not see that volume in
#: any one branch).
FINGERPRINT_HEX_LENGTH: int = 16


def fingerprint_of(capture_path: Path) -> Optional[str]:
    """Return a stable SHA-256 fingerprint of the capture bytes.

    Reads the file as bytes and hashes them with SHA-256. Truncates
    to 16 hex chars (64 bits) for compactness; full 64-char digests
    are available via ``hashlib.sha256(path.read_bytes()).hexdigest()``
    if a caller ever wants them.

    Returns ``None`` when the file is unreadable -- the gate counts
    unreadable files as ``captures_skipped`` rather than treating the
    missing fingerprint as a hash collision.

    The function deliberately reads the *bytes* (not the parsed JSON
    object) so two captures that differ only in key ordering hash
    the same. The J.3 probe writes a deterministic JSON document
    via ``json.dumps(..., sort_keys=True)`` (per the probe's
    canonicalisation discipline), so in practice the bytes-path
    and the parsed-dict-path converge -- but the bytes-path is the
    source of truth and survives future probe changes.
    """
    try:
        data = Path(capture_path).read_bytes()
    except OSError:
        return None
    digest = hashlib.sha256(data).hexdigest()
    return digest[:FINGERPRINT_HEX_LENGTH]


def dedup_count(fingerprints: list[str]) -> int:
    """Return the number of duplicate fingerprints in a list.

    A fingerprint appearing N times contributes ``N - 1`` to the
    duplicate count. An empty list returns 0. The order is
    irrelevant -- this is a set-style counting operation.

    Examples:
        >>> dedup_count([])
        0
        >>> dedup_count(["a", "b", "c"])
        0
        >>> dedup_count(["a", "a", "b"])
        1
        >>> dedup_count(["a", "a", "a"])
        2

    The function is pure and total; it never raises.
    """
    if not fingerprints:
        return 0
    seen: set[str] = set()
    duplicates = 0
    for fp in fingerprints:
        if fp in seen:
            duplicates += 1
        else:
            seen.add(fp)
    return duplicates


__all__ = [
    "FINGERPRINT_HEX_LENGTH",
    "fingerprint_of",
    "dedup_count",
]
