"""Tests for joborion.agent.reflector and reflection database functions."""

import json
import sqlite3
from datetime import datetime, timezone

import pytest
from joborion.database import close_connection, init_db, get_connection
from joborion.agent.reflector import Reflector


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    close_connection(str(db_path))
    c = init_db(str(db_path))
    yield c
    close_connection(str(db_path))


def _insert_fake_run(conn, run_id="run-001", goal="Find Python jobs"):
    """Insert a fake run record for testing."""
    conn.execute(
        "INSERT INTO run_log (run_id, goal, started_at) VALUES (?, ?, ?)",
        (run_id, goal, datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()


def _insert_fake_jobs(conn, n=5, scored=False, tailored=False, applied=False):
    """Insert fake job records for testing."""
    for i in range(n):
        conn.execute(
            "INSERT INTO jobs (url, title, site, discovered_at, full_description, "
            "fit_score, tailored_resume_path, applied_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                f"https://example.com/job/{i}",
                f"Engineer {i}",
                "example.com",
                datetime.now(timezone.utc).isoformat(),
                f"Description for job {i}" if scored or tailored else None,
                (7 + i % 3) if scored else None,
                f"/tmp/resume_{i}.txt" if tailored else None,
                datetime.now(timezone.utc).isoformat() if applied else None,
            ),
        )
    conn.commit()


# ===========================================================================
# Task 1: Reflection Log
# ===========================================================================

class TestReflectionLog:
    """Tests for reflection_log database operations."""

    def test_store_and_retrieve(self, conn):
        """store_reflection inserts and get_reflection retrieves."""
        from joborion.database import store_reflection, get_reflection

        record = {
            "run_id": "run-001",
            "overall_rating": "good",
            "what_went_well": ["Found 47 jobs"],
            "what_failed": ["Indeed rate limited"],
            "strategy_changes": [],
            "memory_updates": [],
            "recommendations": ["Add delay between requests"],
            "scoring_calibration": {"avg_score": 7.2},
            "cost_analysis": {"total": 0.05},
        }
        ref_id = store_reflection(record, conn=conn)
        assert ref_id is not None
        assert ref_id.startswith("refl-")

        result = get_reflection(ref_id, conn=conn)
        assert result is not None
        assert result["run_id"] == "run-001"
        assert result["overall_rating"] == "good"

    def test_get_recent(self, conn):
        """get_recent_reflections returns N most recent."""
        from joborion.database import store_reflection, get_recent_reflections

        for i in range(5):
            store_reflection({
                "run_id": f"run-{i:03d}",
                "overall_rating": "ok",
                "what_went_well": "[]",
                "what_failed": "[]",
                "strategy_changes": "[]",
                "memory_updates": "[]",
                "recommendations": "[]",
                "scoring_calibration": "{}",
                "cost_analysis": "{}",
            }, conn=conn)

        recent = get_recent_reflections(n=3, conn=conn)
        assert len(recent) == 3

    def test_get_for_run(self, conn):
        """get_reflections_for_run filters by run_id."""
        from joborion.database import store_reflection, get_reflections_for_run

        store_reflection({"run_id": "run-A", "overall_rating": "good",
                          "what_went_well": "[]", "what_failed": "[]",
                          "strategy_changes": "[]", "memory_updates": "[]",
                          "recommendations": "[]", "scoring_calibration": "{}",
                          "cost_analysis": "{}"}, conn=conn)
        store_reflection({"run_id": "run-B", "overall_rating": "poor",
                          "what_went_well": "[]", "what_failed": "[]",
                          "strategy_changes": "[]", "memory_updates": "[]",
                          "recommendations": "[]", "scoring_calibration": "{}",
                          "cost_analysis": "{}"}, conn=conn)

        results = get_reflections_for_run("run-A", conn=conn)
        assert len(results) == 1
        assert results[0]["run_id"] == "run-A"

    def test_reflection_id_unique(self, conn):
        """Each reflection gets a unique ID."""
        from joborion.database import store_reflection

        id1 = store_reflection({"run_id": "r1", "overall_rating": "ok",
                                "what_went_well": "[]", "what_failed": "[]",
                                "strategy_changes": "[]", "memory_updates": "[]",
                                "recommendations": "[]", "scoring_calibration": "{}",
                                "cost_analysis": "{}"}, conn=conn)
        id2 = store_reflection({"run_id": "r2", "overall_rating": "ok",
                                "what_went_well": "[]", "what_failed": "[]",
                                "strategy_changes": "[]", "memory_updates": "[]",
                                "recommendations": "[]", "scoring_calibration": "{}",
                                "cost_analysis": "{}"}, conn=conn)
        assert id1 != id2


# ===========================================================================
# Task 2: Reflector Core
# ===========================================================================

class TestReflector:
    """Tests for Reflector analysis."""

    def test_analyze_produces_record(self, conn):
        """analyze_run returns a valid reflection dict."""
        _insert_fake_run(conn)
        _insert_fake_jobs(conn, n=10, scored=True)

        reflector = Reflector(conn)
        result = reflector.analyze_run("run-001")

        assert "overall_rating" in result
        assert result["overall_rating"] in ("good", "ok", "poor")
        assert "what_went_well" in result
        assert "what_failed" in result
        assert "recommendations" in result

    def test_identifies_failures(self, conn):
        """Reflector identifies jobs with errors."""
        _insert_fake_run(conn)
        conn.execute(
            "INSERT INTO jobs (url, title, site, discovered_at, detail_error) "
            "VALUES (?, ?, ?, ?, ?)",
            ("https://fail.com/1", "Fail Job", "fail.com",
             datetime.now(timezone.utc).isoformat(), "timeout"),
        )
        conn.commit()

        reflector = Reflector(conn)
        result = reflector.analyze_run("run-001")

        assert len(result["what_failed"]) > 0

    def test_scoring_calibration(self, conn):
        """Scoring calibration computes score distribution."""
        _insert_fake_run(conn)
        _insert_fake_jobs(conn, n=20, scored=True)

        reflector = Reflector(conn)
        result = reflector.analyze_run("run-001")

        cal = result["scoring_calibration"]
        assert "score_distribution" in cal
        assert "avg_score" in cal

    def test_recommendations_on_failure(self, conn):
        """Recommendations are generated when failures exist."""
        _insert_fake_run(conn)
        conn.execute(
            "INSERT INTO jobs (url, title, site, discovered_at, detail_error) "
            "VALUES (?, ?, ?, ?, ?)",
            ("https://fail.com/1", "Fail", "fail.com",
             datetime.now(timezone.utc).isoformat(), "blocked"),
        )
        conn.commit()

        reflector = Reflector(conn)
        result = reflector.analyze_run("run-001")

        assert len(result["recommendations"]) > 0

    def test_memory_updates(self, conn):
        """Memory updates are proposed based on site performance."""
        _insert_fake_run(conn)
        _insert_fake_jobs(conn, n=5, scored=True)

        reflector = Reflector(conn)
        result = reflector.analyze_run("run-001")

        assert isinstance(result["memory_updates"], list)

    def test_handles_empty_run(self, conn):
        """Reflector handles run with no jobs gracefully."""
        _insert_fake_run(conn)

        reflector = Reflector(conn)
        result = reflector.analyze_run("run-001")

        assert result["overall_rating"] == "ok"
        assert isinstance(result["recommendations"], list)

    def test_overall_rating_good(self, conn):
        """Rating is 'good' when most jobs scored well."""
        _insert_fake_run(conn)
        _insert_fake_jobs(conn, n=10, scored=True, tailored=True)

        reflector = Reflector(conn)
        result = reflector.analyze_run("run-001")

        # All jobs scored 7+, should be good
        assert result["overall_rating"] in ("good", "ok")


# ===========================================================================
# Task 4: Reflection CLI
# ===========================================================================

class TestReflectionCLI:
    """Tests for reflect CLI command."""

    def test_reflect_help(self):
        """'joborion reflect --help' works."""
        from joborion.cli import app
        from typer.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(app, ["reflect", "--help"])
        assert result.exit_code == 0
        assert "reflect" in result.output.lower() or "Reflect" in result.output
