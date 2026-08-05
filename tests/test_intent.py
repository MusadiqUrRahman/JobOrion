"""Tests for joborion.sourcing.intent — preference-to-search-intent mapping."""

from joborion.sourcing.intent import map_arrangement


class TestIntent:
    def test_remote_maps_to_remote_only(self):
        prefs = {
            "arrangement": "remote",
            "locations": ["worldwide"],
            "job_types": ["fulltime"],
            "min_salary": 60000,
            "seniority": ["mid"],
            "sponsorship_ok": True,
        }
        intent = map_arrangement(prefs)
        assert intent["mode"] == "remote"
        assert intent["remote_only"] is True

    def test_hybrid_maps_to_local(self):
        prefs = {"arrangement": "hybrid", "locations": ["germany"]}
        intent = map_arrangement(prefs)
        assert intent["mode"] == "local"
        assert intent["remote_only"] is False

    def test_onsite_maps_to_local(self):
        prefs = {"arrangement": "onsite"}
        intent = map_arrangement(prefs)
        assert intent["mode"] == "local"
        assert intent["remote_only"] is False

    def test_all_maps_to_all(self):
        prefs = {"arrangement": "all"}
        intent = map_arrangement(prefs)
        assert intent["mode"] == "all"
        assert intent["remote_only"] is False

    def test_missing_arrangement_defaults_to_all(self):
        intent = map_arrangement({})
        assert intent["mode"] == "all"

    def test_carries_filter_flags(self):
        prefs = {
            "arrangement": "remote",
            "locations": ["worldwide"],
            "job_types": ["fulltime"],
            "min_salary": 60000,
            "seniority": ["mid", "senior"],
            "sponsorship_ok": False,
        }
        intent = map_arrangement(prefs)
        assert intent["min_salary"] == 60000
        assert intent["job_types"] == ["fulltime"]
        assert intent["seniority"] == ["mid", "senior"]
        assert intent["sponsorship_ok"] is False
        assert intent["locations"] == ["worldwide"]
