"""
[PENNY-ISOLATION 2026-06-21] Architectural rule: penny modules MUST NOT
import from Nifty-side modules. Enforced by walking the AST of every
penny_*.py file under python-engine/.

Forbidden imports (from spec §3.3):
- engine, regime, risk_engine, portfolio
- evaluate_signal, evaluate_momentum_signal
- any other module that imports these transitively

Allowed imports: kite_client, models (base only), config, position_tracker
(read-only extension), performance (read-only extension), analytics
(extended correlator), pydantic, stdlib, structlog, pandas, numpy,
aiosqlite, apscheduler.
"""
import ast
import os
import glob

FORBIDDEN_MODULES = {
    "engine",
    "regime",
    "risk_engine",
    "portfolio",
    "evaluate_signal",
    "evaluate_momentum_signal",
}


def _collect_penny_modules():
    py_engine_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pattern = os.path.join(py_engine_dir, "penny_*.py")
    return sorted(glob.glob(pattern))


def test_penny_modules_exist_or_skip():
    """If no penny_*.py exists yet (early in the plan), skip."""
    files = _collect_penny_modules()
    if not files:
        import pytest
        pytest.skip("no penny_*.py files yet (expected pre-Task 3)")


def test_no_forbidden_imports_in_penny_modules():
    """AST walk: every import / import-from in every penny_*.py must not
    touch any forbidden module name."""
    files = _collect_penny_modules()
    assert files, "no penny_*.py files to check"
    violations = []
    for path in files:
        with open(path) as f:
            tree = ast.parse(f.read(), filename=path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if top in FORBIDDEN_MODULES:
                        violations.append(f"{path}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module is None:
                    continue  # relative import 'from . import x' is fine
                top = node.module.split(".")[0]
                if top in FORBIDDEN_MODULES:
                    violations.append(f"{path}: from {node.module} import ...")
    assert not violations, (
        "penny modules must not import Nifty-side modules. Violations:\n"
        + "\n".join(violations)
    )
