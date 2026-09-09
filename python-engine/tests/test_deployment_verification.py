import importlib.util
from pathlib import Path

import pytest

_path = Path(__file__).parents[2] / "scripts" / "verify_deployment.py"
_spec = importlib.util.spec_from_file_location("verify_deployment", _path)
verify_deployment = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
_spec.loader.exec_module(verify_deployment)


SHA = "a" * 40


def _inspect(service, sha=SHA):
    return {"Id": service * 5, "Image": "sha256:image", "State": {"StartedAt": "2026-09-09T12:00:00Z"},
            "Config": {"Env": [f"SENTINEL_RELEASE_SHA={sha}", f"SENTINEL_SERVICE_NAME={service}",
                               "SENTINEL_BUILD_UTC=2026-09-09T11:59:00Z"]}}


def test_verifier_accepts_one_fully_identified_release():
    result = verify_deployment.verify_containers(SHA, {service: _inspect(service) for service in verify_deployment.APPLICATION_SERVICES})
    assert result["expected_sha"] == SHA
    verify_deployment.verify_health(SHA, {"release": {"revision": SHA, "declared": True},
                                          "python_engine_release": {"revision": SHA, "declared": True}})


def test_verifier_rejects_mixed_service_images():
    data = {service: _inspect(service) for service in verify_deployment.APPLICATION_SERVICES}
    data["agent"] = _inspect("agent", "b" * 40)
    with pytest.raises(verify_deployment.VerificationError, match="agent: release SHA"):
        verify_deployment.verify_containers(SHA, data)


def test_verifier_rejects_stale_gateway_health():
    with pytest.raises(verify_deployment.VerificationError, match="gateway health"):
        verify_deployment.verify_health(SHA, {"release": {"revision": "b" * 40, "declared": True},
                                              "python_engine_release": {"revision": SHA, "declared": True}})
