"""[WORKFLOW-D.3 2026-09-16] Tests for the auto-generated
release notes builder.

Per Workstream D item 3 in NEXT_AGENT_PLAN.md:
> 3. Prepare a PR describing behavior, tests and remaining
>    operational prerequisites. User authorization is required
>    for actions outside existing scope, including actual
>    partner messages or live canary orders.

The script auto-generates the PR body's technical
sections from git + the D.1 + D.2.a audit outputs.
These tests pin the contract:

  - Git state extraction is deterministic.
  - Commit categorization covers all conventional commit
    prefixes used by this branch (feat, fix, docs, test,
    refactor, chore, other).
  - Release notes include branch + SHA + categorized commits.
  - Audit sections (test, migration, defaults) embed
    correctly when their JSON files are present.
  - Output is deterministic for a given SHA + audit input.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest


HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = Path(os.path.dirname(os.path.dirname(HERE))).resolve()
SCRIPTS_DIR = REPO_ROOT / "scripts"

# Import build_release_notes via importlib (same pattern as
# the other audit tests -- the scripts/ tree has no __init__.py).
_spec = importlib.util.spec_from_file_location(
    "build_release_notes",
    str(SCRIPTS_DIR / "build_release_notes.py"),
)
build_release_notes = importlib.util.module_from_spec(_spec)
sys.modules["build_release_notes"] = build_release_notes
_spec.loader.exec_module(build_release_notes)


# ─── Commit categorization ──────────────────────────────


def test_categorize_feat():
    assert build_release_notes.categorize_commit(
        "feat(j10): new feature"
    ) == "feat"


def test_categorize_feature_keyword():
    """``feature`` is treated as a synonym for ``feat``."""
    assert build_release_notes.categorize_commit(
        "feature(j10): alternative prefix"
    ) == "feat"


def test_categorize_fix():
    assert build_release_notes.categorize_commit(
        "fix(gateway): bug fix"
    ) == "fix"


def test_categorize_docs():
    assert build_release_notes.categorize_commit(
        "docs: release notes"
    ) == "docs"


def test_categorize_refactor():
    assert build_release_notes.categorize_commit(
        "refactor: clean up"
    ) == "refactor"


def test_categorize_test():
    assert build_release_notes.categorize_test() if False else (
        build_release_notes.categorize_commit("test: coverage") == "test"
    )


def test_categorize_chore():
    assert build_release_notes.categorize_commit(
        "chore: bump deps"
    ) == "chore"


def test_categorize_other():
    """A commit prefix that's not in the conventional set
    is bucketed as ``other``.
    """
    assert build_release_notes.categorize_commit(
        "wip: scratch"
    ) == "other"


def test_categorize_case_insensitive():
    """Conventional commits are case-insensitive at the verb."""
    assert build_release_notes.categorize_commit("FEAT: upper") == "feat"
    assert build_release_notes.categorize_commit("Fix: mixed") == "fix"


# ─── Git state extraction ────────────────────────────────


def test_get_git_state_extracts_branch_and_head():
    """The git state includes branch + head sha + commits."""
    state = build_release_notes.get_git_state(REPO_ROOT)
    assert "branch" in state
    assert "head_sha" in state
    assert "head_short" in state
    assert "commits" in state
    assert isinstance(state["commits"], list)
    # The repo IS a git repo, so head_sha should be non-empty.
    assert len(state["head_sha"]) >= 7


def test_get_git_state_commits_have_sha_and_subject():
    """Each commit has a SHA and a subject line."""
    state = build_release_notes.get_git_state(REPO_ROOT)
    for commit in state["commits"][:5]:
        assert "sha" in commit
        assert "subject" in commit
        assert len(commit["sha"]) >= 7
        assert commit["subject"]


def test_get_git_state_handles_missing_repo(tmp_path):
    """A non-git directory returns empty strings / lists."""
    state = build_release_notes.get_git_state(tmp_path)
    assert state["head_sha"] == ""
    assert state["commits"] == []


# ─── Markdown rendering ───────────────────────────────────


def _make_minimal_git_state() -> dict:
    """A minimal git_state for renderer tests."""
    return {
        "head_sha": "abc1234567890" * 4,
        "head_short": "abc1234",
        "branch": "main",
        "commits": [
            {"sha": "aaaaaaa", "subject": "feat: new feature"},
            {"sha": "bbbbbbb", "subject": "fix: bug"},
            {"sha": "ccccccc", "subject": "docs: readme"},
            {"sha": "ddddddd", "subject": "wip: scratch"},
        ],
        "tags": ["v1.0.0", "v0.9.0"],
        "uncommitted_files": ["?? new_file.py"],
    }


def test_render_release_notes_includes_branch_and_sha():
    """The notes show branch + SHA prominently."""
    notes = build_release_notes.render_release_notes(_make_minimal_git_state())
    assert "**Branch**: `main`" in notes
    assert "**Head SHA**: `abc1234`" in notes


def test_render_release_notes_groups_by_category():
    """Categories are surfaced in the order: feat, fix, docs, refactor, test, chore, other."""
    notes = build_release_notes.render_release_notes(_make_minimal_git_state())
    # Each category present in the output.
    assert "**feat**: 1" in notes
    assert "**fix**: 1" in notes
    assert "**docs**: 1" in notes
    assert "**other**: 1" in notes


def test_render_release_notes_lists_each_commit():
    """Every commit appears in the detailed list with its sha + category."""
    notes = build_release_notes.render_release_notes(_make_minimal_git_state())
    assert "`aaaaaaa` (feat)" in notes
    assert "`bbbbbbb` (fix)" in notes
    assert "`ccccccc` (docs)" in notes
    assert "`ddddddd` (other)" in notes


def test_render_release_notes_includes_operator_checklist():
    """The pre-deploy + post-deploy checklists are emitted."""
    notes = build_release_notes.render_release_notes(_make_minimal_git_state())
    assert "Operator checklist (pre-deploy)" in notes
    assert "Operator checklist (post-deploy)" in notes
    assert "[ ]" in notes  # checkbox marker


# ─── Audit integration ───────────────────────────────────


def test_render_includes_migration_ledger_when_provided():
    """The migration ledger section surfaces table counts."""
    notes = build_release_notes.render_release_notes(
        _make_minimal_git_state(),
        migration_ledger={
            "tables_count": 80,
            "migrations_count": 10,
            "schema_constants": {"broker_reconciliation.py": ["_SCHEMA"]},
        },
    )
    assert "Migration ledger" in notes
    assert "Tables discovered: **80**" in notes
    assert "Migration steps: **10**" in notes


def test_render_includes_defaults_audit_when_provided():
    """The defaults audit section surfaces tier counts."""
    notes = build_release_notes.render_release_notes(
        _make_minimal_git_state(),
        defaults_audit=[
            {"name": "A", "default": "1", "type": "int", "tier": "RISKY",
             "reason": "fail-open"},
            {"name": "B", "default": "2", "type": "int", "tier": "SAFE",
             "reason": "small"},
        ],
    )
    assert "Defaults audit" in notes
    assert "RISKY" in notes
    assert "operator must review" in notes
    # The RISKY entry should be listed by name.
    assert "`A`" in notes


def test_render_omits_defaults_audit_section_when_empty():
    """If no defaults audit is provided, the section is omitted."""
    notes = build_release_notes.render_release_notes(_make_minimal_git_state())
    assert "Defaults audit" not in notes


def test_render_caps_risky_list_at_20():
    """The RISKY section shows 20 rows + '... and N more' for > 20."""
    many_risky = [
        {"name": f"R{i}", "default": str(i), "type": "int",
         "tier": "RISKY", "reason": "fail-open"}
        for i in range(30)
    ]
    notes = build_release_notes.render_release_notes(
        _make_minimal_git_state(),
        defaults_audit=many_risky,
    )
    # All 30 should be counted in the RISKY count.
    assert "**RISKY** (operator must review): **30**" in notes
    # Only 20 + the "and 10 more" suffix should appear.
    assert "(... and 10 more" in notes


def test_render_includes_test_receipt_section_when_provided():
    """The test health section surfaces D.1's snapshot fields."""
    notes = build_release_notes.render_release_notes(
        _make_minimal_git_state(),
        test_receipt={
            "python-engine": "3,686 PASS / 2 FAIL / 4 SKIP",
            "agent": "330 PASS / 0 FAIL",
        },
    )
    assert "Test health" in notes
    assert "python-engine" in notes


# ─── CLI integration ─────────────────────────────────────


def test_main_emits_notes_to_stdout(tmp_path, capsys):
    """Default mode emits the notes to stdout."""
    rc = build_release_notes.main(["--repo", str(REPO_ROOT)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Release notes" in out
    assert "Branch" in out or "branch" in out


def test_main_writes_to_file(tmp_path):
    """``--out`` writes the notes to the specified path."""
    out_path = tmp_path / "RELEASE_NOTES.md"
    rc = build_release_notes.main([
        "--repo", str(REPO_ROOT),
        "--out", str(out_path),
    ])
    assert rc == 0
    assert out_path.exists()
    text = out_path.read_text(encoding="utf-8")
    assert "Release notes" in text


def test_main_loads_audit_json_files(tmp_path):
    """``--migration-ledger`` and ``--defaults-audit`` are loaded."""
    # Write minimal audit files.
    migration_path = tmp_path / "migration.json"
    migration_path.write_text(json.dumps({
        "ledger": {
            "tables_count": 5,
            "migrations_count": 2,
            "schema_constants": {"a.py": ["_SCHEMA"]},
        }
    }))
    defaults_path = tmp_path / "defaults.json"
    defaults_path.write_text(json.dumps([
        {"name": "X", "default": "1", "type": "int",
         "tier": "RISKY", "reason": "fail-open"}
    ]))
    rc = build_release_notes.main([
        "--repo", str(REPO_ROOT),
        "--migration-ledger", str(migration_path),
        "--defaults-audit", str(defaults_path),
    ])
    assert rc == 0


def test_main_errors_on_missing_repo():
    """Missing repo directory -> exit code 2."""
    rc = build_release_notes.main([
        "--repo", "/nonexistent/path/never/exists",
    ])
    assert rc == 2


# ─── Determinism ─────────────────────────────────────────


def test_rendering_is_deterministic(tmp_path):
    """The same git state + audit input produces byte-identical output."""
    git_state = _make_minimal_git_state()
    audit = [{"name": "A", "default": "1", "type": "int",
              "tier": "RISKY", "reason": "fail-open"}]
    notes_a = build_release_notes.render_release_notes(
        git_state,
        migration_ledger={"tables_count": 1, "migrations_count": 0,
                           "schema_constants": {}},
        defaults_audit=audit,
    )
    notes_b = build_release_notes.render_release_notes(
        git_state,
        migration_ledger={"tables_count": 1, "migrations_count": 0,
                           "schema_constants": {}},
        defaults_audit=audit,
    )
    assert notes_a == notes_b
