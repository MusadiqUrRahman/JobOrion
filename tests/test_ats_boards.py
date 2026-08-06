"""Tests for joborion.sources.ats_boards — ATS boards provider."""

import pytest

from joborion.database import init_db, close_connection
from joborion.sources.ats_boards import (
    AtsBoardsProvider,
    load_companies,
    parse_ashby,
    parse_greenhouse,
    parse_lever,
    parse_smartrecruiters,
)


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    close_connection(str(db_path))
    c = init_db(str(db_path))
    yield c
    close_connection(str(db_path))


VALID_PLATFORMS = {"greenhouse", "lever", "ashby", "smartrecruiters"}


class TestCompaniesYaml:
    def test_loads_companies(self):
        companies = load_companies()
        assert len(companies) >= 25
        for entry in companies.values():
            assert entry["platform"] in VALID_PLATFORMS
            assert entry["slug"]


class TestGreenhouse:
    def test_parses_postings(self):
        payload = {
            "jobs": [
                {
                    "id": 123,
                    "title": "Backend Engineer",
                    "location": {"name": "Remote, US"},
                    "absolute_url": "https://boards.greenhouse.io/gitlab/jobs/123",
                    "updated_at": "2026-01-02T03:04:05Z",
                    "company_name": "GitLab",
                },
                {
                    "id": 456,
                    "title": "Product Designer",
                    "location": {"name": "San Francisco, CA"},
                    "absolute_url": "https://boards.greenhouse.io/gitlab/jobs/456",
                    "updated_at": "2026-01-03T00:00:00Z",
                    "company_name": "GitLab",
                },
            ]
        }
        jobs = parse_greenhouse("gitlab", "GitLab", payload)
        assert len(jobs) == 2
        first = jobs[0]
        assert first.title == "Backend Engineer"
        assert first.company == "GitLab"
        assert first.location == "Remote, US"
        assert first.url == "https://boards.greenhouse.io/gitlab/jobs/123"
        assert first.apply_url == first.url
        assert first.posted_at == "2026-01-02T03:04:05Z"
        assert first.source == "ats_boards"
        assert first.site == "greenhouse-gitlab"
        assert first.description == ""


class TestLever:
    def test_parses_postings(self):
        payload = [
            {
                "id": "1",
                "text": "Engineering Manager",
                "categories": {
                    "location": "Remote",
                    "commitment": "Full-time",
                    "allLocations": ["Remote", "New York, NY"],
                },
                "descriptionPlain": "Lead the engineering team",
                "description": "<p>Lead the engineering team</p>",
                "hostedUrl": "https://jobs.lever.co/spotify/1",
                "applyUrl": "https://jobs.lever.co/spotify/1/apply",
                "createdAt": "2026-01-04T00:00:00Z",
            },
            {
                "id": "2",
                "text": "Data Analyst",
                "categories": {"location": "London, UK", "commitment": "Full-time", "allLocations": []},
                "description": "<p>Analyst role</p>",
                "hostedUrl": "https://jobs.lever.co/spotify/2",
                "createdAt": "2026-01-05T00:00:00Z",
            },
        ]
        jobs = parse_lever("spotify", payload)
        first = jobs[0]
        assert first.title == "Engineering Manager"
        assert first.company == "spotify"
        assert first.location == "Remote, New York, NY"
        assert first.description == "Lead the engineering team"
        assert first.url == "https://jobs.lever.co/spotify/1"
        assert first.apply_url == "https://jobs.lever.co/spotify/1/apply"
        assert first.job_type == "Full-time"
        assert first.posted_at == "2026-01-04T00:00:00Z"

        second = jobs[1]
        assert second.description == "Analyst role"
        assert second.apply_url == second.url
        assert second.location == "London, UK"


class TestAshby:
    def test_parses_postings(self):
        payload = {
            "jobs": [
                {
                    "id": "1",
                    "title": "Solutions Engineer",
                    "location": "New York, NY",
                    "secondaryLocations": ["Remote"],
                    "employmentType": "Full-time",
                    "seniority": "Mid-Senior",
                    "publishedAt": "2026-02-01T00:00:00Z",
                    "jobUrl": "https://jobs.ashbyhq.com/notion/1",
                    "descriptionPlain": "Own the pre-sales loop",
                    "applyUrl": "https://jobs.ashbyhq.com/notion/1/apply",
                    "isRemote": True,
                },
                {
                    "id": "2",
                    "title": "Platform Engineer",
                    "location": "London, UK",
                    "employmentType": "Full-time",
                    "seniority": "Senior",
                    "publishedAt": "2026-02-02T00:00:00Z",
                    "jobUrl": "https://jobs.ashbyhq.com/notion/2",
                    "descriptionPlain": "Build internal tooling",
                },
            ]
        }
        jobs = parse_ashby("notion", payload)
        first = jobs[0]
        assert first.title == "Solutions Engineer"
        assert first.company == "notion"
        assert first.location == "New York, NY, Remote"
        assert first.description == "Own the pre-sales loop"
        assert first.url == "https://jobs.ashbyhq.com/notion/1"
        assert first.apply_url == "https://jobs.ashbyhq.com/notion/1/apply"
        assert first.job_type == "Full-time"
        assert first.seniority == "Mid-Senior"
        assert first.is_remote is True
        assert first.posted_at == "2026-02-01T00:00:00Z"

        second = jobs[1]
        assert second.is_remote is False
        assert second.apply_url == second.url


class TestSmartRecruiters:
    def test_parses_postings(self):
        payload = {
            "content": [
                {
                    "id": "1",
                    "name": "Account Executive",
                    "companyName": "Workato",
                    "releasedDate": "2026-03-01T00:00:00Z",
                    "location": {"city": "San Francisco", "country": "us", "fullLocation": "San Francisco, CA, United States"},
                    "department": {"label": "Sales"},
                    "ref": "REF123",
                    "jobUrl": "https://jobs.smartrecruiters.com/Workato/REF123",
                    "jobType": "Full-time",
                    "experienceLevel": {"label": "Mid-Senior"},
                },
                {
                    "id": "2",
                    "name": "Support Specialist",
                    "company": {"identifier": "Visa", "name": "Visa"},
                    "releasedDate": "2026-03-02T00:00:00Z",
                    "location": {"city": "Austin", "country": "us"},
                    "department": {"label": "Support"},
                    "ref": "REF456",
                    "experienceLevel": {"label": "Associate"},
                    "typeOfEmployment": {"label": "Full-time"},
                },
            ]
        }
        jobs = parse_smartrecruiters(payload)
        first = jobs[0]
        assert first.title == "Account Executive"
        assert first.company == "Workato"
        assert first.location == "San Francisco, CA, United States"
        assert first.url == "https://jobs.smartrecruiters.com/Workato/REF123"
        assert first.apply_url == first.url
        assert first.job_type == "Full-time"
        assert first.seniority == "Mid-Senior"
        assert first.posted_at == "2026-03-01T00:00:00Z"

        second = jobs[1]
        assert second.company == "Visa"
        assert second.job_type == "Full-time"
        assert second.seniority == "Associate"
        assert second.location == "Austin, us"
        assert second.url == "https://jobs.smartrecruiters.com/Visa/REF456"


class TestAtsBoards:
    def test_filters_companies_by_industries(self, monkeypatch):
        companies = {
            "spotify": {
                "platform": "lever",
                "slug": "spotify",
                "industries": ["music", "entertainment"],
                "region": "global",
                "tags": [],
            },
            "stripe": {
                "platform": "greenhouse",
                "slug": "stripe",
                "industries": ["payments", "fintech"],
                "region": "global",
                "tags": [],
            },
        }
        monkeypatch.setattr("joborion.sources.ats_boards.load_companies", lambda: companies)
        monkeypatch.setattr(
            "joborion.sources.ats_boards.load_preferences",
            lambda: {"industries": ["music"], "sponsorship_ok": True},
        )
        provider = AtsBoardsProvider({})
        selected = provider._select_companies({})
        assert [c["slug"] for c in selected] == ["spotify"]

    def test_drops_sponsorship_companies_when_not_ok(self, monkeypatch):
        companies = {
            "spotify": {"platform": "lever", "slug": "spotify", "industries": [], "region": "global", "tags": []},
            "deel": {"platform": "ashby", "slug": "deel", "industries": [], "region": "global", "tags": ["sponsorship"]},
        }
        monkeypatch.setattr("joborion.sources.ats_boards.load_companies", lambda: companies)
        monkeypatch.setattr(
            "joborion.sources.ats_boards.load_preferences",
            lambda: {"industries": [], "sponsorship_ok": False},
        )
        provider = AtsBoardsProvider({})
        selected = provider._select_companies({})
        assert [c["slug"] for c in selected] == ["spotify"]

    def test_filters_companies_by_region(self, monkeypatch):
        companies = {
            "wealthsimple": {"platform": "lever", "slug": "wealthsimple", "industries": [], "region": "canada", "tags": []},
            "kraken": {"platform": "lever", "slug": "kraken", "industries": [], "region": "global", "tags": []},
        }
        monkeypatch.setattr("joborion.sources.ats_boards.load_companies", lambda: companies)
        monkeypatch.setattr(
            "joborion.sources.ats_boards.load_preferences",
            lambda: {"industries": [], "sponsorship_ok": True},
        )
        provider = AtsBoardsProvider({})
        selected = provider._select_companies({"locations": ["canada"]})
        assert [c["slug"] for c in selected] == ["wealthsimple", "kraken"]

    def test_search_stores_and_counts(self, conn, monkeypatch):
        companies = {
            "gitlab": {"platform": "greenhouse", "slug": "gitlab", "industries": [], "region": "global", "tags": []},
        }
        monkeypatch.setattr("joborion.sources.ats_boards.load_companies", lambda: companies)
        monkeypatch.setattr(
            "joborion.sources.ats_boards.load_preferences",
            lambda: {"industries": [], "sponsorship_ok": True},
        )
        monkeypatch.setattr("joborion.sources.ats_boards.get_connection", lambda: conn)
        payload = {
            "jobs": [
                {
                    "id": 1,
                    "title": "Backend Engineer",
                    "location": {"name": "Remote, US"},
                    "absolute_url": "https://boards.greenhouse.io/gitlab/jobs/1",
                    "updated_at": "2026-01-01T00:00:00Z",
                    "company_name": "GitLab",
                }
            ]
        }
        monkeypatch.setattr("joborion.sources.ats_boards._fetch_greenhouse", lambda slug, params, proxy=None: payload)

        provider = AtsBoardsProvider({"max_per_company": 50, "max_results": 300})
        result = provider.search({})

        assert result.provider == "ats_boards"
        assert result.found == 1
        assert result.stored == 1
        assert result.errors == 0
        row = conn.execute("SELECT * FROM jobs WHERE url = ?", ("https://boards.greenhouse.io/gitlab/jobs/1",)).fetchone()
        assert row["site"] == "greenhouse-gitlab"

    def test_company_error_does_not_abort(self, conn, monkeypatch):
        companies = {
            "good": {"platform": "greenhouse", "slug": "good", "industries": [], "region": "global", "tags": []},
            "bad": {"platform": "greenhouse", "slug": "bad", "industries": [], "region": "global", "tags": []},
        }
        monkeypatch.setattr("joborion.sources.ats_boards.load_companies", lambda: companies)
        monkeypatch.setattr(
            "joborion.sources.ats_boards.load_preferences",
            lambda: {"industries": [], "sponsorship_ok": True},
        )
        monkeypatch.setattr("joborion.sources.ats_boards.get_connection", lambda: conn)

        def fake_fetch(slug, params, proxy=None):
            if slug == "bad":
                raise RuntimeError("board exploded")
            return {
                "jobs": [
                    {
                        "id": 1,
                        "title": "Engineer",
                        "location": {"name": "Remote"},
                        "absolute_url": f"https://boards.greenhouse.io/{slug}/jobs/1",
                        "updated_at": "2026-01-01T00:00:00Z",
                        "company_name": slug,
                    }
                ]
            }

        monkeypatch.setattr("joborion.sources.ats_boards._fetch_greenhouse", fake_fetch)

        provider = AtsBoardsProvider({})
        result = provider.search({})

        assert result.errors == 1
        assert result.found == 1
        assert result.stored == 1
        row = conn.execute("SELECT * FROM jobs WHERE url = ?", ("https://boards.greenhouse.io/good/jobs/1",)).fetchone()
        assert row is not None

    def test_skips_pruned_companies_and_notes_attempts(self, conn, monkeypatch):
        companies = {
            "deadbeat": {"platform": "greenhouse", "slug": "deadbeat", "industries": [], "region": "global", "tags": []},
            "good": {"platform": "greenhouse", "slug": "good", "industries": [], "region": "global", "tags": []},
        }
        monkeypatch.setattr("joborion.sources.ats_boards.load_companies", lambda: companies)
        monkeypatch.setattr(
            "joborion.sources.ats_boards.load_preferences",
            lambda: {"industries": [], "sponsorship_ok": True},
        )
        monkeypatch.setattr("joborion.sources.ats_boards.get_connection", lambda: conn)
        conn.execute(
            "INSERT INTO company_yield (provider, company, pruned) VALUES ('ats_boards', 'deadbeat', 1)"
        )
        conn.commit()

        def fake_fetch(slug, params, proxy=None):
            return {
                "jobs": [
                    {
                        "id": 1,
                        "title": "Engineer",
                        "location": {"name": "Remote"},
                        "absolute_url": f"https://boards.greenhouse.io/{slug}/jobs/1",
                        "updated_at": "2026-01-01T00:00:00Z",
                        "company_name": slug,
                    }
                ]
            }

        monkeypatch.setattr("joborion.sources.ats_boards._fetch_greenhouse", fake_fetch)

        provider = AtsBoardsProvider({})
        result = provider.search({})

        assert result.companies == ["good"]
        assert result.found == 1
        row = conn.execute(
            "SELECT * FROM jobs WHERE url = ?", ("https://boards.greenhouse.io/deadbeat/jobs/1",)
        ).fetchone()
        assert row is None
        noted = conn.execute(
            "SELECT total_runs FROM company_yield WHERE provider='ats_boards' AND company='good'"
        ).fetchone()
        assert noted["total_runs"] == 1
