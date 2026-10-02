"""Hermetic: no pacing, no cooldowns carried between tests, librarian's
response cache off, and no request leaves the machine unless a test serves
it from `fake_get`."""
import pytest


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch):
    from librarian.config import settings as core
    from librarian_scholarly import http
    from librarian_scholarly.config import settings

    monkeypatch.setattr(core, "search_cache_enabled", False)
    monkeypatch.setattr(settings, "intervals", {k: 0.0 for k in settings.intervals})
    monkeypatch.setattr(settings, "mailto", "")
    monkeypatch.setattr(settings, "openalex_api_key", "")
    monkeypatch.setattr(settings, "ncbi_api_key", "")
    monkeypatch.setattr(settings, "semantic_scholar_api_key", "")

    def no_network(*a, **k):
        raise AssertionError("a test reached the network")
    monkeypatch.setattr("httpx.get", no_network)
    http.reset()
    yield
    http.reset()
