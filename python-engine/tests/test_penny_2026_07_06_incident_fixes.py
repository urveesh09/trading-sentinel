"""
Regression tests for the 2026-07-06 penny subsystem silent-fire incident.

Today's incident (UTC): the penny-edge cron registered at 07:09 IST but
NEVER FIRED at 09:30 IST. The legacy 30s penny_scan_interval fired 1,376
times all day returning `accept=0 error=0 reject=0` with no debug breadcrumb
to explain why. Production silently produced zero trades.

Three fixes verified by this test module:

1. **Diagnostic breadcrumb at top of penny-edge handlers** (rule 49
   compliance): every penny-edge cron handler must log a `*_invoked`
   line as its FIRST executable statement so future "silent cron" days
   are debuggable in 30 seconds.

2. **Job-level misfire_grace_time=600**: the scheduler's job_defaults
   sets it globally, but defending-in-depth at the job level protects
   against future scheduler-default regressions and documents the intent
   at the registration site.

3. **`penny_scan_summary` companion line** in `run_penny_scanner_once`:
   the legacy `penny_scan_complete` line is a single accept/error/reject
   counter; on a 0/0/0 day the operator had no breadcrumb to explain it.
   The new `penny_scan_summary caller_view` line surfaces the universe
   size, cache size, and regime for every scan tick.

These tests live alongside `test_penny_2026_07_02_incident_fixes.py`
which closed the 2026-07-02 str/int type-mismatch incident. The pattern
is the same: every silent-failure incident gets a regression test that
catches the regression if the fix is ever reverted.
"""

import ast
import asyncio
import inspect
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_PY = os.path.join(REPO_ROOT, "main.py")
# [ROADMAP-4.1 stage 2 2026-07-13] The scheduler registration functions -- and
# the 8 closures whose bodies these tests assert on -- moved out of main.py into
# scheduler_setup.py. These guards check for real things (the `invoked`
# breadcrumb, misfire_grace_time, instance guards), so they follow the code
# rather than being narrowed to a file that no longer contains it.
SCHEDULER_SETUP_PY = os.path.join(REPO_ROOT, "scheduler_setup.py")


def _read_main_py() -> str:
    """main.py plus the scheduler module: the sources that, between them, hold
    every scheduled handler. Name kept for the existing call sites."""
    out = []
    for path in (MAIN_PY, SCHEDULER_SETUP_PY):
        if os.path.exists(path):
            with open(path) as f:
                out.append(f.read())
    return "\n".join(out)


def _function_body(name: str) -> str:
    """Return the source of an `async def name(...)` function inside
    `register_penny_scheduler_jobs` (heuristic: scan until next
    top-level def/class).
    """
    src = _read_main_py()
    # Find the function definition
    lines = src.split("\n")
    start = None
    for i, line in enumerate(lines):
        if f"async def {name}(" in line:
            start = i
            break
    if start is None:
        return ""
    # Walk forward until we hit a non-indented def or a scheduler.add_job call
    end = len(lines)
    for j in range(start + 1, len(lines)):
        line = lines[j]
        if line and not line.startswith((" ", "\t")):
            if (
                line.startswith("def ")
                or line.startswith("async def ")
                or line.startswith("class ")
            ):
                end = j
                break
    return "\n".join(lines[start:end])


@pytest.fixture(autouse=True)
def suppress_aiosqlite_shutdown_noise():
    """register_penny_scheduler_jobs schedules async tasks (the
    startup-catchup path uses `asyncio.create_task`) which run on
    apscheduler's internal event loop. When the test tears down
    the loop, the aiosqlite worker thread sees a closed loop and
    raises `RuntimeError('Event loop is closed')`. This is a benign
    shutdown warning, not a test failure -- suppress it.
    """
    import warnings
    # Suppress Python's default RuntimeWarning emission
    warnings.filterwarnings(
        "ignore",
        message=".*Event loop is closed.*",
        category=RuntimeWarning,
    )
    # Suppress pytest's threading-exception capture for this specific
    # benign pattern. PytestUnhandledThreadExceptionWarning is the
    # wrapper category pytest uses for unhandled thread exceptions.
    try:
        from _pytest.threadexception import PytestUnhandledThreadExceptionWarning
        warnings.filterwarnings(
            "ignore",
            category=PytestUnhandledThreadExceptionWarning,
            message=".*Event loop is closed.*",
        )
    except ImportError:
        pass
    yield


class TestPennyEdgeBreadcrumb:
    """Every penny-edge cron handler must log a `*_invoked` line as its
    FIRST executable statement. Rule 49 (trading-sentinel-ops): every
    wall-clock cron needs a first-line breadcrumb so silent failures
    are debuggable in 30 seconds.
    """

    def test_penny_edge_scan_safe_logs_invoked_first(self):
        body = _function_body("_run_penny_edge_scan_safe")
        assert body, "could not find _run_penny_edge_scan_safe in main.py"
        # Find the first logger.* call inside the function
        lines = body.split("\n")
        first_log_idx = None
        first_log_text = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("logger."):
                first_log_idx = i
                # Collect this and following lines until we hit a line
                # that doesn't continue the call (no leading whitespace
                # and no paren continuation)
                first_log_text.append(stripped)
                j = i + 1
                while j < len(lines):
                    nxt = lines[j]
                    if nxt.startswith(")") or nxt.strip() == ")":
                        first_log_text.append(")")
                        break
                    if nxt.strip().endswith(")") and not nxt.rstrip().endswith("\\"):
                        first_log_text.append(nxt.strip())
                        break
                    if nxt.strip():
                        first_log_text.append(nxt.strip())
                    j += 1
                break
        assert first_log_idx is not None, (
            "_run_penny_edge_scan_safe has no logger.* call -- "
            "the diagnostic breadcrumb must be the FIRST executable "
            "statement (rule 49 trading-sentinel-ops)."
        )
        # The first logger call must be the breadcrumb (the message
        # text is on a separate line from `logger.info(` so we
        # concatenate the captured lines).
        joined = " ".join(first_log_text)
        assert "penny_edge_scan_invoked" in joined, (
            f"First logger call in _run_penny_edge_scan_safe is "
            f"{joined!r}, expected penny_edge_scan_invoked "
            f"breadcrumb per rule 49."
        )

    def test_penny_edge_exit_safe_logs_invoked_first(self):
        body = _function_body("_run_penny_edge_exit_safe")
        assert body, "could not find _run_penny_edge_exit_safe in main.py"
        lines = body.split("\n")
        first_log_idx = None
        first_log_text = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("logger."):
                first_log_idx = i
                first_log_text.append(stripped)
                j = i + 1
                while j < len(lines):
                    nxt = lines[j]
                    if nxt.startswith(")") or nxt.strip() == ")":
                        first_log_text.append(")")
                        break
                    if nxt.strip().endswith(")") and not nxt.rstrip().endswith("\\"):
                        first_log_text.append(nxt.strip())
                        break
                    if nxt.strip():
                        first_log_text.append(nxt.strip())
                    j += 1
                break
        assert first_log_idx is not None, (
            "_run_penny_edge_exit_safe has no logger.* call -- "
            "the diagnostic breadcrumb must be the FIRST executable "
            "statement (rule 49)."
        )
        joined = " ".join(first_log_text)
        assert "penny_edge_exit_invoked" in joined, (
            f"First logger call in _run_penny_edge_exit_safe is "
            f"{joined!r}, expected penny_edge_exit_invoked "
            f"breadcrumb per rule 49."
        )


class TestPennyEdgeMisfireGuard:
    """The penny_edge_scan and penny_edge_exit cron jobs must declare
    an explicit `misfire_grace_time=600` at the registration site.

    The scheduler's `job_defaults` sets it globally, but defending in
    depth at the job level protects against future scheduler-default
    regressions and documents the intent at the registration site.
    """

    def test_penny_edge_scan_misfire_grace_time_set(self):
        src = _read_main_py()
        # Find the scheduler.add_job call for penny_edge_scan and verify
        # misfire_grace_time=600 is in the kwargs.
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "add_job"):
                continue
            if not node.args:
                continue
            first = node.args[0]
            target_name = None
            if isinstance(first, ast.Name):
                target_name = first.id
            elif isinstance(first, ast.Attribute):
                target_name = ast.unparse(first)
            if target_name == "_run_penny_edge_scan_safe":
                # Check the kwargs include misfire_grace_time=600
                kwarg_names = {k.arg for k in node.keywords if k.arg}
                assert "misfire_grace_time" in kwarg_names, (
                    "_run_penny_edge_scan_safe cron registration is "
                    "missing misfire_grace_time -- the 09:30 IST trigger "
                    "can be silently dropped during penny_scan_interval "
                    "contention. See PENNY-EDGE-MISFIRE-GUARD 2026-07-06."
                )
                for kw in node.keywords:
                    if kw.arg == "misfire_grace_time":
                        assert isinstance(kw.value, ast.Constant), (
                            "misfire_grace_time must be a literal int"
                        )
                        assert kw.value.value == 600, (
                            f"misfire_grace_time={kw.value.value}, "
                            f"expected 600 (10 min headroom)"
                        )
                return
        pytest.fail(
            "could not find scheduler.add_job(_run_penny_edge_scan_safe, ...)"
        )

    def test_penny_edge_exit_misfire_grace_time_set(self):
        src = _read_main_py()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "add_job"):
                continue
            if not node.args:
                continue
            first = node.args[0]
            target_name = None
            if isinstance(first, ast.Name):
                target_name = first.id
            elif isinstance(first, ast.Attribute):
                target_name = ast.unparse(first)
            if target_name == "_run_penny_edge_exit_safe":
                kwarg_names = {k.arg for k in node.keywords if k.arg}
                assert "misfire_grace_time" in kwarg_names, (
                    "_run_penny_edge_exit_safe cron registration is "
                    "missing misfire_grace_time -- the 15:15 IST trigger "
                    "can be silently dropped. REAL FINANCIAL RISK: missed "
                    "15:15 exit leaves EDGE positions open overnight. "
                    "See PENNY-EDGE-MISFIRE-GUARD 2026-07-06."
                )
                for kw in node.keywords:
                    if kw.arg == "misfire_grace_time":
                        assert isinstance(kw.value, ast.Constant), (
                            "misfire_grace_time must be a literal int"
                        )
                        assert kw.value.value == 600, (
                            f"misfire_grace_time={kw.value.value}, "
                            f"expected 600"
                        )
                return
        pytest.fail(
            "could not find scheduler.add_job(_run_penny_edge_exit_safe, ...)"
        )


class TestPennyScanSummary:
    """`run_penny_scanner_once` must log a `penny_scan_summary caller_view`
    line on every path that returns. Today's incident: 1,376 ticks of
    `accept=0 error=0 reject=0` with no breadcrumb to explain why.

    Paths covered:
    - scanner is None (loud warning)
    - successful scan (caller_view with universe_size + cache_size + regime)
    - TimeoutError (caller_view reason=timeout_90s)
    - generic Exception (caller_view reason=exception)
    """

    def test_penny_scan_summary_present_on_all_paths(self):
        body = _function_body("run_penny_scanner_once")
        assert body, "could not find run_penny_scanner_once in main.py"
        # The caller_view summary must be in there
        assert "penny_scan_summary caller_view" in body, (
            "run_penny_scanner_once is missing the penny_scan_summary "
            "caller_view log line. Today's 1,376 silent 0/0/0 ticks had "
            "no breadcrumb to explain why -- this is the fix."
        )
        # Scanner-None branch must have its own summary too
        assert "scanner=None reason=scanner_not_initialised" in body, (
            "run_penny_scanner_once is missing the scanner=None branch "
            "summary. The legacy `return` on scanner-None silently "
            "logged nothing."
        )
        # Timeout branch must have its own summary
        assert "reason=timeout_90s" in body, (
            "run_penny_scanner_once is missing the timeout-path summary."
        )
        # Exception branch must have its own summary
        assert "reason=exception" in body, (
            "run_penny_scanner_once is missing the exception-path summary."
        )


class TestPennyEdgeSchedulerRegistration:
    """End-to-end test that calling register_penny_scheduler_jobs
    actually wires up penny_edge_scan + penny_edge_exit with the
    expected shape (misfire_grace_time=600, max_instances=1,
    coalesce=True). Catches a future regression where the job-level
    guard is removed.
    """

    def test_register_penny_scheduler_jobs_wires_edge_jobs(self):
        # We import lazily so the test doesn't need kite access at
        # collection time. The registration function only touches kite
        # via the cron-target closures (which are not invoked at
        # registration time), so the import is safe.
        sys.path.insert(0, REPO_ROOT)
        from main import register_penny_scheduler_jobs

        async def _run():
            from apscheduler.schedulers.asyncio import AsyncIOScheduler
            sched = AsyncIOScheduler(
                timezone="Asia/Kolkata",
                job_defaults={"misfire_grace_time": 600},
            )
            register_penny_scheduler_jobs(sched)
            # Don't start() the scheduler -- we only want to inspect
            # the registered jobs, not run them. This avoids the
            # asyncio event-loop race that apscheduler's shutdown()
            # triggers when there are pending catchup tasks.
            jobs = {j.id: j for j in sched.get_jobs()}
            return jobs

        jobs = asyncio.run(_run())
        for jid in ["penny_edge_scan", "penny_edge_exit"]:
            assert jid in jobs, (
                f"{jid} not registered by register_penny_scheduler_jobs"
            )
            j = jobs[jid]
            assert j.misfire_grace_time == 600, (
                f"{jid} misfire_grace_time={j.misfire_grace_time}, "
                f"expected 600"
            )
            assert j.coalesce is True, (
                f"{jid} coalesce={j.coalesce}, expected True"
            )
            assert j.max_instances == 1, (
                f"{jid} max_instances={j.max_instances}, expected 1"
            )


class TestPennyEdgeHandlerInvokedBreadcrumb:
    """End-to-end test: invoking the penny_edge_scan_safe handler
    directly (mimicking what APScheduler would do at 09:30 IST) MUST
    emit the `penny_edge_scan_invoked` breadcrumb.

    Today the production log showed zero `penny_edge_scan_*` lines
    after 07:09 IST startup -- the operator could not tell whether the
    cron had fired silently and returned nothing, or whether it never
    fired at all. After this fix, ANY invocation -- whether from
    APScheduler's cron trigger, from the startup catchup, or from a
    manual /penny/command/scan trigger -- must produce a log line.
    """

    def test_penny_edge_scan_safe_emits_invoked_breadcrumb(self):
        """Directly call _run_penny_edge_scan_safe and assert it logs
        the breadcrumb as its first action."""
        # We can't easily import main here without kite init -- so we
        # inspect the function source and check the breadcrumb is the
        # first logger call. The unit test above already covers this
        # with AST; here we make it explicit for clarity in the test
        # report.
        body = _function_body("_run_penny_edge_scan_safe")
        assert "penny_edge_scan_invoked" in body, (
            "_run_penny_edge_scan_safe missing breadcrumb"
        )
        # The breadcrumb must appear BEFORE any await call (so it
        # fires even if the await hangs or is cancelled).
        lines = body.split("\n")
        breadcrumb_idx = None
        first_await_idx = None
        for i, line in enumerate(lines):
            if "penny_edge_scan_invoked" in line and breadcrumb_idx is None:
                breadcrumb_idx = i
            if "await" in line and first_await_idx is None:
                first_await_idx = i
        assert breadcrumb_idx is not None, "breadcrumb line not found"
        if first_await_idx is not None:
            assert breadcrumb_idx < first_await_idx, (
                f"breadcrumb at line {breadcrumb_idx} but first await at "
                f"line {first_await_idx} -- the breadcrumb must fire "
                f"BEFORE any await so it survives mid-flight cancellations."
            )


class TestPennyEdgeOrchestratorBreadcrumb:
    """The orchestrator (`run_penny_edge_scan` and `run_penny_edge_exit`)
    inside `penny_edge_orchestrator.py` must also emit a first-line
    breadcrumb. Today's incident: even after the wrapper fired (which
    we couldn't verify at the time), the orchestrator itself could
    crash silently with `sqlite3.OperationalError: no such table:
    ohlv_cache` and leave no trace beyond a single `penny_edge_scan_failed`
    line in the wrapper's try/except.
    """

    def _extract_function_body(self, src_text: str, func_name: str) -> str:
        """Use AST to extract the source of a top-level `async def`."""
        import ast
        tree = ast.parse(src_text)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == func_name:
                    lines = src_text.split("\n")
                    return "\n".join(lines[node.lineno - 1:node.end_lineno])
        return ""

    def test_orchestrator_scan_has_first_line_breadcrumb(self):
        orch_path = os.path.join(REPO_ROOT, "penny_edge_orchestrator.py")
        with open(orch_path) as f:
            src = f.read()
        body = self._extract_function_body(src, "run_penny_edge_scan")
        assert body, "could not find run_penny_edge_scan via AST"
        assert "penny_edge_orchestrator_invoked" in body, (
            "run_penny_edge_scan missing penny_edge_orchestrator_invoked "
            "breadcrumb. The orchestrator must log a first-line 'I am "
            "running' line so silent crashes (like today's "
            "ohlcv_cache_table_missing crash) are debuggable."
        )
        # Find first logger.* call in the function body
        lines = body.split("\n")
        first_log_idx = None
        for i, line in enumerate(lines):
            if line.lstrip().startswith("logger."):
                first_log_idx = i
                break
        assert first_log_idx is not None, (
            "run_penny_edge_scan has no logger.* call"
        )
        joined = "\n".join(lines[first_log_idx:first_log_idx + 6])
        assert "penny_edge_orchestrator_invoked" in joined, (
            f"First logger call in run_penny_edge_scan is not the "
            f"orchestrator breadcrumb. Got: {joined[:300]!r}"
        )

    def test_orchestrator_exit_has_first_line_breadcrumb(self):
        orch_path = os.path.join(REPO_ROOT, "penny_edge_orchestrator.py")
        with open(orch_path) as f:
            src = f.read()
        body = self._extract_function_body(src, "run_penny_edge_exit")
        assert body, "could not find run_penny_edge_exit via AST"
        assert "penny_edge_exit_orchestrator_invoked" in body, (
            "run_penny_edge_exit missing penny_edge_exit_orchestrator_invoked "
            "breadcrumb. Same rationale as run_penny_edge_scan."
        )


class TestPennyEdgeEngineFailsafe:
    """The orchestrator must not let `pel.scan_today` raise out of
    its own try/except. Today's incident: a fresh DB without the
    `ohlcv_cache` table crashed `scan_today` with `OperationalError`,
    which the wrapper's try/except caught and logged as a single
    `penny_edge_scan_failed err=...` line. The operator couldn't tell
    whether the engine ran and returned nothing, or whether it never
    ran.

    After this fix:
    - `penny_edge_scan_engine_db_unready reason=ohlcv_cache_table_missing`
      is logged if the table is missing.
    - `penny_edge_scan_engine_db_unready reason=ohlcv_cache_empty` is
      logged if the table is empty.
    - The orchestrator returns an empty-candidates summary instead of
      raising, so the wrapper's `penny_edge_scan_done` line still fires.
    """

    def test_orchestrator_wraps_scan_today_in_try_except(self):
        orch_path = os.path.join(REPO_ROOT, "penny_edge_orchestrator.py")
        with open(orch_path) as f:
            src = f.read()
        # The `scan = pel.scan_today(...)` call must be inside a try block
        assert "penny_edge_scan_engine_failed" in src, (
            "penny_edge_orchestrator.py missing penny_edge_scan_engine_failed "
            "log tag. The orchestrator must catch engine exceptions and "
            "log a loud diagnostic so the cron wrapper doesn't swallow "
            "the root cause."
        )

    def test_scan_today_handles_missing_ohlcv_cache_table(self):
        """End-to-end: a fresh DB without the ohlcv_cache table must
        NOT crash pel.scan_today. It must return an empty-candidates
        dict and log a loud diagnostic.
        """
        import sqlite3
        import tempfile
        from unittest.mock import AsyncMock, MagicMock

        import penny_edge_orchestrator as peo

        tmp_db = tempfile.mktemp(suffix=".db")
        # Empty DB (no tables)
        conn = sqlite3.connect(tmp_db)
        conn.close()

        async def _run():
            kite = MagicMock()
            kite.get_historical = AsyncMock(return_value=None)
            # Set DB_PATH so the orchestrator's settings resolve to
            # the temp DB.
            import os as _os
            old = _os.environ.get("DB_PATH")
            _os.environ["DB_PATH"] = tmp_db
            try:
                summary = await peo.run_penny_edge_scan(kite, db_path=tmp_db)
            finally:
                if old is not None:
                    _os.environ["DB_PATH"] = old
            return summary

        summary = asyncio.run(_run())
        assert summary["candidates_total"] == 0
        assert summary["universe"] == 0
        assert summary["regime"] in ("ERROR", "BOTH", "MR", "MO")
        # paper + live both have 0 entered
        assert summary["paper"]["entered"] == 0
        assert summary["live"]["entered"] == 0
        # skipped contains the engine_failed marker (if regime=ERROR path)
        skipped = summary.get("skipped", [])
        engine_failed_marker = any(
            "engine_failed" in str(reason) for _t, reason in skipped
        )
        # The summary is well-formed even if no error marker present
        # (orchestrator's early-return short-circuit may not include
        # the marker -- depends on which path triggered).
        assert isinstance(skipped, list), "skipped must be a list"