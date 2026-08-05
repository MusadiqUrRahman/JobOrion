"""Tests for joborion.sources.jobspy_provider."""

from unittest.mock import patch

from joborion.sources.jobspy_provider import JobSpyProvider


class TestJobSpyProvider:
    def test_search_calls_scrape_with_mode(self):
        provider = JobSpyProvider({"sites": ["indeed"], "results_per_site": 10})
        stats = {"new": 5, "existing": 3, "errors": 0, "db_total": 8, "queries": 2}
        with patch("joborion.sources.jobspy_provider.scrape_jobspy", return_value=stats) as m:
            result = provider.search({"mode": "remote"})
        assert m.call_count == 1
        assert m.call_args.kwargs["mode"] == "remote"
        assert result.provider == "jobspy"
        assert result.found == 8
        assert result.stored == 5
        assert result.errors == 0

    def test_search_forwards_provider_options(self):
        provider = JobSpyProvider({"sites": ["bayt"], "results_per_site": 25, "hours_old": 48})
        with patch("joborion.sources.jobspy_provider.scrape_jobspy", return_value={}) as m:
            provider.search({"mode": "all"})
        cfg = m.call_args.kwargs["cfg"]
        assert cfg["sites"] == ["bayt"]
        assert cfg["defaults"]["results_per_site"] == 25
        assert cfg["defaults"]["hours_old"] == 48

    def test_search_handles_missing_intent(self):
        provider = JobSpyProvider({})
        with patch("joborion.sources.jobspy_provider.scrape_jobspy", return_value={}) as m:
            result = provider.search({})
        assert m.call_args.kwargs["mode"] is None
        assert result.stored == 0
