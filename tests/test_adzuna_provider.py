"""Tests for joborion.sources.adzuna_provider."""

import pytest

from joborion.database import init_db, close_connection
from joborion.sources.adzuna_provider import AdzunaProvider

SEARCH_CONFIG = {"queries": [{"query": "software engineer", "tier": 1}]}

PAYLOAD = {
    "results": [
        {
            "title": "Software Engineer",
            "company": {"display_name": "Acme Corp"},
            "location": {"display_name": "London"},
            "description": "<p>Build <b>great</b> things.</p>",
            "redirect_url": "https://adzuna.com/jobs/1",
            "salary_min": 60000,
            "salary_max": 80000,
            "contract_type": "permanent",
            "created": "2026-07-01T10:00:00Z",
        },
        {
            "title": "Senior Python Developer",
            "company": {"display_name": "Globex"},
            "location": {"display_name": "Remote"},
            "description": "Remote role &amp; async team.",
            "redirect_url": "https://adzuna.com/jobs/2",
            "salary_min": 90000,
            "salary_max": 110000,
            "contract_type": "permanent",
            "created": "2026-07-02T10:00:00Z",
        },
    ]
}


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    close_connection(str(db_path))
    c = init_db(str(db_path))
    yield c
    close_connection(str(db_path))


def _set_creds(monkeypatch):
    monkeypatch.setenv("ADZUNA_APP_ID", "test_id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "test_key")
    monkeypatch.setattr("joborion.sources.adzuna_provider.load_env", lambda: None)
    monkeypatch.setattr(
        "joborion.sources.adzuna_provider.load_search_config", lambda: SEARCH_CONFIG
    )


class TestAdzunaProvider:
    def test_parses_response(self, conn, monkeypatch):
        _set_creds(monkeypatch)
        monkeypatch.setattr(
            "joborion.sources.adzuna_provider.get_connection", lambda db_path=None: conn
        )
        monkeypatch.setattr("joborion.sources.adzuna_provider._fetch", lambda url, params: PAYLOAD)

        provider = AdzunaProvider({})
        result = provider.search({"locations": ["london"]})

        assert result.provider == "adzuna"
        assert result.found == 2
        assert result.stored == 2
        assert result.errors == 0
        row = conn.execute(
            "SELECT * FROM jobs WHERE url = ?", ("https://adzuna.com/jobs/1",)
        ).fetchone()
        assert row["title"] == "Software Engineer"
        assert row["salary"] == "USD60,000-USD80,000/year"
        assert row["site"] == "adzuna"

    def test_missing_key_returns_empty(self, monkeypatch):
        monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
        monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
        monkeypatch.setattr("joborion.sources.adzuna_provider.load_env", lambda: None)
        calls = []

        def fake_fetch(url, params):
            calls.append((url, params))
            return PAYLOAD

        monkeypatch.setattr("joborion.sources.adzuna_provider._fetch", fake_fetch)

        provider = AdzunaProvider({})
        result = provider.search({})

        assert result.found == 0
        assert result.errors == 0
        assert calls == []

    def test_sends_expected_params(self, monkeypatch):
        _set_creds(monkeypatch)
        captured = {}

        def fake_fetch(url, params):
            captured["url"] = url
            captured["params"] = params
            return {"results": []}

        monkeypatch.setattr("joborion.sources.adzuna_provider._fetch", fake_fetch)

        provider = AdzunaProvider({})
        result = provider.search(
            {"locations": ["london"], "job_types": ["fulltime"], "min_salary": 60000}
        )

        params = captured["params"]
        assert "what" in params
        assert params["full_time"] == "1"
        assert params["salary_min"] == 60000
        assert params["location0"] == "london"
        assert params["app_id"] == "test_id"
        assert params["results_per_page"] == 50
        assert captured["url"] == "https://api.adzuna.com/v1/api/jobs/gb/search/1"
        assert result.found == 0

    def test_network_error_counts(self, monkeypatch):
        _set_creds(monkeypatch)

        def boom(url, params):
            raise RuntimeError("boom")

        monkeypatch.setattr("joborion.sources.adzuna_provider._fetch", boom)

        provider = AdzunaProvider({})
        result = provider.search({})

        assert result.errors == 1
        assert result.error == "boom"
