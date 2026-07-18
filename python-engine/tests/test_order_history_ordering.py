"""[ORDER-HISTORY-2026-07-17] latest_order_state() ordering.

Kite's GET /orders/{id} returns history rows chronologically (oldest
first). Three call sites (penny_executor, fno_executor, the momentum
intraday monitor) read `history[0]`, believing it was the newest -- so a
filled order's COMPLETE row (always LAST) was invisible and every live
edge entry since 2026-07-15 "timed out". These tests pin the correct
selection.
"""
from kite_client import latest_order_state


def test_empty_history_returns_empty_dict():
    assert latest_order_state([]) == {}
    assert latest_order_state(None or []) == {}


def test_picks_last_row_by_timestamp_not_index_zero():
    history = [
        {"status": "PUT ORDER REQ RECEIVED",
         "order_timestamp": "2026-07-17 09:30:00"},
        {"status": "OPEN", "order_timestamp": "2026-07-17 09:30:01"},
        {"status": "COMPLETE", "average_price": 34.53,
         "order_timestamp": "2026-07-17 09:30:04"},
    ]
    latest = latest_order_state(history)
    assert latest["status"] == "COMPLETE"
    assert latest["average_price"] == 34.53


def test_out_of_order_rows_still_resolve_to_newest():
    """Even if a relay reorders rows, sort by timestamp wins."""
    history = [
        {"status": "COMPLETE", "order_timestamp": "2026-07-17 09:30:04"},
        {"status": "OPEN", "order_timestamp": "2026-07-17 09:30:01"},
    ]
    assert latest_order_state(history)["status"] == "COMPLETE"


def test_missing_timestamps_fall_back_to_list_position():
    """No order_timestamp on any row -> last element is the current state."""
    history = [
        {"status": "OPEN"},
        {"status": "COMPLETE"},
    ]
    assert latest_order_state(history)["status"] == "COMPLETE"


def test_single_row_history():
    assert latest_order_state([{"status": "REJECTED"}])["status"] == "REJECTED"
