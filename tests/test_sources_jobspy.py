"""Tests for joborion.sources.jobspy_provider — proxy handling (E3)."""

import pytest


@pytest.fixture
def fake_search(monkeypatch):
    captured = {}

    def fake_scrape_jobspy(cfg=None, mode=None):
        captured["cfg"] = cfg
        captured["mode"] = mode
        return {"new": 0, "existing": 0, "errors": 0}

    monkeypatch.setattr(
        "joborion.sources.jobspy_provider.scrape_jobspy", fake_scrape_jobspy
    )
    return captured


class TestProxy:
    def test_proxy_kwargs(self, fake_search, monkeypatch):
        from joborion.sources.jobspy_provider import JobSpyProvider

        monkeypatch.setenv("JOBSPY_PROXY", "127.0.0.1:8080:user:pass")
        provider = JobSpyProvider({})
        provider.search({})
        assert fake_search["cfg"]["proxy"] == "127.0.0.1:8080:user:pass"

    def test_cfg_proxy_used_when_env_unset(self, fake_search, monkeypatch):
        from joborion.sources.jobspy_provider import JobSpyProvider

        monkeypatch.delenv("JOBSPY_PROXY", raising=False)
        provider = JobSpyProvider({"proxy": "proxy.example:3128"})
        provider.search({})
        assert fake_search["cfg"]["proxy"] == "proxy.example:3128"

    def test_no_proxy_when_none_configured(self, fake_search, monkeypatch):
        from joborion.sources.jobspy_provider import JobSpyProvider

        monkeypatch.delenv("JOBSPY_PROXY", raising=False)
        provider = JobSpyProvider({})
        provider.search({})
        assert fake_search["cfg"].get("proxy") is None

    def test_httpx_url_conversion(self):
        from joborion.sources.base import proxy_http_url

        assert proxy_http_url("127.0.0.1:8080") == "http://127.0.0.1:8080"
        assert proxy_http_url("127.0.0.1:8080:user:pass") == "http://user:pass@127.0.0.1:8080"
        assert proxy_http_url("http://already:url") == "http://already:url"
        assert proxy_http_url("") is None
