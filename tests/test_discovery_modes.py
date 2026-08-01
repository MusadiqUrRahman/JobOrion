"""Tests for search-mode-aware discovery helpers."""

from joborion.discovery.jobspy import _build_searches


QUERIES = [{"query": "python developer", "tier": 1}]
LOCATIONS = [
    {"location": "worldwide", "remote": True},
    {"location": "New York, NY", "remote": False},
]


class TestBuildSearches:
    def test_remote_mode_uses_worldwide_remote_only(self):
        searches, remote_only = _build_searches(QUERIES, LOCATIONS, "remote")
        assert remote_only is True
        assert len(searches) == 1
        assert searches[0]["location"] == "worldwide"
        assert searches[0]["remote"] is True

    def test_local_mode_keeps_remote_locations(self):
        searches, remote_only = _build_searches(QUERIES, LOCATIONS, "local")
        assert remote_only is False
        locations = {s["location"] for s in searches}
        assert "worldwide" in locations
        assert all(not s["remote"] or s["location"] == "worldwide" for s in searches)

    def test_sponsorship_keeps_all_locations(self):
        searches, remote_only = _build_searches(QUERIES, LOCATIONS, "sponsorship")
        assert remote_only is False
        assert len(searches) == 2

    def test_all_keeps_all_locations(self):
        searches, remote_only = _build_searches(QUERIES, LOCATIONS, "all")
        assert remote_only is False
        assert len(searches) == 2

    def test_invalid_mode_defaults_to_all(self):
        searches, remote_only = _build_searches(QUERIES, LOCATIONS, "bogus")
        assert remote_only is False
        assert len(searches) == 2
