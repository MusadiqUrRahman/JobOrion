"""Tests for Reflector — post-run analysis and insights."""

import sqlite3

import pytest
from joborion.agent.reflector import Reflector


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    c = sqlite3.connect(str(db_path))
    c.execute("""
        CREATE TABLE run_log (
            run_id TEXT PRIMARY KEY,
            goal TEXT,
            status TEXT,
            started_at TEXT,
            completed_at TEXT,
            total_cost REAL,
            stages_completed TEXT,
            error_count INTEGER
        )
    """)
    c.execute("""
        CREATE TABLE jobs (
            url TEXT PRIMARY KEY,
            title TEXT,
            site TEXT,
            full_description TEXT,
            fit_score REAL,
            score_reasoning TEXT,
            scored_at TEXT,
            tailored_resume_path TEXT,
            cover_letter_path TEXT,
            detail_error TEXT,
            applied_at TEXT,
            apply_status TEXT,
            discovered_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE cost_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT,
            tool TEXT,
            action TEXT,
            tokens_in INTEGER,
            tokens_out INTEGER,
            cost_usd REAL,
            created_at TEXT
        )
    """)
    c.commit()
    yield c
    c.close()


class TestReflectorEmpty:
    def test_analyze_run_no_data(self, conn):
        conn.execute(
            "INSERT INTO run_log (run_id, goal, status, started_at) VALUES (?, ?, ?, ?)",
            ("run-001", "Find jobs", "completed", "2025-01-01T00:00:00"),
        )
        conn.commit()
        reflector = Reflector(conn)
        result = reflector.analyze_run("run-001")
        assert result["run_id"] == "run-001"
        assert result["overall_rating"] in ("ok", "good")
        assert isinstance(result["what_went_well"], list)
        assert isinstance(result["what_failed"], list)
        assert isinstance(result["recommendations"], list)

    def test_analyze_run_nonexistent(self, conn):
        reflector = Reflector(conn)
        result = reflector.analyze_run("nonexistent")
        assert result["overall_rating"] == "ok"
        assert result["what_went_well"] == ["Run completed without errors"]


class TestReflectorOutcomes:
    def test_analyze_with_enriched_jobs(self, conn):
        conn.execute(
            "INSERT INTO run_log (run_id, goal, status, started_at) VALUES (?, ?, ?, ?)",
            ("run-002", "Find jobs", "completed", "2025-01-01T00:00:00"),
        )
        conn.execute(
            "INSERT INTO jobs (url, title, site, full_description, fit_score, discovered_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("http://example.com/1", "Dev", "linkedin", "Full desc", 8, "2025-01-01T00:00:01"),
        )
        conn.commit()
        reflector = Reflector(conn)
        result = reflector.analyze_run("run-002")
        well = " ".join(result["what_went_well"])
        assert "1" in well or "jobs" in well.lower()

    def test_analyze_with_tailored_jobs(self, conn):
        conn.execute(
            "INSERT INTO run_log (run_id, goal, status, started_at) VALUES (?, ?, ?, ?)",
            ("run-003", "Find jobs", "completed", "2025-01-01T00:00:00"),
        )
        conn.execute(
            "INSERT INTO jobs (url, title, site, full_description, fit_score, "
            "tailored_resume_path, discovered_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("http://example.com/1", "Dev", "linkedin", "desc", 8, "/tmp/resume.pdf", "2025-01-01T00:00:01"),
        )
        conn.commit()
        reflector = Reflector(conn)
        result = reflector.analyze_run("run-003")
        well = " ".join(result["what_went_well"])
        assert "tailor" in well.lower() or "resume" in well.lower()


class TestReflectorFailures:
    def test_identifies_extraction_errors(self, conn):
        conn.execute(
            "INSERT INTO run_log (run_id, goal, status, started_at) VALUES (?, ?, ?, ?)",
            ("run-004", "Find jobs", "completed", "2025-01-01T00:00:00"),
        )
        conn.execute(
            "INSERT INTO jobs (url, title, site, detail_error, discovered_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("http://example.com/1", "Dev", "linkedin", "timeout", "2025-01-01T00:00:01"),
        )
        conn.commit()
        reflector = Reflector(conn)
        result = reflector.analyze_run("run-004")
        assert len(result["what_failed"]) > 0
        assert any("extraction" in f.lower() or "timeout" in f.lower() for f in result["what_failed"])

    def test_identifies_unscored_jobs(self, conn):
        conn.execute(
            "INSERT INTO run_log (run_id, goal, status, started_at) VALUES (?, ?, ?, ?)",
            ("run-005", "Find jobs", "completed", "2025-01-01T00:00:00"),
        )
        conn.execute(
            "INSERT INTO jobs (url, title, site, full_description, discovered_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("http://example.com/1", "Dev", "linkedin", "desc", "2025-01-01T00:00:01"),
        )
        conn.commit()
        reflector = Reflector(conn)
        result = reflector.analyze_run("run-005")
        assert len(result["what_failed"]) > 0


class TestReflectorCalibration:
    def test_scoring_calibration_healthy(self, conn):
        conn.execute(
            "INSERT INTO run_log (run_id, goal, status, started_at) VALUES (?, ?, ?, ?)",
            ("run-006", "Find jobs", "completed", "2025-01-01T00:00:00"),
        )
        for i, score in enumerate([5, 6, 7, 8, 9]):
            conn.execute(
                "INSERT INTO jobs (url, title, site, fit_score, discovered_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (f"http://example.com/{i}", f"Job {i}", "linkedin", score, "2025-01-01T00:00:01"),
            )
        conn.commit()
        reflector = Reflector(conn)
        result = reflector.analyze_run("run-006")
        cal = result["scoring_calibration"]
        assert cal["avg_score"] > 0
        assert cal["score_range"] > 0
        assert "healthy" in cal["assessment"].lower() or cal["score_range"] > 2

    def test_scoring_calibration_narrow(self, conn):
        conn.execute(
            "INSERT INTO run_log (run_id, goal, status, started_at) VALUES (?, ?, ?, ?)",
            ("run-007", "Find jobs", "completed", "2025-01-01T00:00:00"),
        )
        for i in range(5):
            conn.execute(
                "INSERT INTO jobs (url, title, site, fit_score, discovered_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (f"http://example.com/{i}", f"Job {i}", "linkedin", 7, "2025-01-01T00:00:01"),
            )
        conn.commit()
        reflector = Reflector(conn)
        result = reflector.analyze_run("run-007")
        cal = result["scoring_calibration"]
        assert cal["score_range"] <= 2
        assert "tightly" in cal["assessment"].lower() or "narrow" in cal["assessment"].lower()

    def test_scoring_calibration_high(self, conn):
        conn.execute(
            "INSERT INTO run_log (run_id, goal, status, started_at) VALUES (?, ?, ?, ?)",
            ("run-008", "Find jobs", "completed", "2025-01-01T00:00:00"),
        )
        for i in range(5):
            conn.execute(
                "INSERT INTO jobs (url, title, site, fit_score, discovered_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (f"http://example.com/{i}", f"Job {i}", "linkedin", 9, "2025-01-01T00:00:01"),
            )
        conn.commit()
        reflector = Reflector(conn)
        result = reflector.analyze_run("run-008")
        cal = result["scoring_calibration"]
        assert cal["avg_score"] > 8


class TestReflectorCostAnalysis:
    def test_cost_analysis_with_entries(self, conn):
        conn.execute(
            "INSERT INTO run_log (run_id, goal, status, started_at) VALUES (?, ?, ?, ?)",
            ("run-009", "Find jobs", "completed", "2025-01-01T00:00:00"),
        )
        conn.execute(
            "INSERT INTO cost_ledger (run_id, tool, cost_usd) VALUES (?, ?, ?)",
            ("run-009", "search", 0.001),
        )
        conn.execute(
            "INSERT INTO cost_ledger (run_id, tool, cost_usd) VALUES (?, ?, ?)",
            ("run-009", "score", 0.002),
        )
        conn.commit()
        reflector = Reflector(conn)
        result = reflector.analyze_run("run-009")
        cost = result["cost_analysis"]
        assert cost["total"] == pytest.approx(0.003, abs=0.001)
        assert "search" in cost["by_tool"]
        assert "score" in cost["by_tool"]

    def test_cost_analysis_empty(self, conn):
        conn.execute(
            "INSERT INTO run_log (run_id, goal, status, started_at) VALUES (?, ?, ?, ?)",
            ("run-010", "Find jobs", "completed", "2025-01-01T00:00:00"),
        )
        conn.commit()
        reflector = Reflector(conn)
        result = reflector.analyze_run("run-010")
        assert result["cost_analysis"]["total"] == 0.0


class TestReflectorRecommendations:
    def test_recommendations_from_failures(self, conn):
        conn.execute(
            "INSERT INTO run_log (run_id, goal, status, started_at) VALUES (?, ?, ?, ?)",
            ("run-011", "Find jobs", "completed", "2025-01-01T00:00:00"),
        )
        conn.execute(
            "INSERT INTO jobs (url, title, site, detail_error, discovered_at) "
            "VALUES (?, ?, ?, ?, ?)",
            ("http://example.com/1", "Dev", "linkedin", "timeout", "2025-01-01T00:00:01"),
        )
        conn.commit()
        reflector = Reflector(conn)
        result = reflector.analyze_run("run-011")
        assert len(result["recommendations"]) > 0

    def test_recommendations_healthy_run(self, conn):
        conn.execute(
            "INSERT INTO run_log (run_id, goal, status, started_at) VALUES (?, ?, ?, ?)",
            ("run-012", "Find jobs", "completed", "2025-01-01T00:00:00"),
        )
        for i in range(3):
            conn.execute(
                "INSERT INTO jobs (url, title, site, fit_score, discovered_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (f"http://example.com/{i}", f"Job {i}", "linkedin", 7, "2025-01-01T00:00:01"),
            )
        conn.commit()
        reflector = Reflector(conn)
        result = reflector.analyze_run("run-012")
        assert len(result["recommendations"]) > 0


class TestReflectorRating:
    def test_rating_good(self, conn):
        conn.execute(
            "INSERT INTO run_log (run_id, goal, status, started_at) VALUES (?, ?, ?, ?)",
            ("run-013", "Find jobs", "completed", "2025-01-01T00:00:00"),
        )
        for i in range(5):
            conn.execute(
                "INSERT INTO jobs (url, title, site, fit_score, discovered_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (f"http://example.com/{i}", f"Job {i}", "linkedin", 7, "2025-01-01T00:00:01"),
            )
        conn.commit()
        reflector = Reflector(conn)
        result = reflector.analyze_run("run-013")
        assert result["overall_rating"] in ("ok", "good")

    def test_rating_poor_with_many_errors(self, conn):
        conn.execute(
            "INSERT INTO run_log (run_id, goal, status, started_at) VALUES (?, ?, ?, ?)",
            ("run-014", "Find jobs", "completed", "2025-01-01T00:00:00"),
        )
        for i in range(5):
            conn.execute(
                "INSERT INTO jobs (url, title, site, detail_error, discovered_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (f"http://example.com/{i}", f"Job {i}", "linkedin", "timeout", "2025-01-01T00:00:01"),
            )
        conn.commit()
        reflector = Reflector(conn)
        result = reflector.analyze_run("run-014")
        assert result["overall_rating"] == "poor"
