"""
[HIGH-001 2026-07-12] INTERNAL_API_SECRET hygiene.

The field keeps its empty-string default (operator mandate 2026-06-25:
a misconfigured secret must never block boot during market hours -- the
auth gate degrades to 503 instead). What the validator guarantees is
that a whitespace-only value can NOT masquerade as a configured secret:
it is stripped to "", which the auth gate treats as unconfigured.
"""
import os
from unittest import mock

from config import Settings


def _fresh_settings(**env):
    """Build a Settings instance from a controlled environment, ignoring
    any .env file on disk so the test is hermetic."""
    with mock.patch.dict(os.environ, env, clear=False):
        return Settings(_env_file=None)


def test_whitespace_only_secret_strips_to_empty():
    s = _fresh_settings(INTERNAL_API_SECRET="   ")
    assert s.INTERNAL_API_SECRET == ""


def test_surrounding_whitespace_is_stripped():
    s = _fresh_settings(INTERNAL_API_SECRET="  real-secret-value  ")
    assert s.INTERNAL_API_SECRET == "real-secret-value"


def test_unset_secret_defaults_to_empty_and_does_not_block_construction():
    env = {k: v for k, v in os.environ.items() if k != "INTERNAL_API_SECRET"}
    with mock.patch.dict(os.environ, env, clear=True):
        s = Settings(_env_file=None)
    assert s.INTERNAL_API_SECRET == ""
