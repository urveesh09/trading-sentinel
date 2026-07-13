"""[ROADMAP-4.1 2026-07-13] Characterization harness for the main.py split.

main.py is the largest and least-tested file in the system (4,245 lines).
Splitting it is a *mechanical* refactor, but "mechanical" is exactly the
class of change that silently breaks a trading system: the FastAPI route
table and the APScheduler job list are both built by import-time side
effects (decorators / register_*_scheduler_jobs), so a function that
fails to get re-registered after a move disappears WITHOUT any import
error, any test failure, or any log line. It just never runs again.

That is not hypothetical here. The scheduler is how every scan fires; a
dropped `add_job` would look exactly like a healthy, silent engine --
the same failure signature as the 2026-07-13 outage.

So: pin the observable surface BEFORE the split, and require it to be
byte-identical after. This file is the contract.

Two snapshots:
  1. ROUTES     -- every (path, methods, response_model, endpoint name).
  2. JOBS       -- every scheduler job (id, trigger repr, callable name).

The golden values live in `main_surface_golden.json` next to this file.
Regenerate DELIBERATELY (never casually) with:

    TS_UPDATE_GOLDEN=1 pytest tests/test_main_surface_characterization.py

and justify every diff in the commit message. An unexplained diff in
this file's golden means a route or a scheduled job changed behaviour.
(An env var rather than a --flag: pytest only honours addoption() from
conftest.py, and this harness is deliberately self-contained so it can
be copied to any repo that needs to survive a big mechanical refactor.)
"""
import json
import os
import pathlib

import pytest

GOLDEN = pathlib.Path(__file__).parent / "main_surface_golden.json"


def _updating() -> bool:
    return os.environ.get("TS_UPDATE_GOLDEN") == "1"


def _route_surface(app) -> list[dict]:
    """Every HTTP route the app actually serves, in a stable order."""
    out = []
    for r in app.routes:
        path = getattr(r, "path", None)
        if path is None:
            continue
        methods = sorted(getattr(r, "methods", None) or [])
        # FastAPI mounts a few internal routes (openapi/docs/redoc); they
        # are framework-owned and not part of OUR surface.
        if path in ("/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"):
            continue
        rm = getattr(r, "response_model", None)
        out.append(
            {
                "path": path,
                "methods": methods,
                "endpoint": getattr(getattr(r, "endpoint", None), "__name__", None),
                "response_model": getattr(rm, "__name__", None) if rm else None,
            }
        )
    out.sort(key=lambda d: (d["path"], ",".join(d["methods"]), d["endpoint"] or ""))
    return out


def _job_surface(scheduler) -> list[dict]:
    """Every registered scheduler job. `str(trigger)` is APScheduler's own
    canonical rendering (cron fields / interval seconds), so it captures a
    changed minute or interval, not just a dropped job."""
    out = []
    for j in scheduler.get_jobs():
        fn = j.func
        out.append(
            {
                "id": j.id,
                "trigger": str(j.trigger),
                "func": getattr(fn, "__name__", repr(fn)),
                "kwargs": sorted((j.kwargs or {}).keys()),
            }
        )
    out.sort(key=lambda d: (d["func"], d["trigger"], d["id"]))
    return out


@pytest.fixture(scope="module")
def surface():
    """Import main and build BOTH scheduler families, without starting the
    scheduler and without running the lifespan (no network, no Kite)."""
    import main

    # register_*_scheduler_jobs are normally called from lifespan() and
    # take the scheduler as a parameter, so we can populate a throwaway
    # one and read the job table without booting the app (no network, no
    # Kite, no started scheduler).
    from apscheduler.schedulers.asyncio import AsyncIOScheduler

    probe = AsyncIOScheduler(timezone=main.IST)
    main.register_penny_scheduler_jobs(probe)
    main.register_fno_scheduler_jobs(probe)

    return {"routes": _route_surface(main.app), "jobs": _job_surface(probe)}


def test_surface_matches_golden(surface):
    if _updating():
        GOLDEN.write_text(json.dumps(surface, indent=2, sort_keys=True) + "\n")
        pytest.skip("golden regenerated -- review the diff before committing")

    if not GOLDEN.exists():
        GOLDEN.write_text(json.dumps(surface, indent=2, sort_keys=True) + "\n")
        pytest.skip("golden seeded on first run -- commit it, then this test binds")

    expected = json.loads(GOLDEN.read_text())

    # Compare the two halves separately so a failure names the subsystem.
    assert surface["routes"] == expected["routes"], (
        "HTTP route table changed. If this is an intentional route add/remove, "
        "regenerate with --update-golden and justify it in the commit message. "
        "If you are mid-refactor, a MISSING route means a decorator did not "
        "re-register after the move."
    )
    assert surface["jobs"] == expected["jobs"], (
        "Scheduler job table changed. A missing job means a scan/watchdog will "
        "NEVER FIRE AGAIN, silently -- this is the highest-severity refactor "
        "regression in this codebase. Regenerate only if intentional."
    )


def test_no_duplicate_routes(surface):
    """A path+method registered twice is always a mistake (the second
    registration is dead). Caught main.py's stacked @app.post duplicate."""
    seen = {}
    dupes = []
    for r in surface["routes"]:
        for m in r["methods"]:
            key = (m, r["path"])
            if key in seen:
                dupes.append(f"{m} {r['path']} -> {seen[key]} AND {r['endpoint']}")
            seen[key] = r["endpoint"]
    assert not dupes, f"duplicate route registrations: {dupes}"


def test_every_scheduled_job_is_callable(surface):
    """A job whose func is a bare repr (not a named function) usually means a
    lambda/partial got moved and lost its binding."""
    bad = [j for j in surface["jobs"] if j["func"].startswith("<")]
    assert not bad, f"scheduler jobs with unresolvable callables: {bad}"


# ===================================================================
# Static add_job census
# ===================================================================
# The `surface` fixture above only sees jobs registered by the two
# register_*_scheduler_jobs() functions -- 19 of them. The other 13 are
# added INLINE inside lifespan() (run_screener, the momentum scans,
# token_reconciliation, scheduler_tick, kite_endpoint_probe,
# ops_daily_snapshot, penny_daily_reset, ...), and capturing those the
# dynamic way would mean booting the app with a live Kite client.
#
# So census them statically instead: walk the AST of every module and
# record each `*.add_job(...)` call as (callable, trigger, id). The tuple
# deliberately does NOT include the file or line -- that is the whole
# point. Moving a job into scheduler_setup.py during the 4.1 split keeps
# this green; DROPPING one turns it red. Which is the invariant that
# matters, because a dropped scan job fails completely silently.

STATIC_GOLDEN = pathlib.Path(__file__).parent / "add_job_census_golden.json"
ENGINE_DIR = pathlib.Path(__file__).parent.parent


def _add_job_census() -> list[dict]:
    import ast

    out = []
    for py in sorted(ENGINE_DIR.glob("*.py")):
        tree = ast.parse(py.read_text())
        for node in ast.walk(tree):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_job"
            ):
                continue
            kw = {k.arg: ast.unparse(k.value) for k in node.keywords if k.arg}
            out.append(
                {
                    "func": ast.unparse(node.args[0]) if node.args else "?",
                    "trigger": (
                        ast.unparse(node.args[1])
                        if len(node.args) > 1
                        else kw.get("trigger")
                    ),
                    "id": kw.get("id"),
                }
            )
    out.sort(key=lambda d: (d["func"], str(d["trigger"]), str(d["id"])))
    return out


def test_add_job_census_matches_golden():
    census = _add_job_census()

    if _updating():
        STATIC_GOLDEN.write_text(json.dumps(census, indent=2, sort_keys=True) + "\n")
        pytest.skip("census regenerated -- review the diff before committing")

    if not STATIC_GOLDEN.exists():
        STATIC_GOLDEN.write_text(json.dumps(census, indent=2, sort_keys=True) + "\n")
        pytest.skip("census seeded on first run -- commit it, then this test binds")

    expected = json.loads(STATIC_GOLDEN.read_text())

    missing = [j for j in expected if j not in census]
    added = [j for j in census if j not in expected]
    assert not missing, (
        f"SCHEDULED JOB(S) DISAPPEARED: {missing}. A job that is never "
        "registered never runs, and nothing logs an error -- it just goes "
        "quiet. If you deleted it on purpose, regenerate the census."
    )
    assert not added, (
        f"new scheduled job(s) not in the census: {added}. Regenerate the "
        "census to accept them."
    )
