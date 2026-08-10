"""
[FNO-ISOLATION 2026-07-10] Architectural firewall for the F&O subsystem
(spec §5). Mirrors tests/test_penny_isolation.py: one subsystem's bug
must not cascade into another. F&O has real money (eventually) and a
fresh codebase; it gets the same firewall from day one.

Rules enforced by AST walk:
  1. No fno_* module (or options_math) imports penny_*, engine,
     risk_engine, portfolio, evaluate_signal, or evaluate_momentum_signal.
     A read-only import of regime.py IS permitted (spec §5).
  2. options_math is pure: stdlib-only imports (spec §6.3).
  3. fno_risk does not import options_math -- max_loss must stay
     model-free (spec §4).
"""
import ast
import glob
import os

FORBIDDEN_MODULES = {
    "engine",
    "risk_engine",
    "portfolio",
    "evaluate_signal",
    "evaluate_momentum_signal",
}

PY_ENGINE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _collect_fno_modules():
    files = sorted(glob.glob(os.path.join(PY_ENGINE_DIR, "fno_*.py")))
    om = os.path.join(PY_ENGINE_DIR, "options_math.py")
    if os.path.exists(om):
        files.append(om)
    return files


def _imports_of(path):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=path)
    tops = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            tops.extend(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            tops.append(node.module.split(".")[0])
    return tops


def test_fno_modules_exist():
    assert _collect_fno_modules(), "no fno_*.py files found"


def test_no_forbidden_imports_in_fno_modules():
    violations = []
    for path in _collect_fno_modules():
        for top in _imports_of(path):
            if top in FORBIDDEN_MODULES or top.startswith("penny_"):
                violations.append(f"{path}: imports {top}")
    assert not violations, (
        "fno modules must not import Nifty-side or penny modules. "
        "Violations:\n" + "\n".join(violations)
    )


def test_options_math_is_pure_stdlib():
    """Spec §6.3: pure, dependency-free. math + typing + __future__ only."""
    path = os.path.join(PY_ENGINE_DIR, "options_math.py")
    allowed = {"math", "typing", "__future__"}
    bad = [t for t in _imports_of(path) if t not in allowed]
    assert not bad, f"options_math must be stdlib-pure, found imports: {bad}"


def test_fno_risk_does_not_import_options_math():
    """Spec §4: max_loss is model-free; its module never touches pricing."""
    path = os.path.join(PY_ENGINE_DIR, "fno_risk.py")
    assert "options_math" not in _imports_of(path), (
        "fno_risk must not import options_math -- max_loss stays pure"
    )


def test_no_nifty_module_imports_fno():
    """Reverse direction: the pre-existing Nifty core must not grow an
    fno import (main.py wires via its own wrappers, which is allowed --
    main is the composition root, not a strategy module)."""
    core = ["engine.py", "risk_engine.py", "portfolio.py", "regime.py"]
    violations = []
    for name in core:
        path = os.path.join(PY_ENGINE_DIR, name)
        if not os.path.exists(path):
            continue
        for top in _imports_of(path):
            if top.startswith("fno_") or top == "options_math":
                violations.append(f"{name}: imports {top}")
    assert not violations, "\n".join(violations)
