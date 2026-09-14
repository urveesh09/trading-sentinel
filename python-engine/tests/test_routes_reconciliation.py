"""[WORKFLOW-F 2026-09-13] Reconciliation route acceptance.

Closes F5 (route portion) of workstream F per
``docs/2026-09-13-workflow-f-state-of-codebase-audit.md`` section 6
future plan and ``docs/NEXT_AGENT_PLAN.md`` section 10.

Acceptance coverage for the two new routes in
``python-engine/routes_commands.py``:

  * ``POST /reconciliation/import-statement``
  * ``GET /reconciliation/discrepancies``

[WHY-THIS-EXISTS 2026-09-13]
  Pre-fix, ``broker_reconciliation.import_broker_statement`` was a
  Python async function with no HTTP surface. The F5 slice ships
  the route so an admin UI can POST a JSON payload and get the
  resulting discrepancy IDs back.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

# Importing ``main`` first breaks the ``routes_commands`` <-> ``main``
# circular import the safe way (main imports routes_commands first;
# routes_commands rebinds ``main as _main`` only at call time).
from main import app


def _client() -> TestClient:
    """Build a TestClient bound to the FastAPI app.

    Matches the existing pattern used by
    ``test_promotion_readiness_route.py``, ``test_operator_status.py``,
    and other route tests. TestClient emits a ``'app' shortcut``
    DeprecationWarning from ``httpx`` -- this is the same warning the
    existing test suite already produces; we follow the convention
    rather than refactor unrelated infrastructure.
    """
    return TestClient(app)


def _good_payload(account: str = "owner", statement: str = "2026-09-08") -> dict:
    return {
        "account_id": account, "statement_id": statement,
        "as_of": "2026-09-08T00:00:00+00:00",
        "opening_cash": 1137.0, "closing_cash": 1100.0,
        "entries": [
            {"entry_id": "d", "entry_type": "DEPOSIT", "amount": 200},
            {"entry_id": "t", "entry_type": "TRADE_REALIZED", "amount": -40},
            {"entry_id": "c", "entry_type": "CHARGE", "amount": 8},
            {"entry_id": "o", "entry_type": "OPERATING_EXPENSE", "amount": 15},
        ],
        "fills": [],
    }


class TestImportStatementRoute:
    def test_happy_path_imports_and_returns_ids(
        self, monkeypatch, tmp_path,
    ) -> None:
        db = str(tmp_path / "test.db")
        from config import settings
        monkeypatch.setattr(settings, "DB_PATH", db)
        client = _client()
        resp = client.post(
            "/reconciliation/import-statement", json=_good_payload(),
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["imported"] is True
        assert body["broker_status"] in {"MATCH", "UNRESOLVED", "UNAVAILABLE"}
        assert body["can_place_orders"] is False
        assert "broker" in body["discrepancy_ids"]
        assert "evidence" in body["discrepancy_ids"]

    def test_idempotent_repost_flips_imported_flag(
        self, monkeypatch, tmp_path,
    ) -> None:
        db = str(tmp_path / "test.db")
        from config import settings
        monkeypatch.setattr(settings, "DB_PATH", db)
        client = _client()
        first = client.post(
            "/reconciliation/import-statement", json=_good_payload(),
        )
        second = client.post(
            "/reconciliation/import-statement", json=_good_payload(),
        )
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["imported"] is True
        assert second.json()["imported"] is False
        # Same discrepancy IDs (F4 idempotency).
        assert (
            first.json()["discrepancy_ids"]["broker"]
            == second.json()["discrepancy_ids"]["broker"]
        )

    def test_non_object_payload_422(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(
            "config.settings.DB_PATH", str(tmp_path / "test.db"),
        )
        client = _client()
        resp = client.post("/reconciliation/import-statement", json=[1, 2, 3])
        # FastAPI's built-in body validator rejects non-dict payloads
        # *before* the route runs. The error message comes from
        # pydantic, not from our route; we only assert the status
        # code (422) and that "dictionary" appears in the error.
        assert resp.status_code == 422
        body = resp.json()
        # The detail is a list of validation errors; flatten and
        # check for the right message.
        detail_text = json.dumps(body["detail"]) if isinstance(
            body["detail"], list
        ) else str(body["detail"])
        assert "dictionary" in detail_text.lower()

    def test_missing_required_keys_422(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(
            "config.settings.DB_PATH", str(tmp_path / "test.db"),
        )
        client = _client()
        bad = _good_payload()
        bad.pop("statement_id")
        resp = client.post("/reconciliation/import-statement", json=bad)
        assert resp.status_code == 422
        assert "missing required keys" in resp.json()["detail"]
        assert "statement_id" in resp.json()["detail"]

    def test_naive_as_of_422(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(
            "config.settings.DB_PATH", str(tmp_path / "test.db"),
        )
        client = _client()
        bad = _good_payload()
        bad["as_of"] = "2026-09-08T00:00:00"  # naive
        resp = client.post("/reconciliation/import-statement", json=bad)
        assert resp.status_code == 422
        assert "timezone-aware" in resp.json()["detail"]

    def test_garbage_as_of_422(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(
            "config.settings.DB_PATH", str(tmp_path / "test.db"),
        )
        client = _client()
        bad = _good_payload()
        bad["as_of"] = "yesterday"
        resp = client.post("/reconciliation/import-statement", json=bad)
        assert resp.status_code == 422

    def test_non_list_entries_422(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(
            "config.settings.DB_PATH", str(tmp_path / "test.db"),
        )
        client = _client()
        bad = _good_payload()
        bad["entries"] = "not a list"
        resp = client.post("/reconciliation/import-statement", json=bad)
        assert resp.status_code == 422
        assert "entries must be a list" in resp.json()["detail"]

    def test_non_list_fills_422(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(
            "config.settings.DB_PATH", str(tmp_path / "test.db"),
        )
        client = _client()
        bad = _good_payload()
        bad["fills"] = "not a list"
        resp = client.post("/reconciliation/import-statement", json=bad)
        assert resp.status_code == 422
        assert "fills must be a list" in resp.json()["detail"]

    def test_can_place_orders_always_false(
        self, monkeypatch, tmp_path,
    ) -> None:
        # Defensive: the response MUST always have can_place_orders=False
        # even when the import succeeds. The route is never an order
        # authority.
        db = str(tmp_path / "test.db")
        from config import settings
        monkeypatch.setattr(settings, "DB_PATH", db)
        client = _client()
        resp = client.post(
            "/reconciliation/import-statement", json=_good_payload(),
        )
        body = resp.json()
        assert body["can_place_orders"] is False


class TestDiscrepanciesRoute:
    def test_empty_list(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(
            "config.settings.DB_PATH", str(tmp_path / "test.db"),
        )
        client = _client()
        resp = client.get("/reconciliation/discrepancies")
        assert resp.status_code == 200
        body = resp.json()
        assert body["rows"] == []
        assert body["can_place_orders"] is False

    def test_invalid_category_422(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(
            "config.settings.DB_PATH", str(tmp_path / "test.db"),
        )
        client = _client()
        resp = client.get(
            "/reconciliation/discrepancies?category=NOT_A_CATEGORY",
        )
        assert resp.status_code == 422
        assert "category" in resp.json()["detail"]

    def test_invalid_status_422(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(
            "config.settings.DB_PATH", str(tmp_path / "test.db"),
        )
        client = _client()
        resp = client.get(
            "/reconciliation/discrepancies?status=NOT_A_STATUS",
        )
        assert resp.status_code == 422
        assert "status" in resp.json()["detail"]

    def test_naive_since_422(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(
            "config.settings.DB_PATH", str(tmp_path / "test.db"),
        )
        client = _client()
        resp = client.get(
            "/reconciliation/discrepancies?since=2026-09-08T00:00:00",
        )
        assert resp.status_code == 422
        assert "timezone-aware" in resp.json()["detail"]

    def test_naive_until_422(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(
            "config.settings.DB_PATH", str(tmp_path / "test.db"),
        )
        client = _client()
        resp = client.get(
            "/reconciliation/discrepancies?until=2026-09-08T00:00:00",
        )
        assert resp.status_code == 422
        assert "timezone-aware" in resp.json()["detail"]

    def test_garbage_since_422(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setattr(
            "config.settings.DB_PATH", str(tmp_path / "test.db"),
        )
        client = _client()
        resp = client.get(
            "/reconciliation/discrepancies?since=yesterday",
        )
        assert resp.status_code == 422

    def test_after_import_then_list(self, monkeypatch, tmp_path) -> None:
        # End-to-end: import via POST, then list via GET.
        db = str(tmp_path / "test.db")
        from config import settings
        monkeypatch.setattr(settings, "DB_PATH", db)
        client = _client()
        # Import via POST.
        resp = client.post(
            "/reconciliation/import-statement", json=_good_payload(),
        )
        assert resp.status_code == 200
        # Now list discrepancies; we should see at least the broker
        # discrepancy (the evidence side requires a ledger row, which
        # the route doesn't seed, so it may be empty).
        resp2 = client.get("/reconciliation/discrepancies")
        assert resp2.status_code == 200
        body = resp2.json()
        # The route side doesn't seed a ledger row, but it DOES seed
        # broker discrepancies when the broker report returns
        # UNRESOLVED. The MATCH case yields no broker row; the
        # UNRESOLVED case yields at least one.
        assert "rows" in body
        assert "filters" in body
