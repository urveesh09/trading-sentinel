from intraday_spread_replay import ReplayResult
from intraday_spread_research import build_research_artifact, create_research_run_manifest, render_research_summary


def result(state, pnl=None, identity="a"):
    return ReplayResult(state, "fixture", 100.0 if pnl is not None else None, 110.0 if pnl is not None else None,
                        2.0 if pnl is not None else None, pnl, "2026-09-10T11:00:00+05:30",
                        "2026-09-10T14:00:00+05:30", identity * 64)


def test_artifact_retains_no_fill_and_unresolved_evidence_and_cannot_auto_qualify():
    artifact = build_research_artifact(dataset_sha256="b" * 64, code_revision="d1f6467",
                                       results=[result("CLOSED", 8.0, "a"), result("NO_FILL", identity="b"), result("UNRESOLVED", identity="c")],
                                       session_dates=["2026-09-10"], declared_min_sessions=2, declared_min_closed_trades=2)
    assert artifact["outcomes"] == {"submitted": 3, "deduplicated": 3, "closed": 1, "no_fill": 1, "unresolved": 1,
                                    "rejected": 0, "net_pnl_rs": 8.0, "net_expectancy_rs": 8.0}
    assert artifact["review_state"] == "INSUFFICIENT_EVIDENCE"
    assert artifact["automatic_qualification"] is False
    assert "not a delivery" in render_research_summary(artifact)


def test_artifact_hash_is_stable_when_created_at_is_frozen(monkeypatch):
    import intraday_spread_research as research
    class Clock:
        @classmethod
        def now(cls, _tz):
            from datetime import datetime, timezone
            return datetime(2026, 9, 10, tzinfo=timezone.utc)
    monkeypatch.setattr(research, "datetime", Clock)
    manifest = create_research_run_manifest(dataset_sha256="c" * 64, code_revision="rev", session_dates=["2026-09-10"],
                                            declared_min_sessions=1, declared_min_closed_trades=1, policy_groups={"NIFTY": {}})
    first = build_research_artifact(dataset_sha256="c" * 64, code_revision="rev", results=[result("CLOSED", -2.0)],
                                    session_dates=["2026-09-10"], declared_min_sessions=1, declared_min_closed_trades=1,
                                    policy_groups={"NIFTY": {}}, run_manifest=manifest)
    second = build_research_artifact(dataset_sha256="c" * 64, code_revision="rev", results=[result("CLOSED", -2.0)],
                                     session_dates=["2026-09-10"], declared_min_sessions=1, declared_min_closed_trades=1,
                                     policy_groups={"NIFTY": {}}, run_manifest=manifest)
    assert first["artifact_sha256"] == second["artifact_sha256"]
    assert first["review_state"] == "READY_FOR_HUMAN_REVIEW"
