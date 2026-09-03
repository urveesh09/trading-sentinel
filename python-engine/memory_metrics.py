"""Small, dependency-free process-memory probes for the engine.

``resource.getrusage(...).ru_maxrss`` is a high-water mark on Linux.  It is
useful for capacity planning, but must never be presented as the process's
current RSS: it does not fall after a temporary allocation is released.
"""
from __future__ import annotations

import os
import sys


def current_rss_kb() -> int:
    """Return the process's current resident set in KiB, or ``-1`` if unknown.

    Linux containers expose the authoritative current value as ``VmRSS`` in
    procfs.  ``statm`` is retained as a small fallback for stripped proc
    status files.  Both paths are deliberately dependency-free so this probe
    remains available in the production slim image.
    """
    try:
        with open("/proc/self/status", encoding="utf-8") as status:
            for line in status:
                if line.startswith("VmRSS:"):
                    fields = line.split()
                    return int(fields[1])
    except (OSError, ValueError, IndexError):
        pass

    try:
        with open("/proc/self/statm", encoding="utf-8") as statm:
            resident_pages = int(statm.read().split()[1])
        return resident_pages * os.sysconf("SC_PAGE_SIZE") // 1024
    except (OSError, ValueError, IndexError, AttributeError):
        return -1


def peak_rss_kb() -> int:
    """Return the process high-water RSS in KiB, or ``-1`` if unavailable."""
    try:
        import resource

        peak = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
        # Linux reports KiB while macOS reports bytes.  The engine production
        # image is Linux, but normalise here so local diagnostics remain true.
        if sys.platform == "darwin":
            peak //= 1024
        return peak
    except (ImportError, OSError, AttributeError, ValueError):
        return -1
