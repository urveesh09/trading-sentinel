import json
from pathlib import Path
import sqlite3

from tools.runtime_audit import audit_runtime, parse_log, redact_text, render_text


DAY = "2026-08-31"


def _log(tmp_path: Path, text: str, name: str = "python.log") -> Path:
    path = tmp_path / name
    path.write_text(text.strip() + "\n", encoding="utf-8")
    return path


def test_levels_are_case_insensitive_and_pino_levels_are_normalized(tmp_path):
    python_log = _log(tmp_path, """
2026-08-31 09:15:00 [INFO] upper
2026-08-31 09:15:01 [info     ] lower
2026-08-31 09:15:02 [WARNING] upper warning
2026-08-31 09:15:03 [warning  ] lower warning
2026-08-31 09:15:04 [error    ] lower error
""")
    gateway = _log(tmp_path, json.dumps({
        "time": "2026-08-31T03:45:05Z", "level": 50, "msg": "pino error",
    }), "gateway.log")
    report = audit_runtime(
        python_log=python_log, gateway_log=gateway, target_date=DAY,
    )
    assert report["levels"] == {"error": 2, "info": 2, "warning": 2}


def test_restart_gap_is_an_epoch_boundary_not_a_freeze(tmp_path):
    log = _log(tmp_path, """
2026-08-31 04:45:44 [INFO] penny_liveness_tick count=58 rss_kb=1 threads=1
INFO:     Started server process [1]
2026-08-31 07:02:06 [INFO] penny_liveness_tick count=1 rss_kb=1 threads=1
2026-08-31 07:03:06 [INFO] penny_liveness_tick count=2 rss_kb=1 threads=1
""")
    report = audit_runtime(python_log=log, target_date=DAY)
    assert len(report["boot_epochs"]) == 2
    assert report["boot_epochs"][1]["restart_gap_seconds"] == 8182
    assert not any(item["code"] == "LIVENESS_GAP" for item in report["findings"])


def test_gap_inside_one_boot_epoch_is_a_liveness_finding(tmp_path):
    log = _log(tmp_path, """
2026-08-31 10:00:00 [INFO] penny_liveness_tick count=1 rss_kb=1 threads=1
2026-08-31 10:10:01 [INFO] penny_liveness_tick count=2 rss_kb=1 threads=1
""")
    report = audit_runtime(python_log=log, target_date=DAY)
    finding = next(item for item in report["findings"] if item["code"] == "LIVENESS_GAP")
    assert finding["severity"] == "P0"
    assert "601s" in finding["message"]


def test_premarket_process_gap_is_retained_as_evidence_not_a_p0_freeze(tmp_path):
    log = _log(tmp_path, """
2026-08-31 07:00:00 [INFO] penny_liveness_tick count=1 rss_kb=1 threads=1
2026-08-31 07:10:01 [INFO] penny_liveness_tick count=2 rss_kb=1 threads=1
""")
    report = audit_runtime(python_log=log, target_date=DAY)
    assert not any(item["code"] == "LIVENESS_GAP" for item in report["findings"])
    assert report["boot_epochs"][0]["outside_market_gaps"] == [{
        "seconds": 601,
        "from": "2026-08-31T07:00:00+05:30",
        "to": "2026-08-31T07:10:01+05:30",
    }]


def test_scheduler_progress_is_a_distinct_market_hours_liveness_signal(tmp_path):
    log = _log(tmp_path, """
2026-08-31 10:00:00 [INFO] scheduler_progress_tick count=1 boot_id=one
2026-08-31 10:10:01 [INFO] scheduler_progress_tick count=2 boot_id=one
""")
    report = audit_runtime(python_log=log, target_date=DAY)
    assert report["scheduler_progress"]["status"] == "OBSERVED"
    finding = next(item for item in report["findings"]
                   if item["code"] == "SCHEDULER_PROGRESS_GAP")
    assert finding["severity"] == "P0"


def test_scheduler_boot_id_starts_a_new_epoch_not_a_freeze(tmp_path):
    log = _log(tmp_path, """
2026-08-31 10:00:00 [INFO] scheduler_progress_tick count=58 boot_id=old
2026-08-31 10:10:01 [INFO] scheduler_progress_tick count=1 boot_id=new
""")
    report = audit_runtime(python_log=log, target_date=DAY)
    assert len(report["scheduler_progress"]["epochs"]) == 2
    assert not any(item["code"] == "SCHEDULER_PROGRESS_GAP"
                   for item in report["findings"])


def test_token_state_uses_last_transition_not_boot_event_count(tmp_path):
    log = _log(tmp_path, """
2026-08-31 07:02:06 [info     ] kite_token_restore_skipped saved_date=2026-08-28 today=2026-08-31
2026-08-31 07:51:34 [info     ] kite_token_set suffix=...never-copy-this
2026-08-31 07:51:34 [info     ] kite_token_injected len=32
""")
    report = audit_runtime(python_log=log, target_date=DAY)
    assert report["token"]["status"] == "ARMED"
    assert report["token"]["last_transition"]["line"] == 3


def test_order_403_is_recognized_without_raw_http_request_and_output_is_redacted(tmp_path):
    log = _log(tmp_path, """
2026-08-31 15:00:01 [error    ] kite_place_order_failed status=403 body={"message":"IP (146.70.246.119) is not allowed to place orders","error_type":"PermissionException","access_token":"do-not-copy"}
2026-08-31 15:00:02 [INFO] penny_hourly_telegram_sent chat_id=917185439
""")
    report = audit_runtime(python_log=log, target_date=DAY)
    assert report["order_authorization"]["status"] == "BLOCKED"
    assert report["order_authorization"]["denials"] == 1
    rendered = render_text(report)
    assert "Order authorization: BLOCKED" in rendered
    assert "146.70.246.119" not in rendered
    assert "917185439" not in rendered
    assert "do-not-copy" not in rendered
    assert redact_text("chat_id=123 token=abc 10.1.2.3") == (
        "chat_id=<redacted> token=<redacted> <redacted-ip>"
    )


def test_both_apscheduler_skip_formats_are_counted(tmp_path):
    log = _log(tmp_path, """
2026-08-31 14:31:06 [WARNING] Execution of job "run_penny_scanner_once (trigger: interval[0:01:00], next run at: x)" skipped: maximum number of running instances reached (1)
2026-08-31 14:32:06 [WARNING] Job "pkg.<locals>._run_fno_tick_safe (trigger: interval[0:01:30], next run at: x)" skipped: maximum number of running instances reached (1)
""")
    report = audit_runtime(python_log=log, target_date=DAY)
    assert report["scheduler_skips"] == {
        "_run_fno_tick_safe": 1, "run_penny_scanner_once": 1,
    }


def test_absent_database_means_unknown_pnl_not_zero(tmp_path):
    log = _log(tmp_path, "2026-08-31 10:00:00 [INFO] healthy-looking line")
    report = audit_runtime(python_log=log, target_date=DAY)
    assert report["pnl"]["status"] == "UNKNOWN"
    assert report["pnl"]["realized_pnl"] is None
    assert "no SQLite snapshot" in report["pnl"]["reason"]


def test_read_only_ledger_snapshot_produces_observed_pnl(tmp_path):
    log = _log(tmp_path, "2026-08-31 10:00:00 [INFO] line")
    db = tmp_path / "snapshot.db"
    with sqlite3.connect(db) as connection:
        connection.execute("CREATE TABLE bankroll_ledger(timestamp TEXT,source TEXT,pnl REAL)")
        connection.executemany("INSERT INTO bankroll_ledger VALUES (?,?,?)", [
            ("2026-08-31T05:00:00+00:00", "PENNY", 12.5),
            ("2026-08-31T06:00:00+00:00", "MOMENTUM", -2.0),
            ("2026-08-30T06:00:00+00:00", "PENNY", 999.0),
        ])
    report = audit_runtime(python_log=log, db_snapshot=db, target_date=DAY)
    assert report["pnl"]["status"] == "OBSERVED_LEDGER"
    assert report["pnl"]["realized_pnl"] == 10.5
    assert report["pnl"]["events"] == 2


def test_none_order_id_cannot_be_reported_as_closed(tmp_path):
    log = _log(tmp_path, """
2026-08-31 15:00:01 [warning  ] penny_force_close_mis_exit ticker=AAA shares=3 order_id=None reason=time_stop
2026-08-31 15:00:02 [warning  ] penny_force_close_mis_exit ticker=BBB shares=4 order_id=None reason=time_stop
2026-08-31 15:00:03 [warning  ] penny_force_close_mis_done closed=2
""")
    report = audit_runtime(python_log=log, target_date=DAY)
    finding = next(item for item in report["findings"]
                   if item["code"] == "UNCONFIRMED_EXIT_COUNTED_CLOSED")
    assert finding["severity"] == "P0"
    assert "2 exit attempt(s) had no broker order id" in finding["message"]


def test_other_dates_do_not_affect_final_state(tmp_path):
    log = _log(tmp_path, """
2026-08-31 07:51:34 [info     ] kite_token_set suffix=...today
2026-09-01 07:00:00 [info     ] kite_token_restore_skipped saved_date=old
INFO:     Started server process [99]
""")
    assert len(parse_log(log, DAY)) == 1
    report = audit_runtime(python_log=log, target_date=DAY)
    assert report["token"]["status"] == "ARMED"
