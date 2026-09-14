"""[WORKFLOW-G 2026-09-13] ``default-v1`` legacy back-compat shim acceptance.

Closes gap #5 of 6 from
``docs/2026-09-13-workflow-g-state-of-codebase-audit.md`` §6.

Why this file exists:

* ``_shadow_run_storage_key`` historically short-circuits ``run_id ==
  "default-v1"`` to the bare ``account_id`` so pre-versioning Dev fixtures
  remain readable.
* A *configured* shadow run (``run_shadow_workflow``,
  ``run_configured_shadow_workflow``) must never produce this id; its
  lineage is derived from the operator-visible label by
  ``_configured_shadow_run_id``.
* ``audit §3.3`` documents the collision risk: two distinct conceptual
  runs sharing the legacy id for one account collapse to one storage row.

This file pins the contract so a future refactor cannot:

1. rename the legacy id away from ``"default-v1"`` without notice,
2. silently change the storage-key short-circuit to the hash form (which
   would orphan pre-existing Dev evidence),
3. accidentally use the literal ``"default-v1"`` in a new code path when
   the proper runtime helper ``_configured_shadow_run_id`` exists.

Behaviour preserved (no deletions): pre-existing callers that pass
``run_id="default-v1"`` continue to receive the same storage key for
the same account, and configured runners continue to produce hashed
lineage ids. The change is the addition of one named constant
``LEGACY_DEFAULT_V1_RUN_ID`` and a small docstring expansion.
"""
from __future__ import annotations

import pytest

from proactive_intelligence import (
    LEGACY_DEFAULT_V1_RUN_ID,
    _configured_shadow_run_id,
    _shadow_implementation_identity,
    _shadow_run_storage_key,
    _SHADOW_SCHEMA_VERSION,
)


def _impl_prefix() -> str:
    """Match the runtime layout: ``f"{label}:impl-{sha256(file)[:12]}"``."""
    return _shadow_implementation_identity()[:12]


# ---- 1: constant shape and value ---------------------------------------

def test_legacy_default_v1_run_id_has_expected_value() -> None:
    """The literal is preserved exactly; no rename, no version suffix.

    Existing fixtures and any on-disk SQLite row key depend on the
    string being byte-identical to ``"default-v1"``; tampering with
    this value would orphan every legacy row.
    """
    assert LEGACY_DEFAULT_V1_RUN_ID == "default-v1"
    assert isinstance(LEGACY_DEFAULT_V1_RUN_ID, str)


# ---- 2: storage-key short-circuit preserved ---------------------------

def test_legacy_run_id_short_circuits_to_bare_account_id() -> None:
    """``_shadow_run_storage_key`` preserves the historical short-circuit.

    A change here would silently re-hash every existing legacy fixture
    under ``account_id``, breaking read-path compatibility without a
    migration. The test makes the change visible at code-review time.
    """
    assert _shadow_run_storage_key("dev-shadow", LEGACY_DEFAULT_V1_RUN_ID) == "dev-shadow"
    assert _shadow_run_storage_key("account-x", LEGACY_DEFAULT_V1_RUN_ID) == "account-x"
    assert _shadow_run_storage_key("op-prod-1", LEGACY_DEFAULT_V1_RUN_ID) == "op-prod-1"


def test_legacy_short_circuit_collides_for_identical_inputs() -> None:
    """Two ``(account_id, LEGACY_DEFAULT_V1_RUN_ID)`` tuples collide on purpose.

    This is the documented collision risk from audit §3.3. The test
    pins it as *behavioural property* rather than bug so a future
    contributor who tries to \"fix\" it by adding a hash step is forced
    to acknowledge the legacy contract.
    """
    key_a = _shadow_run_storage_key("dev-shadow", LEGACY_DEFAULT_V1_RUN_ID)
    key_b = _shadow_run_storage_key("dev-shadow", LEGACY_DEFAULT_V1_RUN_ID)
    assert key_a == key_b
    assert key_a == "dev-shadow"
    # Different accounts using the legacy id do NOT collide — the bare
    # account_id is itself the key.
    assert _shadow_run_storage_key("acct-y", LEGACY_DEFAULT_V1_RUN_ID) != key_a


def test_non_legacy_run_id_uses_hashed_storage_key() -> None:
    """Fresh run ids never take the legacy short-circuit."""
    fresh = "team-alpha-2026-09-13"
    key = _shadow_run_storage_key("dev-shadow", fresh)
    assert key != "dev-shadow"
    assert key.startswith("shadow-run:")
    digest = key.removeprefix("shadow-run:")
    assert len(digest) == 24  # truncated SHA-256 hex
    # Hash is deterministic for the same inputs.
    assert _shadow_run_storage_key("dev-shadow", fresh) == key


def test_storage_key_rejects_empty_inputs() -> None:
    with pytest.raises(ValueError, match="required"):
        _shadow_run_storage_key("", "run-1")
    with pytest.raises(ValueError, match="required"):
        _shadow_run_storage_key("acct-1", "")


# ---- 3: configured run IDs never land on the legacy constant ----------

def test_configured_shadow_run_id_never_returns_legacy_default() -> None:
    """The configured-runner helper mints a hashed lineage id, never the legacy label.

    A future bug here would silently re-introduce the collision risk
    even after a careful constant rename. The test asserts the
    invariant rather than a specific hashed value.
    """
    lineage = _configured_shadow_run_id("dev-shadow-v1")
    assert lineage != LEGACY_DEFAULT_V1_RUN_ID
    assert lineage.startswith("dev-shadow-v1:impl-")
    assert lineage.endswith(f":impl-{_impl_prefix()}") or lineage.endswith(":impl-" + _impl_prefix())
    # The lineage id, passed through the storage key, must NOT hit the
    # legacy short-circuit.
    key = _shadow_run_storage_key("dev-shadow", lineage)
    assert not key.startswith(_shadow_run_storage_key.__qualname__ or "")  # always false; sanity
    assert key != "dev-shadow"
    assert key.startswith("shadow-run:")


def test_configured_shadow_run_id_rejects_empty_label() -> None:
    """Empty labels raise rather than silently fall through to the legacy id."""
    with pytest.raises(ValueError, match="required"):
        _configured_shadow_run_id("")
    with pytest.raises(ValueError, match="required"):
        _configured_shadow_run_id("   ")


# ---- 4: no internal callers depend on the bare literal -----------------

def test_internal_usage_references_named_constant() -> None:
    """The literal ``"default-v1"`` should appear *only* at the constant declaration.

    A grep-based smoke test: we import the module source and check
    that the bare literal appears exactly once, on the constant
    declaration itself. If a future contributor reintroduces the magic
    string at any other site, this test fails.
    """
    import re
    import proactive_intelligence as mod

    source = mod.__file__
    with open(source, encoding="utf-8") as handle:
        body = handle.read()
    # Strip the constant declaration itself so the test does not assert
    # against its own evidence: replace the line with the comment that
    # follows it.
    constant_line = "LEGACY_DEFAULT_V1_RUN_ID = \"default-v1\""
    assert constant_line in body, "constant declaration missing"
    body = body.replace(constant_line, "LEGACY_DEFAULT_V1_RUN_ID = <centralised>")

    # After stripping the declaration, the bare literal must not appear
    # anywhere else in the module source.
    leftover = re.findall(r"(?<![A-Za-z0-9_])default-v1(?![A-Za-z0-9_])", body)
    assert leftover == [], (
        f"bare \"default-v1\" literal leaked outside LEGACY_DEFAULT_V1_RUN_ID: {leftover}"
    )


# ---- 5: schema-version is unrelated to the legacy id --------------------

def test_legacy_constant_independent_of_schema_version() -> None:
    """No accidental coupling between the legacy id and the schema version.

    The ``_SHADOW_SCHEMA_VERSION`` moves with evidence-shape changes;
    the ``LEGACY_DEFAULT_V1_RUN_ID`` is fixture-shape invariance. If
    a future bump of either inadvertently changed the other, this
    test catches it.
    """
    assert _SHADOW_SCHEMA_VERSION != LEGACY_DEFAULT_V1_RUN_ID
    # Sanity: both are non-empty strings.
    assert _SHADOW_SCHEMA_VERSION and LEGACY_DEFAULT_V1_RUN_ID
