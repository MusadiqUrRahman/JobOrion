"""Tests for joborion.sources.remote_boards."""

import pytest

from joborion.database import init_db, close_connection
from joborion.sources.remote_boards import (
    RemoteBoardsProvider,
    parse_arbeitnow,
    parse_hn,
    parse_jobicy,
    parse_remotive,
    parse_remoteok,
    parse_wwr,
)


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    close_connection(str(db_path))
    c = init_db(str(db_path))
    yield c
    close_connection(str(db_path))


class TestRemoteBoards:
    def test_remotive_parses(self):
        payload = [
            {
                "title": "Senior Python Developer",
                "company_name": "Acme Corp",
                "candidate_required_location": "Worldwide",
                "url": "https://remotive.com/remote-jobs/software-dev/senior-python-developer",
                "description": "Build backend services with Python.",
                "salary": "$60k - $80k",
                "job_type": "full_time",
                "date": "2025-07-01T00:00:00Z",
            },
            {
                "title": "Frontend Engineer",
                "company_name": "Globex",
                "candidate_required_location": "Remote - Europe",
                "url": "https://remotive.com/remote-jobs/software-dev/frontend-engineer",
                "description": "React and TypeScript.",
                "salary": "Competitive",
                "job_type": "full_time",
                "date": "2025-07-02T00:00:00Z",
            },
        ]
        jobs = parse_remotive(payload)
        assert len(jobs) == 2
        assert jobs[0].title == "Senior Python Developer"
        assert jobs[0].company == "Acme Corp"
        assert jobs[0].location == "Worldwide"
        assert jobs[0].salary_min == 60000.0
        assert jobs[0].salary_max == 80000.0
        assert jobs[0].job_type == "full_time"
        assert jobs[0].posted_at == "2025-07-01T00:00:00Z"
        assert jobs[0].url == "https://remotive.com/remote-jobs/software-dev/senior-python-developer"
        assert jobs[0].is_remote is True
        assert jobs[1].salary_min is None
        assert jobs[1].salary_max is None

    def test_remoteok_parses(self):
        payload = [
            {"_metadata": {"count": 2, "page": 1}},
            {
                "position": "Backend Engineer",
                "company": "Initech",
                "location": "Remote",
                "description": "Go and Postgres",
                "slug": "backend-engineer-initech-001",
                "salary_min": 90000,
                "salary_max": 130000,
                "salary_currency": "USD",
                "apply_url": "https://remoteok.com/l/1234",
            },
            {
                "position": "DevOps Engineer",
                "company": "Umbrella Corp",
                "location": "Anywhere",
                "description": "Kubernetes",
                "slug": "devops-engineer-umbrella-002",
            },
        ]
        jobs = parse_remoteok(payload)
        assert len(jobs) == 2
        assert jobs[0].title == "Backend Engineer"
        assert jobs[0].company == "Initech"
        assert jobs[0].url == "https://remoteok.com/remote-jobs/backend-engineer-initech-001"
        assert jobs[0].apply_url == "https://remoteok.com/l/1234"
        assert jobs[0].salary_min == 90000.0
        assert jobs[0].salary_max == 130000.0
        assert jobs[0].salary_currency == "USD"
        assert jobs[0].is_remote is True
        assert jobs[1].title == "DevOps Engineer"
        assert jobs[1].apply_url == jobs[1].url

    def test_wwr_parses(self):
        payload = [
            {
                "title": "Full Stack Developer",
                "company_name": "Stark Industries",
                "location": "Anywhere in the World",
                "url": "https://weworkremotely.com/remote-jobs/full-stack-developer",
                "apply_url": "https://apply.stark.example/x",
                "description_html": "<div><h3>About</h3><p>Join our team &amp; build great things.</p><ul><li>Remote first</li></ul></div>",
                "published_at": "2025-07-10 12:00:00 UTC",
            },
            {
                "title": "Product Designer",
                "company_name": "Wayne Enterprises",
                "location": "Remote",
                "url": "https://weworkremotely.com/remote-jobs/product-designer",
                "description_html": "<p>Design delightful products.</p>",
                "published_at": "2025-07-11",
            },
        ]
        jobs = parse_wwr(payload)
        assert len(jobs) == 2
        assert jobs[0].title == "Full Stack Developer"
        assert jobs[0].company == "Stark Industries"
        assert jobs[0].location == "Anywhere in the World"
        assert jobs[0].apply_url == "https://apply.stark.example/x"
        assert "Join our team & build great things." in jobs[0].description
        assert "<" not in jobs[0].description
        assert "&amp;" not in jobs[0].description
        assert jobs[0].posted_at == "2025-07-10 12:00:00 UTC"
        assert jobs[0].is_remote is True
        assert jobs[1].apply_url == jobs[1].url

    def test_jobicy_parses(self):
        payload = [
            {
                "jobTitle": "Remote Marketing Manager",
                "companyName": "Buffer",
                "jobGeo": "Anywhere",
                "jobDescription": "Own the marketing roadmap.",
                "url": "https://jobicy.com/jobs/marketing-manager-1234",
                "annualSalaryMin": 70000,
                "annualSalaryMax": 95000,
                "salaryCurrency": "USD",
                "jobType": "full-time",
                "jobLevel": "mid-level",
                "pubDate": "2025-06-20T10:00:00.000Z",
            },
            {
                "jobTitle": "Support Engineer",
                "companyName": "Zendesk",
                "jobGeo": "Remote - US",
                "jobDescription": "Help customers.",
                "url": "https://jobicy.com/jobs/support-engineer-5678",
                "jobType": "full-time",
                "jobLevel": "entry-level",
                "pubDate": "2025-06-21T00:00:00.000Z",
            },
        ]
        jobs = parse_jobicy(payload)
        assert len(jobs) == 2
        assert jobs[0].title == "Remote Marketing Manager"
        assert jobs[0].company == "Buffer"
        assert jobs[0].location == "Anywhere"
        assert jobs[0].salary_min == 70000.0
        assert jobs[0].salary_max == 95000.0
        assert jobs[0].salary_currency == "USD"
        assert jobs[0].salary_interval == "year"
        assert jobs[0].job_type == "full-time"
        assert jobs[0].seniority == "mid-level"
        assert jobs[0].posted_at == "2025-06-20T10:00:00.000Z"
        assert jobs[0].is_remote is True
        assert jobs[1].salary_min is None
        assert jobs[1].salary_max is None

    def test_arbeitnow_parses(self):
        payload = [
            {
                "title": "Senior Go Engineer",
                "company_name": "Grafana Labs",
                "location": "Remote",
                "url": "https://www.arbeitnow.com/job/1234",
                "description": "Distributed systems with Go.",
                "salary": "€70k - €90k",
                "job_type": "Full-time",
                "experience_level": "Senior",
                "published_at": "2025-07-05",
            },
            {
                "title": "Data Engineer",
                "company_name": "Thoughtworks",
                "location": "Europe",
                "url": "https://www.arbeitnow.com/job/5678",
                "description": "Build data pipelines.",
                "salary": "",
                "job_type": "Full-time",
                "experience_level": "Mid-level",
                "published_at": "2025-07-06",
            },
        ]
        jobs = parse_arbeitnow(payload)
        assert len(jobs) == 2
        assert jobs[0].title == "Senior Go Engineer"
        assert jobs[0].company == "Grafana Labs"
        assert jobs[0].location == "Remote"
        assert jobs[0].salary_min == 70000.0
        assert jobs[0].salary_max == 90000.0
        assert jobs[0].job_type == "Full-time"
        assert jobs[0].seniority == "Senior"
        assert jobs[0].posted_at == "2025-07-05"
        assert jobs[0].is_remote is True
        assert jobs[1].salary_min is None
        assert jobs[1].salary_max is None

    def test_hn_parses(self):
        children = [
            {
                "id": 123456,
                "text": "<p>Acme Corp | Senior Backend Engineer (Remote)</p>\n<p>Build distributed systems with Python &amp; Go.</p>",
            },
            {"id": 123457, "text": "<p>Wayne Enterprises – Data Scientist</p>"},
            {"id": 123458, "text": ""},
            {"id": 123459},
        ]
        jobs = parse_hn(children)
        assert len(jobs) == 2
        assert jobs[0].title == "Acme Corp | Senior Backend Engineer (Remote)"
        assert jobs[0].company == "Acme Corp"
        assert jobs[0].url == "https://news.ycombinator.com/item?id=123456"
        assert "Build distributed systems with Python & Go." in jobs[0].description
        assert jobs[0].is_remote is True
        assert jobs[1].title == "Wayne Enterprises – Data Scientist"
        assert jobs[1].company == "Wayne Enterprises"
        assert jobs[1].url == "https://news.ycombinator.com/item?id=123457"

    def test_search_aggregates_and_stores(self, conn, monkeypatch):
        monkeypatch.setattr("joborion.sources.remote_boards.get_connection", lambda: conn)
        monkeypatch.setattr(
            "joborion.sources.remote_boards.load_search_config",
            lambda: {"queries": [{"query": "python developer", "tier": 1}]},
        )
        provider = RemoteBoardsProvider({
            "sources": ["remotive", "remoteok", "wwr", "jobicy", "arbeitnow", "hn"],
        })
        payloads = {
            "_fetch_remotive": [{
                "title": "R1", "company_name": "AC", "candidate_required_location": "Worldwide",
                "url": "https://remotive.com/r1", "description": "d", "salary": "",
                "job_type": "full_time", "date": "2025-01-01",
            }],
            "_fetch_remoteok": [{
                "position": "OK1", "company": "OK Co", "location": "Remote",
                "slug": "ok1", "description": "d",
            }],
            "_fetch_wwr": [{
                "title": "W1", "company_name": "WW", "location": "Anywhere",
                "url": "https://wwr.co/w1", "description_html": "<p>d</p>",
                "published_at": "2025-01-01",
            }],
            "_fetch_jobicy": [{
                "jobTitle": "J1", "companyName": "JC", "jobGeo": "Anywhere",
                "url": "https://jobicy.com/j1", "jobDescription": "d", "pubDate": "2025-01-01",
            }],
            "_fetch_arbeitnow": [{
                "title": "A1", "company_name": "AB", "location": "Remote",
                "url": "https://arbeitnow.com/a1", "description": "d", "salary": "",
                "published_at": "2025-01-01",
            }],
            "_fetch_hn": [{"id": 1, "text": "<p>HN Co | Role</p>"}],
        }
        for name, payload in payloads.items():
            monkeypatch.setattr(
                f"joborion.sources.remote_boards.{name}",
                lambda client, term, payload=payload: payload,
            )

        result = provider.search({"mode": "remote"})

        assert result.provider == "remote_boards"
        assert result.found == 6
        assert result.stored == 6
        assert result.errors == 0
        assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 6

    def test_source_error_does_not_abort(self, conn, monkeypatch):
        monkeypatch.setattr("joborion.sources.remote_boards.get_connection", lambda: conn)
        monkeypatch.setattr(
            "joborion.sources.remote_boards.load_search_config",
            lambda: {"queries": [{"query": "python developer", "tier": 2}]},
        )
        provider = RemoteBoardsProvider({"sources": ["remotive", "remoteok"]})

        def boom(client, term):
            raise RuntimeError("network down")

        monkeypatch.setattr("joborion.sources.remote_boards._fetch_remotive", boom)
        monkeypatch.setattr(
            "joborion.sources.remote_boards._fetch_remoteok",
            lambda client, term: [{
                "position": "OK1", "company": "OK", "location": "Remote",
                "slug": "ok1", "description": "d",
            }],
        )

        result = provider.search({"mode": "remote"})

        assert result.errors == 1
        assert result.found == 1
        assert result.stored == 1
