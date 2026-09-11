from datetime import datetime, timedelta
import hashlib
import json
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from partner_research_capture import persist_public_input


def test_capture_retains_frame_and_actual_late_receipt(tmp_path):
    now = datetime(2026, 9, 11, 10, tzinfo=ZoneInfo("Asia/Kolkata"))
    bars = pd.DataFrame({"open": [100.], "high": [102.], "low": [99.], "close": [101.], "volume": [50.]},
                        index=pd.to_datetime(["2026-09-11 09:55"]))
    scan = SimpleNamespace(name="NIFTY", research_bars=bars, research_received_at=now + timedelta(seconds=3),
                           research_future_token=123, sig=None, error="")
    result = persist_public_input(tmp_path, scan, regime="NORMAL", evaluation_at=now)
    repeated = persist_public_input(tmp_path, scan, regime="NORMAL", evaluation_at=now)
    assert result == repeated
    from pathlib import Path
    raw = Path(result["path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == result["sha256"]
    payload = json.loads(raw)
    assert payload["received_at"] != payload["evaluation_at"]
    assert payload["bars"][0]["close"] == 101
    assert payload["can_qualify"] is False
    Path(result["path"]).write_text("corrupted")
    with pytest.raises(ValueError, match="hash mismatch"):
        persist_public_input(tmp_path, scan, regime="NORMAL", evaluation_at=now)


def test_missing_capture_is_explicit(tmp_path):
    result = persist_public_input(tmp_path, SimpleNamespace(), regime="NORMAL", evaluation_at=None)
    assert result == {"state": "UNAVAILABLE", "reason": "observed_bars_missing"}
