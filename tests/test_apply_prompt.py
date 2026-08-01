"""Tests for the apply prompt location check (profile/mode-driven)."""

from joborion.apply.prompt import _build_location_check

PAKISTAN_PROFILE = {
    "personal": {"city": "mardan", "province_state": "kpk", "country": "Pakistan"},
    "work_authorization": {
        "legally_authorized_to_work": True,
        "require_sponsorship": True,
        "authorized_countries": [],
        "relocation_willing": False,
    },
}


def _cfg(mode: str) -> dict:
    return {"defaults": {"search_mode": mode}}


class TestLocationCheck:
    def test_remote_mode_rejects_onsite(self):
        text = _build_location_check(PAKISTAN_PROFILE, _cfg("remote"))
        assert "not_remote" in text
        assert "RESULT:FAILED:not_remote" in text

    def test_local_mode_mentions_home_country(self):
        text = _build_location_check(PAKISTAN_PROFILE, _cfg("local"))
        assert "pakistan" in text
        assert "not_eligible_location" in text

    def test_sponsorship_mode_includes_relocation(self):
        text = _build_location_check(PAKISTAN_PROFILE, _cfg("sponsorship"))
        assert "sponsorship" in text.lower() or "visa sponsorship" in text

    def test_all_mode_includes_authorized_countries(self):
        text = _build_location_check(PAKISTAN_PROFILE, _cfg("all"))
        assert "country_restricted" in text
        assert "pakistan" in text

    def test_relocation_willing_changes_rules(self):
        willing = {
            **PAKISTAN_PROFILE,
            "work_authorization": {
                **PAKISTAN_PROFILE["work_authorization"],
                "relocation_willing": True,
            },
        }
        text = _build_location_check(willing, _cfg("all"))
        assert "ELIGIBLE" in text

    def test_unknown_mode_falls_back_to_all(self):
        text = _build_location_check(PAKISTAN_PROFILE, _cfg("bogus"))
        assert "country_restricted" in text
