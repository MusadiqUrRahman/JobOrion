"""Tests for the eligibility engine (profile-driven, any country)."""


from joborion.eligibility import (
    REASON_COUNTRY_RESTRICTED,
    REASON_LOCATION,
    REASON_NOT_REMOTE,
    evaluate_job,
    location_country,
)

PAKISTAN_PROFILE = {
    "personal": {"city": "mardan", "province_state": "kpk", "country": "Pakistan"},
    "work_authorization": {
        "legally_authorized_to_work": True,
        "require_sponsorship": True,
        "authorized_countries": [],
        "relocation_willing": False,
    },
}

US_CITIZEN_PROFILE = {
    "personal": {"city": "Austin", "province_state": "Texas", "country": "United States"},
    "work_authorization": {
        "legally_authorized_to_work": True,
        "require_sponsorship": False,
        "authorized_countries": ["United States"],
        "relocation_willing": False,
    },
}


def _job(location: str | None) -> dict:
    return {"location": location}


class TestLocationCountry:
    def test_matches_spellings(self):
        assert location_country("Remote, US (Remote)") == "us"
        assert location_country("United Arab Emirates") == "uae"
        assert location_country("Lahore, Punjab, Pakistan") == "pakistan"
        assert location_country("London, UK") == "uk"

    def test_unknown_returns_none(self):
        assert location_country("Somewhere else entirely") is None


class TestRemoteMode:
    def test_remote_unrestricted_eligible(self):
        r = evaluate_job(_job("Remote"), PAKISTAN_PROFILE, mode="remote")
        assert r.eligible is True

    def test_remote_anywhere_eligible(self):
        r = evaluate_job(_job("Remote, anywhere"), PAKISTAN_PROFILE, mode="remote")
        assert r.eligible is True

    def test_onsite_rejected(self):
        r = evaluate_job(_job("Lahore, Pakistan"), PAKISTAN_PROFILE, mode="remote")
        assert r.eligible is False
        assert r.reason == REASON_NOT_REMOTE
        assert r.suggestion

    def test_remote_restricted_foreign_rejected(self):
        r = evaluate_job(_job("Remote, US (Remote)"), PAKISTAN_PROFILE, mode="remote")
        assert r.eligible is False
        assert r.reason == REASON_COUNTRY_RESTRICTED

    def test_remote_restricted_home_country_eligible(self):
        r = evaluate_job(_job("Remote, Pakistan"), PAKISTAN_PROFILE, mode="remote")
        assert r.eligible is True


class TestLocalMode:
    def test_onsite_home_eligible(self):
        r = evaluate_job(_job("Islamabad, Pakistan"), PAKISTAN_PROFILE, mode="local")
        assert r.eligible is True

    def test_onsite_foreign_rejected(self):
        r = evaluate_job(_job("Dubai, UAE"), PAKISTAN_PROFILE, mode="local")
        assert r.eligible is False
        assert r.reason == REASON_LOCATION

    def test_remote_unrestricted_eligible(self):
        r = evaluate_job(_job("Remote"), PAKISTAN_PROFILE, mode="local")
        assert r.eligible is True

    def test_remote_restricted_home_eligible(self):
        r = evaluate_job(_job("Remote, Pakistan"), PAKISTAN_PROFILE, mode="local")
        assert r.eligible is True

    def test_remote_restricted_foreign_rejected(self):
        r = evaluate_job(_job("Remote, US"), PAKISTAN_PROFILE, mode="local")
        assert r.eligible is False
        assert r.reason == REASON_LOCATION


class TestSponsorshipMode:
    def test_foreign_onsite_relocatable_eligible(self):
        profile = {
            **PAKISTAN_PROFILE,
            "work_authorization": {
                **PAKISTAN_PROFILE["work_authorization"],
                "relocation_willing": True,
            },
        }
        r = evaluate_job(_job("London, UK"), profile, mode="sponsorship")
        assert r.eligible is True

    def test_foreign_onsite_not_relocatable_rejected(self):
        r = evaluate_job(_job("London, UK"), PAKISTAN_PROFILE, mode="sponsorship")
        assert r.eligible is False
        assert r.reason == REASON_LOCATION

    def test_authorized_foreign_country_eligible(self):
        profile = {
            **PAKISTAN_PROFILE,
            "work_authorization": {
                **PAKISTAN_PROFILE["work_authorization"],
                "authorized_countries": ["United Kingdom"],
            },
        }
        r = evaluate_job(_job("Manchester, UK"), profile, mode="sponsorship")
        assert r.eligible is True


class TestAllMode:
    def test_remote_unrestricted_eligible(self):
        r = evaluate_job(_job("Remote"), PAKISTAN_PROFILE, mode="all")
        assert r.eligible is True

    def test_onsite_home_eligible(self):
        r = evaluate_job(_job("Karachi, Pakistan"), PAKISTAN_PROFILE, mode="all")
        assert r.eligible is True

    def test_onsite_foreign_needs_sponsorship_rejected(self):
        r = evaluate_job(_job("New York, USA"), PAKISTAN_PROFILE, mode="all")
        assert r.eligible is False
        assert r.reason == REASON_LOCATION

    def test_remote_restricted_foreign_rejected(self):
        r = evaluate_job(_job("Remote, US"), PAKISTAN_PROFILE, mode="all")
        assert r.eligible is False
        assert r.reason == REASON_COUNTRY_RESTRICTED

    def test_authorized_foreign_country_eligible(self):
        profile = {
            **PAKISTAN_PROFILE,
            "work_authorization": {
                **PAKISTAN_PROFILE["work_authorization"],
                "authorized_countries": ["Germany"],
            },
        }
        r = evaluate_job(_job("Berlin, Germany"), profile, mode="all")
        assert r.eligible is True

    def test_no_sponsorship_needed_foreign_onsite_requires_sponsorship(self):
        r = evaluate_job(_job("San Francisco, US"), US_CITIZEN_PROFILE, mode="all")
        # US citizen, US job — eligible
        assert r.eligible is True

    def test_us_citizen_foreign_onsite(self):
        r = evaluate_job(_job("Toronto, Canada"), US_CITIZEN_PROFILE, mode="all")
        assert r.eligible is False


class TestUnknownLocation:
    def test_no_location_passes(self):
        r = evaluate_job(_job(None), PAKISTAN_PROFILE, mode="all")
        assert r.eligible is True

    def test_unrecognized_location_passes(self):
        r = evaluate_job(_job("Somewhere bizarre"), PAKISTAN_PROFILE, mode="all")
        assert r.eligible is True

    def test_unknown_mode_defaults_to_all(self):
        r = evaluate_job(_job("New York, USA"), PAKISTAN_PROFILE, mode="bogus")
        assert r.eligible is False
