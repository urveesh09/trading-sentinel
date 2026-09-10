"""Non-secret identity baked into a deployable Sentinel release.

This deliberately reads only deployment environment variables.  Asking a
running container to inspect ``.git`` is unreliable (and often impossible in
a minimal production image), while accepting an unset value as a revision
would recreate the exact false-positive this module is intended to prevent.
"""
from __future__ import annotations

import os
import re
from typing import Final

_SHA: Final = re.compile(r"^[0-9a-f]{7,64}$")


def _value(name: str, default: str = "unknown") -> str:
    """Return a bounded, presentation-safe deployment value."""
    value = str(os.getenv(name, default)).strip()
    return value[:128] if value else default


def release_identity(service_name: str = "python-engine") -> dict[str, str | bool]:
    """Return metadata safe to expose on authenticated and health surfaces."""
    revision = _value("SENTINEL_RELEASE_SHA")
    return {
        "service": _value("SENTINEL_SERVICE_NAME", service_name),
        "revision": revision,
        "build_utc": _value("SENTINEL_BUILD_UTC"),
        # ``declared`` is intentionally separate from liveness.  An old or
        # unlabelled image can answer health checks perfectly well.
        "declared": bool(_SHA.fullmatch(revision)),
    }
