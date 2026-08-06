"""Tests for joborion.sources.base — RawJob schema and shared storage."""

import time

import pytest

from joborion.database import init_db, close_connection
from joborion.sources.base import RawJob, ProviderResult, store_raw_jobs


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    close_connection(str(db_path))
    c = init_db(str(db_path))
    yield c
    close_connection(str(db_path))


class TestRawJob:
    def test_normalizes_fields(self):
        job = RawJob(
            title="  Senior Backend Engineer  ",
            company="  Acme  ",
            location=" Remote, Worldwide ",
            url=" https://example.com/job ",
            description="",
        )
        assert job.title == "Senior Backend Engineer"
        assert job.company == "Acme"
        assert job.location == "Remote, Worldwide"
        assert job.url == "https://example.com/job"
        assert job.apply_url == job.url
        assert job.is_remote is True

    def test_is_remote_derived_from_location(self):
        job = RawJob(title="Dev", location="Anywhere")
        assert job.is_remote is True

    def test_is_remote_derived_from_description(self):
        job = RawJob(title="Dev", location="", description="This is a fully remote role")
        assert job.is_remote is True

    def test_is_remote_explicit_wins(self):
        job = RawJob(title="Dev", location="New York, NY", is_remote=True)
        assert job.is_remote is True

    def test_non_remote_location(self):
        job = RawJob(title="Dev", location="Toronto, ON")
        assert job.is_remote is False

    def test_apply_url_falls_back_to_url(self):
        job = RawJob(title="Dev", url="https://x.com/job", apply_url="")
        assert job.apply_url == "https://x.com/job"


class TestStoreRawJobs:
    def test_stores_and_counts(self, conn):
        job = RawJob(
            title="Backend Engineer", company="Acme", location="Remote",
            url="https://acme.com/job", source="adzuna",
            salary_min=60000, salary_max=80000, salary_currency="$",
            salary_interval="year",
        )
        new, existing = store_raw_jobs(conn, [job])
        assert new == 1
        assert existing == 0
        row = conn.execute("SELECT * FROM jobs WHERE url = ?", (job.url,)).fetchone()
        assert row["title"] == "Backend Engineer"
        assert row["site"] == "adzuna"
        assert row["salary"] == "$60,000-$80,000/year"

    def test_duplicate_url_counts_existing(self, conn):
        jobs = [
            RawJob(title="A", url="https://x.com/job", source="remotive"),
            RawJob(title="B", url="https://x.com/job", source="remotive"),
        ]
        new, existing = store_raw_jobs(conn, jobs)
        assert new == 1
        assert existing == 1

    def test_long_description_promoted_to_full(self, conn):
        desc = "x" * 300
        job = RawJob(title="Dev", url="https://x.com/job2", description=desc, source="jobspy")
        new, _ = store_raw_jobs(conn, [job])
        assert new == 1
        row = conn.execute("SELECT * FROM jobs WHERE url = ?", (job.url,)).fetchone()
        assert row["full_description"] == desc
        assert row["detail_scraped_at"] is not None


class TestProviderResult:
    def test_defaults(self):
        r = ProviderResult(provider="adzuna")
        assert r.found == 0
        assert r.stored == 0
        assert r.errors == 0
        assert r.error is None


class TestRateLimiter:
    def test_rate_limit_respected(self):
        from joborion.sources.base import RateLimiter

        limiter = RateLimiter(min_interval=0.1)
        t0 = time.monotonic()
        limiter.wait()
        limiter.wait()
        limiter.wait()
        assert time.monotonic() - t0 >= 0.2

    def test_zero_interval_is_noop(self):
        from joborion.sources.base import RateLimiter

        limiter = RateLimiter(min_interval=0)
        t0 = time.monotonic()
        for _ in range(3):
            limiter.wait()
        assert time.monotonic() - t0 < 0.05


class TestRegistryPacing:
    def test_injects_rate_limiter_into_intent(self):
        from joborion.sources.registry import run_providers

        captured = {}

        class PacedProvider:
            name = "paced"
            cfg = {"min_request_interval": 0.01}

            def search(self, intent):
                captured["limiter"] = intent.get("rate_limiter")
                return ProviderResult(provider=self.name)

        run_providers({}, providers=[PacedProvider()])
        assert captured["limiter"] is not None

    def test_provider_calls_limiter_wait(self):
        from joborion.sources.registry import run_providers

        calls = []

        class PacedProvider:
            name = "paced"
            cfg = {}

            def search(self, intent):
                limiter = intent.get("rate_limiter")
                if limiter is not None:
                    limiter.wait()
                calls.append(len(calls))
                return ProviderResult(provider=self.name)

        run_providers({}, providers=[PacedProvider()])
        assert calls == [0]
