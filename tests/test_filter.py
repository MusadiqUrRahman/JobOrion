"""Tests for joborion.sourcing.filter — the relevance gate (LLM-free)."""

import pytest

from joborion.database import init_db, close_connection
from joborion.sources.base import RawJob, store_raw_jobs
from joborion.sourcing.filter import (
    apply_relevance_gate,
    evaluate,
    location_matches,
    title_matches,
)
from joborion.sourcing.normalize import normalize_job


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    close_connection(str(db_path))
    c = init_db(str(db_path))
    yield c
    close_connection(str(db_path))


def _job_row(job: RawJob) -> dict:
    return {
        "url": job.url,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "description": job.description,
        "salary": job.salary_text(),
        "site": job.source,
    }


class TestEvaluate:
    def test_remote_only_drops_onsite(self):
        job = RawJob(title="Dev", location="Toronto, ON", url="https://x.com/1")
        norm = normalize_job(_job_row(job))
        decision = evaluate(norm, {"remote_only": True})
        assert not decision.passed
        assert "arrangement" in decision.reasons

    def test_remote_only_passes_remote(self):
        job = RawJob(title="Dev", location="Remote", url="https://x.com/2")
        norm = normalize_job(_job_row(job))
        assert evaluate(norm, {"remote_only": True}).passed

    def test_no_restriction_passes_everything(self):
        job = RawJob(title="Dev", location="Toronto, ON", url="https://x.com/3")
        norm = normalize_job(_job_row(job))
        assert evaluate(norm, {}).passed

    def test_drops_bangkok_remote_for_restricted_locations(self):
        # The core plan scenario: Thailand-remote job must NOT pass when the
        # user restricted locations (even though its text contains "Remote").
        job = RawJob(
            title="Software Engineer", company="Acme", location="Bangkok, Thailand",
            description="Remote role", url="https://x.com/4",
        )
        norm = normalize_job(_job_row(job))
        assert norm.is_remote is True
        decision = evaluate(norm, {"locations": ["Canada"]})
        assert not decision.passed
        assert "location" in decision.reasons

    def test_passes_matching_country(self):
        job = RawJob(title="Dev", location="Berlin, Germany", url="https://x.com/5")
        norm = normalize_job(_job_row(job))
        assert evaluate(norm, {"locations": ["Germany"]}).passed

    def test_passes_matching_city(self):
        job = RawJob(title="Dev", location="Berlin, Germany", url="https://x.com/6")
        norm = normalize_job(_job_row(job))
        assert evaluate(norm, {"locations": ["Berlin"]}).passed

    def test_worldwide_ignores_location_restriction(self):
        job = RawJob(title="Dev", location="Bangkok, Thailand", url="https://x.com/7")
        norm = normalize_job(_job_row(job))
        assert evaluate(norm, {"locations": ["worldwide"]}).passed

    def test_drops_below_min_salary(self):
        job = RawJob(
            title="Dev", location="Remote", url="https://x.com/8",
            salary_min=50000, salary_max=60000, salary_currency="USD", salary_interval="annual",
        )
        norm = normalize_job(_job_row(job))
        decision = evaluate(norm, {"min_salary": 80000})
        assert not decision.passed
        assert "salary" in decision.reasons

    def test_passes_at_or_above_min_salary(self):
        job = RawJob(
            title="Dev", location="Remote", url="https://x.com/9",
            salary_min=90000, salary_max=120000, salary_currency="USD", salary_interval="annual",
        )
        norm = normalize_job(_job_row(job))
        assert evaluate(norm, {"min_salary": 80000}).passed

    def test_unknown_salary_passes_salary_gate(self):
        job = RawJob(title="Dev", location="Remote", url="https://x.com/10")
        norm = normalize_job(_job_row(job))
        assert evaluate(norm, {"min_salary": 80000}).passed

    def test_drops_restricted_job_type(self):
        job = RawJob(title="Part-time Barista", location="Remote", url="https://x.com/11")
        norm = normalize_job(_job_row(job))
        decision = evaluate(norm, {"job_types": ["fulltime"]})
        assert not decision.passed
        assert "job_type" in decision.reasons

    def test_passes_matching_job_type(self):
        job = RawJob(title="Part-time Barista", location="Remote", url="https://x.com/12")
        norm = normalize_job(_job_row(job))
        assert evaluate(norm, {"job_types": ["parttime"]}).passed

    def test_drops_wrong_seniority(self):
        job = RawJob(title="Junior Developer", location="Remote", url="https://x.com/13")
        norm = normalize_job(_job_row(job))
        decision = evaluate(norm, {"seniority": ["senior"]})
        assert not decision.passed
        assert "seniority" in decision.reasons

    def test_passes_matching_seniority(self):
        job = RawJob(title="Senior Developer", location="Remote", url="https://x.com/14")
        norm = normalize_job(_job_row(job))
        assert evaluate(norm, {"seniority": ["mid", "senior"]}).passed

    def test_drops_unrelated_title(self):
        job = RawJob(title="Receptionist", location="Remote", url="https://x.com/15")
        norm = normalize_job(_job_row(job))
        decision = evaluate(norm, {"keywords": ["Software Engineer", "python"]})
        assert not decision.passed
        assert "title" in decision.reasons

    def test_passes_related_title_via_skill_term(self):
        job = RawJob(title="Python Developer", location="Remote", url="https://x.com/16")
        norm = normalize_job(_job_row(job))
        assert evaluate(norm, {"keywords": ["Software Engineer", "python"]}).passed

    def test_passes_related_title_via_fuzzy_role(self):
        job = RawJob(title="Senior Software Engineer", location="Remote", url="https://x.com/17")
        norm = normalize_job(_job_row(job))
        assert evaluate(norm, {"keywords": ["software engineer"]}).passed

    def test_no_keywords_skips_title_gate(self):
        job = RawJob(title="Receptionist", location="Remote", url="https://x.com/18")
        norm = normalize_job(_job_row(job))
        assert evaluate(norm, {}).passed


class TestLocationMatches:
    def test_country_code_match(self):
        job = RawJob(title="Dev", location="Paris, France", url="https://x.com/1")
        norm = normalize_job(_job_row(job))
        assert location_matches(norm, ["France"])

    def test_city_fuzzy_match(self):
        job = RawJob(title="Dev", location="San Francisco, CA, US", url="https://x.com/2")
        norm = normalize_job(_job_row(job))
        assert location_matches(norm, ["San Francisco"])

    def test_mismatch(self):
        job = RawJob(title="Dev", location="Berlin, Germany", url="https://x.com/3")
        norm = normalize_job(_job_row(job))
        assert not location_matches(norm, ["Canada"])


class TestTitleMatches:
    def test_exact_role(self):
        assert title_matches("Backend Engineer", ["backend engineer"])

    def test_seniority_insensitive(self):
        assert title_matches("Senior Backend Engineer", ["backend engineer"])

    def test_skill_token(self):
        assert title_matches("Python Developer", ["software engineer", "python"])

    def test_no_match(self):
        assert not title_matches("Receptionist", ["software engineer", "python"])


class TestApplyRelevanceGate:
    def test_passes_store_structured_fields(self, conn):
        store_raw_jobs(
            conn,
            [
                RawJob(
                    title="Senior Backend Engineer", company="Acme", location="Remote, UK",
                    description="Fully remote", salary_min=80000, salary_max=100000,
                    salary_currency="USD", salary_interval="annual",
                    url="https://x.com/1", source="jobspy",
                )
            ],
        )
        summary = apply_relevance_gate(conn, {"locations": ["worldwide"]})
        assert summary["passed"] == 1
        row = conn.execute("SELECT * FROM jobs WHERE url = 'https://x.com/1'").fetchone()
        assert row["is_remote"] == 1
        assert row["country"] == "GB"
        assert row["job_type"] is None
        assert row["seniority"] == "senior"
        assert row["salary_min"] == 80000.0
        assert row["salary_max"] == 100000.0
        assert row["source_provider"] == "jobspy"

    def test_dropped_jobs_deleted(self, conn):
        store_raw_jobs(
            conn,
            [
                RawJob(title="Receptionist", location="Bangkok, Thailand", url="https://x.com/2"),
                RawJob(title="Backend Engineer", location="Vancouver, Canada", url="https://x.com/3"),
            ],
        )
        summary = apply_relevance_gate(conn, {"locations": ["Canada"], "keywords": ["software engineer"]})
        assert summary["passed"] == 1
        assert summary["dropped"] == 1
        assert "location" in summary["reasons"] or "title" in summary["reasons"]
        remaining = conn.execute("SELECT url FROM jobs").fetchall()
        assert [r[0] for r in remaining] == ["https://x.com/3"]

    def test_idempotent_second_pass(self, conn):
        store_raw_jobs(
            conn,
            [RawJob(title="Backend Engineer", location="Remote", url="https://x.com/4")],
        )
        first = apply_relevance_gate(conn, {})
        second = apply_relevance_gate(conn, {})
        assert first["processed"] == 1
        assert second["processed"] == 0
        assert second["passed"] == 0

    def test_unknown_provider_grouped(self, conn):
        store_raw_jobs(conn, [RawJob(title="Dev", location="Remote", url="https://x.com/5")])
        summary = apply_relevance_gate(conn, {})
        assert summary["by_provider"]["unknown"]["passed"] == 1

    def test_dedupes_across_providers(self, conn):
        # Same role at the same company found by two providers with different
        # URLs must be kept once, not twice.
        store_raw_jobs(
            conn,
            [
                RawJob(
                    title="Senior Software Engineer", company="Stripe", location="Remote",
                    url="https://stripe.greenhouse.io/jobs/1", source="ats_boards",
                ),
                RawJob(
                    title="Software Engineer (Senior)", company="Stripe, LLC", location="Remote",
                    url="https://www.linkedin.com/jobs/2", source="jobspy",
                ),
            ],
        )
        summary = apply_relevance_gate(conn, {"locations": ["worldwide"]})
        assert summary["passed"] == 1
        assert summary["dropped"] == 1
        assert summary["reasons"].get("duplicate") == 1
        remaining = conn.execute("SELECT url FROM jobs").fetchall()
        assert len(remaining) == 1

    def test_no_dedup_without_company_match(self, conn):
        store_raw_jobs(
            conn,
            [
                RawJob(title="Senior Software Engineer", company="Stripe", location="Remote",
                       url="https://x.com/1", source="ats_boards"),
                RawJob(title="Senior Software Engineer", company="Shopify", location="Remote",
                       url="https://x.com/2", source="jobspy"),
            ],
        )
        summary = apply_relevance_gate(conn, {})
        assert summary["passed"] == 2
        assert summary["dropped"] == 0

    def test_no_dedup_when_disabled(self, conn):
        store_raw_jobs(
            conn,
            [
                RawJob(title="Senior Software Engineer", company="Stripe", location="Remote",
                       url="https://x.com/1", source="ats_boards"),
                RawJob(title="Senior Software Engineer", company="Stripe", location="Remote",
                       url="https://x.com/2", source="jobspy"),
            ],
        )
        summary = apply_relevance_gate(conn, {}, dedup=False)
        assert summary["passed"] == 2
