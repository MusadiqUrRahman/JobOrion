"""Tests for joborion.sources.ai_site_provider."""

from unittest.mock import patch

from joborion.sources.ai_site_provider import AiSiteProvider


class TestAiSiteProvider:
    def test_search_calls_scrape(self):
        provider = AiSiteProvider({"workers": 2})
        stats = {"total_new": 5, "total_existing": 3, "passed": 8, "total": 8}
        with patch("joborion.sources.ai_site_provider.scrape_ai_sites", return_value=stats) as m:
            result = provider.search({})
        assert m.call_count == 1
        assert m.call_args.kwargs["workers"] == 2
        assert result.provider == "ai_sites"
        assert result.found == 8
        assert result.stored == 5
