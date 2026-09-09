from release_identity import release_identity


def test_release_identity_is_declared_only_for_a_valid_revision(monkeypatch):
    monkeypatch.setenv("SENTINEL_RELEASE_SHA", "a" * 40)
    monkeypatch.setenv("SENTINEL_BUILD_UTC", "2026-09-09T12:00:00Z")
    monkeypatch.setenv("SENTINEL_SERVICE_NAME", "python-engine")
    assert release_identity() == {
        "service": "python-engine", "revision": "a" * 40,
        "build_utc": "2026-09-09T12:00:00Z", "declared": True,
    }


def test_release_identity_makes_missing_build_data_visible(monkeypatch):
    monkeypatch.delenv("SENTINEL_RELEASE_SHA", raising=False)
    monkeypatch.delenv("SENTINEL_BUILD_UTC", raising=False)
    assert release_identity()["declared"] is False
    assert release_identity()["revision"] == "unknown"
