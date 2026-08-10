from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from config import settings
import routes_promotion_readiness as route


def _client():
    app = FastAPI()
    app.include_router(route.router)
    return TestClient(app)


def _comparison(names):
    return {"as_of": "2026-08-10T10:00:00+00:00", "variants": [
        {"variant": name, "evaluations": 1, "distinct_candidates": 0}
        for name in names
    ]}


def _patch_sources(monkeypatch):
    monkeypatch.setattr(route, "momentum_shadow_comparison", AsyncMock(
        return_value=_comparison(route.MOMENTUM_VARIANTS)))
    monkeypatch.setattr(route, "penny_shadow_comparison", AsyncMock(
        return_value=_comparison(route.PENNY_VARIANTS)))
    monkeypatch.setattr(route, "fno_shadow_comparison", AsyncMock(
        return_value=_comparison(route.FNO_VARIANTS)))
    # _FAMILIES freezes callable objects at import, so update its callables too.
    monkeypatch.setitem(route._FAMILIES["MOMENTUM"], "comparison", route.momentum_shadow_comparison)
    monkeypatch.setitem(route._FAMILIES["PENNY"], "comparison", route.penny_shadow_comparison)
    monkeypatch.setitem(route._FAMILIES["FNO"], "comparison", route.fno_shadow_comparison)
    monkeypatch.setattr(route, "division_performance", AsyncMock(return_value={
        "as_of": "2026-08-10T10:05:00+00:00", "divisions": [
            {"key": key, "reconciliation": {"status": "MATCH"}}
            for key in ("momentum_paper", "penny_breakout_paper", "fno_paper")
        ],
    }))
    monkeypatch.setattr(route, "promotion_report", AsyncMock(return_value={
        "strategies": [
            {"key": key, "verdict": "legacy_candidate_for_research_review"}
            for key in ("momentum_paper", "penny_breakout_paper", "fno_paper")
        ]
    }))
    listing = AsyncMock(side_effect=lambda db, limit, strategy_id: [{
        "run_id": strategy_id, "strategy_id": strategy_id,
    }])
    detail = AsyncMock(side_effect=lambda db, run_id: {
        "run_id": run_id, "strategy_id": run_id, "status": "SUCCEEDED",
        "completed_at": "2026-08-10T10:10:00+00:00",
        "config": {"variants": []}, "dataset": {"status": "valid"},
        "result": {"oos": {"status": "insufficient_data", "scored_folds": 0}},
        "summary": {"oos": {"n_scored_folds": 0}},
    })
    monkeypatch.setattr(route, "list_runs", listing)
    monkeypatch.setattr(route, "get_run", detail)
    return listing, detail


def test_endpoint_requires_authentication():
    assert _client().get("/research/promotion-readiness").status_code == 403


def test_endpoint_aggregates_every_registered_variant_using_latest_full_runs(monkeypatch):
    listing, detail = _patch_sources(monkeypatch)
    response = _client().get(
        "/research/promotion-readiness",
        headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["research_only"] is True and body["can_place_orders"] is False
    assert body["authorization_effect"] == "NONE"
    assert body["maximum_possible_state"] == "CANDIDATE_FOR_PAPER_REVIEW"
    assert {row["strategy"] for row in body["families"]} == {"MOMENTUM", "PENNY", "FNO"}
    assert sum(len(row["variants"]) for row in body["families"]) == (
        len(route.MOMENTUM_VARIANTS) + len(route.PENNY_VARIANTS) + len(route.FNO_VARIANTS)
    )
    assert all(report["state"] != "LIVE_READY" for family in body["families"] for report in family["variants"])
    assert listing.await_count == detail.await_count == 3
    assert all(call.kwargs["limit"] == 1 for call in listing.await_args_list)


def test_family_and_variant_failures_are_isolated(monkeypatch):
    _patch_sources(monkeypatch)
    broken = AsyncMock(side_effect=RuntimeError("shadow corrupt"))
    monkeypatch.setitem(route._FAMILIES["PENNY"], "comparison", broken)
    original = route.assess_promotion_readiness

    def assess(*args, **kwargs):
        if args[1] == "MOM_BASE":
            raise ValueError("malformed evidence")
        return original(*args, **kwargs)

    monkeypatch.setattr(route, "assess_promotion_readiness", assess)
    response = _client().get(
        "/research/promotion-readiness",
        headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
    )
    assert response.status_code == 200
    by_family = {row["strategy"]: row for row in response.json()["families"]}
    assert "shadow comparison unavailable" in " ".join(by_family["PENNY"]["source_errors"])
    mom_base = next(row for row in by_family["MOMENTUM"]["variants"] if row["variant"] == "MOM_BASE")
    assert mom_base["state"] == "COLLECTING"
    assert mom_base["blockers"][0]["gate"] == "assessment_integrity"
    assert by_family["FNO"]["variants"]


def test_malformed_global_and_run_sources_degrade_without_500(monkeypatch):
    _patch_sources(monkeypatch)
    monkeypatch.setattr(route, "division_performance", AsyncMock(return_value=None))
    monkeypatch.setattr(route, "promotion_report", AsyncMock(return_value={"strategies": None}))
    monkeypatch.setattr(route, "list_runs", AsyncMock(return_value=None))

    response = _client().get(
        "/research/promotion-readiness",
        headers={"X-Internal-Secret": settings.INTERNAL_API_SECRET},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["source_errors"]) == 2
    assert all(family["source_errors"] for family in body["families"])
    assert all(
        report["state"] in {"COLLECTING", "INELIGIBLE"}
        for family in body["families"] for report in family["variants"]
    )
