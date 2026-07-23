"""Tests for joborion.database — schema, CRUD, stats, migrations."""

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest
from joborion.database import (
    get_connection,
    close_connection,
    init_db,
    ensure_columns,
    get_stats,
    store_jobs,
    get_jobs_by_stage,
    record_source_run,
    get_source_reliability,
    record_validation_error,
    get_recent_validation_errors,
    get_validation_error_summary,
)


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary database and return its path."""
    db_path = tmp_path / "test.db"
    # Reset thread-local connections to avoid cross-test pollution
    close_connection(str(db_path))
    yield db_path
    close_connection(str(db_path))


@pytest.fixture
def conn(tmp_db):
    """Initialize a fresh database and return the connection."""
    c = init_db(str(tmp_db))
    yield c
    close_connection(str(tmp_db))


# ── init_db ────────────────────────────────────────────────────────────


class TestInitDb:
    def test_creates_db_file(self, tmp_db):
        init_db(str(tmp_db))
        assert tmp_db.exists()

    def test_creates_jobs_table(self, conn):
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {t[0] for t in tables}
        assert "jobs" in table_names

    def test_creates_source_stats_table(self, conn):
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {t[0] for t in tables}
        assert "source_stats" in table_names

    def test_creates_validation_errors_table(self, conn):
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {t[0] for t in tables}
        assert "validation_errors" in table_names

    def test_creates_run_history_table(self, conn):
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {t[0] for t in tables}
        assert "run_history" in table_names

    def test_idempotent(self, tmp_db):
        init_db(str(tmp_db))
        init_db(str(tmp_db))
        c = get_connection(str(tmp_db))
        count = c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        assert count == 0

    def test_creates_parent_dirs(self, tmp_path):
        nested = tmp_path / "a" / "b" / "test.db"
        init_db(str(nested))
        assert nested.exists()


# ── ensure_columns ─────────────────────────────────────────────────────


class TestEnsureColumns:
    def test_no_missing_columns(self, conn):
        added = ensure_columns(conn)
        assert added == []

    def test_detects_missing_column(self, tmp_db):
        c = get_connection(str(tmp_db))
        c.execute("CREATE TABLE IF NOT EXISTS jobs (url TEXT PRIMARY KEY)")
        c.commit()
        added = ensure_columns(c)
        assert "title" in added

    def test_returns_empty_when_current(self, conn):
        added = ensure_columns(conn)
        assert added == []


# ── store_jobs ─────────────────────────────────────────────────────────


class TestStoreJobs:
    def test_stores_jobs(self, conn):
        jobs = [
            {"url": "https://example.com/1", "title": "Engineer", "salary": "100k"},
            {"url": "https://example.com/2", "title": "Designer", "salary": "90k"},
        ]
        new, dup = store_jobs(conn, jobs, site="test", strategy="api")
        assert new == 2
        assert dup == 0

    def test_handles_duplicates(self, conn):
        jobs = [{"url": "https://example.com/1", "title": "Engineer"}]
        store_jobs(conn, jobs, site="test", strategy="api")
        new, dup = store_jobs(conn, jobs, site="test", strategy="api")
        assert new == 0
        assert dup == 1

    def test_skips_missing_url(self, conn):
        jobs = [{"title": "No URL job"}, {"url": "https://example.com/1", "title": "OK"}]
        new, dup = store_jobs(conn, jobs, site="test", strategy="api")
        assert new == 1

    def test_stores_all_fields(self, conn):
        jobs = [{
            "url": "https://example.com/1",
            "title": "Engineer",
            "salary": "150k",
            "description": "Build stuff",
            "location": "Remote",
        }]
        store_jobs(conn, jobs, site="indeed", strategy="css")
        row = conn.execute("SELECT * FROM jobs WHERE url = ?", ("https://example.com/1",)).fetchone()
        assert row["title"] == "Engineer"
        assert row["salary"] == "150k"
        assert row["site"] == "indeed"
        assert row["strategy"] == "css"
        assert row["discovered_at"] is not None


# ── get_jobs_by_stage ──────────────────────────────────────────────────


class TestGetJobsByStage:
    def test_discovered_stage(self, conn):
        jobs = [{"url": f"https://example.com/{i}", "title": f"Job {i}"} for i in range(5)]
        store_jobs(conn, jobs, site="test", strategy="api")
        result = get_jobs_by_stage(conn, stage="discovered")
        assert len(result) == 5

    def test_empty_result(self, conn):
        result = get_jobs_by_stage(conn, stage="discovered")
        assert result == []

    def test_scored_stage(self, conn):
        jobs = [{"url": "https://example.com/1", "title": "Job 1"}]
        store_jobs(conn, jobs, site="test", strategy="api")
        conn.execute("UPDATE jobs SET fit_score = 8 WHERE url = 'https://example.com/1'")
        conn.commit()
        result = get_jobs_by_stage(conn, stage="scored")
        assert len(result) == 1
        assert result[0]["fit_score"] == 8

    def test_min_score_filter(self, conn):
        jobs = [
            {"url": f"https://example.com/{i}", "title": f"Job {i}"} for i in range(5)
        ]
        store_jobs(conn, jobs, site="test", strategy="api")
        for i, url in enumerate(jobs):
            conn.execute("UPDATE jobs SET fit_score = ? WHERE url = ?", (i + 1, url["url"]))
        conn.commit()
        # Use "pending_tailor" stage which applies min_score filter
        result = get_jobs_by_stage(conn, stage="pending_tailor", min_score=4)
        assert all(r["fit_score"] >= 4 for r in result)

    def test_limit(self, conn):
        jobs = [{"url": f"https://example.com/{i}", "title": f"Job {i}"} for i in range(10)]
        store_jobs(conn, jobs, site="test", strategy="api")
        result = get_jobs_by_stage(conn, stage="discovered", limit=3)
        assert len(result) == 3

    def test_returns_dicts(self, conn):
        jobs = [{"url": "https://example.com/1", "title": "Job 1"}]
        store_jobs(conn, jobs, site="test", strategy="api")
        result = get_jobs_by_stage(conn, stage="discovered")
        assert isinstance(result[0], dict)


# ── get_stats ──────────────────────────────────────────────────────────


class TestGetStats:
    def test_empty_db(self, conn):
        stats = get_stats(conn)
        assert stats["total"] == 0
        assert stats["scored"] == 0
        assert stats["applied"] == 0

    def test_with_jobs(self, conn):
        jobs = [{"url": f"https://example.com/{i}", "title": f"Job {i}"} for i in range(3)]
        store_jobs(conn, jobs, site="test", strategy="api")
        stats = get_stats(conn)
        assert stats["total"] == 3

    def test_score_distribution(self, conn):
        jobs = [{"url": f"https://example.com/{i}", "title": f"Job {i}"} for i in range(3)]
        store_jobs(conn, jobs, site="test", strategy="api")
        conn.execute("UPDATE jobs SET fit_score = 9 WHERE url = 'https://example.com/0'")
        conn.execute("UPDATE jobs SET fit_score = 7 WHERE url = 'https://example.com/1'")
        conn.execute("UPDATE jobs SET fit_score = 7 WHERE url = 'https://example.com/2'")
        conn.commit()
        stats = get_stats(conn)
        assert stats["score_distribution"] == [(9, 1), (7, 2)]

    def test_by_site(self, conn):
        jobs = [
            {"url": "https://a.com/1", "title": "A1"},
            {"url": "https://a.com/2", "title": "A2"},
            {"url": "https://b.com/1", "title": "B1"},
        ]
        store_jobs(conn, jobs[:2], site="site_a", strategy="api")
        store_jobs(conn, jobs[2:], site="site_b", strategy="api")
        stats = get_stats(conn)
        assert len(stats["by_site"]) == 2

    def test_has_all_keys(self, conn):
        stats = get_stats(conn)
        expected_keys = {
            "total", "by_site", "pending_detail", "with_description",
            "detail_errors", "scored", "unscored", "score_distribution",
            "tailored", "untailored_eligible", "tailor_exhausted",
            "with_cover_letter", "cover_exhausted", "applied",
            "apply_errors", "ready_to_apply",
        }
        assert expected_keys.issubset(stats.keys())


# ── source_stats ───────────────────────────────────────────────────────


class TestSourceStats:
    def test_record_first_run(self, conn):
        record_source_run("indeed", success=True, jobs_found=10, conn=conn)
        row = conn.execute("SELECT * FROM source_stats WHERE source_name = 'indeed'").fetchone()
        assert row["total_runs"] == 1
        assert row["success_runs"] == 1
        assert row["total_jobs"] == 10

    def test_record_failure(self, conn):
        record_source_run("indeed", success=False, error="rate limited", conn=conn)
        row = conn.execute("SELECT * FROM source_stats WHERE source_name = 'indeed'").fetchone()
        assert row["total_runs"] == 1
        assert row["failed_runs"] == 1
        assert row["last_error"] == "rate limited"

    def test_record_multiple_runs(self, conn):
        record_source_run("indeed", success=True, jobs_found=5, conn=conn)
        record_source_run("indeed", success=True, jobs_found=8, conn=conn)
        record_source_run("indeed", success=False, error="timeout", conn=conn)
        row = conn.execute("SELECT * FROM source_stats WHERE source_name = 'indeed'").fetchone()
        assert row["total_runs"] == 3
        assert row["success_runs"] == 2
        assert row["failed_runs"] == 1
        assert row["total_jobs"] == 13

    def test_get_reliability(self, conn):
        record_source_run("indeed", success=True, jobs_found=10, conn=conn)
        record_source_run("indeed", success=True, jobs_found=8, conn=conn)
        record_source_run("indeed", success=True, jobs_found=12, conn=conn)
        record_source_run("remoteok", success=False, error="blocked", conn=conn)
        record_source_run("remoteok", success=False, error="blocked", conn=conn)
        record_source_run("remoteok", success=False, error="blocked", conn=conn)
        reliable = get_source_reliability(min_runs=3, conn=conn)
        assert len(reliable) == 2
        assert reliable[0]["source_name"] == "indeed"
        assert reliable[0]["success_rate"] == 1.0

    def test_get_reliability_min_runs(self, conn):
        record_source_run("indeed", success=True, jobs_found=5, conn=conn)
        reliable = get_source_reliability(min_runs=3, conn=conn)
        assert len(reliable) == 0


# ── validation_errors ──────────────────────────────────────────────────


class TestValidationErrors:
    def test_record_and_retrieve(self, conn):
        record_validation_error(
            stage="tailor",
            job_url="https://example.com/1",
            error_type="banned_word",
            error_message="Found: passionate",
            attempt_number=2,
            conn=conn,
        )
        errors = get_recent_validation_errors(stage="tailor", conn=conn)
        assert len(errors) == 1
        assert errors[0]["error_type"] == "banned_word"
        assert errors[0]["attempt_number"] == 2

    def test_filter_by_stage(self, conn):
        record_validation_error("tailor", None, "banned_word", "msg", conn=conn)
        record_validation_error("cover", None, "llm_leak", "msg", conn=conn)
        tailor_errors = get_recent_validation_errors(stage="tailor", conn=conn)
        assert len(tailor_errors) == 1

    def test_no_filter(self, conn):
        record_validation_error("tailor", None, "banned_word", "msg", conn=conn)
        record_validation_error("cover", None, "llm_leak", "msg", conn=conn)
        all_errors = get_recent_validation_errors(conn=conn)
        assert len(all_errors) == 2

    def test_limit(self, conn):
        for i in range(10):
            record_validation_error("tailor", None, "error", f"msg {i}", conn=conn)
        errors = get_recent_validation_errors(limit=5, conn=conn)
        assert len(errors) == 5

    def test_summary(self, conn):
        record_validation_error("tailor", None, "banned_word", "msg", conn=conn)
        record_validation_error("tailor", None, "banned_word", "msg", conn=conn)
        record_validation_error("tailor", None, "llm_leak", "msg", conn=conn)
        summary = get_validation_error_summary(stage="tailor", conn=conn)
        assert summary["banned_word"] == 2
        assert summary["llm_leak"] == 1

    def test_summary_all_stages(self, conn):
        record_validation_error("tailor", None, "banned_word", "msg", conn=conn)
        record_validation_error("cover", None, "banned_word", "msg", conn=conn)
        summary = get_validation_error_summary(conn=conn)
        assert summary["banned_word"] == 2
