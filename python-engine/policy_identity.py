"""[WORKFLOW-A4 2026-09-20] Policy identity fingerprint helper.

Exposes the policy + economic-model fingerprint computation as a
public helper so callers (full-policy replay, downstream
verification routes, qualification re-validation) can:

  1. Recompute the identity from the same source modules the
     `policy_manifest` in `partner_qualification` uses.
  2. Reject a stored identity when a material fill/exit/fee-model
     change has invalidated it.
  3. Separate the policy identity from data identity so a new bar
     capture timestamp does NOT create a new strategy.

Pure of I/O: takes the module source bytes / config dict and
returns the fingerprint. The caller reads the modules from disk
and the config from `settings.model_dump()`.

Design choices:

  * **Pure**: no DB, no clock, no I/O. The caller supplies the
    module source bytes (via ``read_bytes()``) and the config dict.
  * **Stable**: the SHA-256 input is a canonical JSON encoding
    with sorted keys; deterministic across processes and
    platforms.
  * **Bounded**: only the modules listed in
    ``_POLICY_IDENTITY_MODULES`` participate. Adding a module is a
    contract change; removing one is also a contract change.
  * **Two fingerprints**: ``policy_fingerprint`` binds the source
    modules only; ``economic_model_fingerprint`` binds the source
    modules + the config dict so a fee-model change invalidates
    stored identities.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


# [WORKFLOW-A4 2026-09-20] Modules that participate in the policy
# identity. Mirrors the ``source_names`` tuple in
# ``partner_qualification.policy_manifest``. A change to any of
# these source files invalidates old identities.
_POLICY_IDENTITY_MODULES = (
    # Original signal / advisory core.
    "fno_engine_mom.py", "partner_manual_advisory.py", "fno_chain.py",
    "fno_instruments.py", "options_math.py", "partner_qualification.py",
    "partner_thesis.py", "partner_decision_clock.py",
    # Chronological execution + replay (A4: previously omitted).
    "intraday_spread_chronological.py",
    "intraday_spread_replay.py",
    "intraday_spread_holdout.py",
    "intraday_spread_research.py",
    "intraday_spread_research_verify.py",
    # Exit / cost / quality (A4: previously omitted).
    "momentum_exits.py",
    "fno_costs.py",
    "exit_quality.py",
    "cost_audit.py",
    # Full-policy replay (A4: previously omitted).
    "partner_full_policy_replay.py",
)


def _canonical_sha256(payload: Any) -> str:
    """SHA-256 hex digest over ``json.dumps(sort_keys=True)``."""
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def module_sha256s(root: Path) -> dict[str, str]:
    """Compute per-module SHA-256 fingerprints under ``root``.

    Skips a module silently when the file is absent so a partial
    deployment (e.g. a future removal of a deprecated module)
    does not crash the helper. The caller decides whether a
    missing module is acceptable.
    """
    out: dict[str, str] = {}
    for name in _POLICY_IDENTITY_MODULES:
        path = root / name
        if not path.is_file():
            continue
        out[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def policy_fingerprint(root: Path) -> str:
    """Return the policy identity fingerprint.

    Binds only the source modules listed in
    ``_POLICY_IDENTITY_MODULES``. A change to any module produces
    a different fingerprint, so the audit's "each material
    fill/exit/fee-model change invalidates old evidence"
    requirement is enforced.

    Modules that are absent on disk are simply omitted from the
    fingerprint input, so a partial deployment does not crash the
    helper. Callers that need to REJECT on missing modules must
    compute the expected set themselves and compare.
    """
    shas = module_sha256s(root)
    return _canonical_sha256({
        "format": "partner_policy_identity_v1",
        "modules": shas,
    })


def economic_model_fingerprint(
    root: Path,
    config: Mapping[str, Any],
) -> str:
    """Return the economic-model identity fingerprint.

    Binds the policy modules + the config dict. A change to
    either produces a different fingerprint, so the audit's
    "fee-model change invalidates old evidence" requirement is
    enforced.
    """
    shas = module_sha256s(root)
    return _canonical_sha256({
        "format": "partner_economic_model_identity_v1",
        "modules": shas,
        "config": dict(config),
    })


__all__ = [
    "economic_model_fingerprint",
    "module_sha256s",
    "policy_fingerprint",
]
