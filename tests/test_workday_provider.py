"""Tests for joborion.sources.workday_provider."""

from unittest.mock import patch

from joborion.sources.workday_provider import WorkdayProvider


class TestWorkdayProvider:
    def test_search_calls_scrape(self):
        provider = WorkdayProvider({"workers": 2})
        stats = {"found": 12, "new": 4, "existing": 8, "queries": 1}
        with patch("joborion.sources.workday_provider.scrape_workday", return_value=stats) as m:
            result = provider.search({"mode": "remote"})
        assert m.call_count == 1
        assert m.call_args.kwargs["workers"] == 2
        assert result.provider == "workday"
        assert result.found == 12
        assert result.stored == 4

    def test_search_defaults_workers(self):
        provider = WorkdayProvider({})
        with patch("joborion.sources.workday_provider.scrape_workday", return_value={}) as m:
            result = provider.search({})
        assert m.call_args.kwargs["workers"] == 1
        assert result.found == 0
