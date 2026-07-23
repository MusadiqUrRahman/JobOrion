"""Tests for Phase 5: Goal Parser, Autonomous Mode, Reporter."""

import sqlite3
from unittest.mock import patch, MagicMock

import pytest
from joborion.agent.goal_parser import GoalParser
from joborion.agent.reporter import RunReporter
from joborion.agent.orchestrator import Orchestrator
from joborion.database import close_connection, init_db


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    close_connection(str(db_path))
    c = init_db(str(db_path))
    yield c
    close_connection(str(db_path))


# ===========================================================================
# Task 1: Goal Parser
# ===========================================================================

class TestGoalParser:
    """Tests for GoalParser — natural language to structured goal."""

    def test_basic_goal(self):
        """Parses 'Find Python jobs' correctly."""
        parser = GoalParser()
        result = parser.parse("Find Python jobs")
        assert "python" in result["query"].lower()
        assert result["actions"]["search"] is True

    def test_with_remote(self):
        """Detects 'remote' in goal."""
        parser = GoalParser()
        result = parser.parse("Find remote Python jobs")
        assert result["filters"]["remote"] is True

    def test_with_salary(self):
        """Extracts salary threshold from goal."""
        parser = GoalParser()
        result = parser.parse("Find Python jobs paying 150k+")
        assert result["filters"]["min_salary"] == 150000

    def test_with_limits(self):
        """Extracts max_jobs and max_applications."""
        parser = GoalParser()
        result = parser.parse("Find 10 Python jobs, apply to best 5")
        assert result["limits"]["max_jobs"] == 10
        assert result["limits"]["max_applications"] == 5

    def test_defaults(self):
        """Sensible defaults for all fields."""
        parser = GoalParser()
        result = parser.parse("Find jobs")
        assert result["filters"]["min_score"] == 7
        assert result["actions"]["search"] is True
        assert result["actions"]["details"] is True
        assert result["actions"]["evaluate"] is True

    def test_high_score_keyword(self):
        """'best' or 'top' raises min_score to 8."""
        parser = GoalParser()
        result = parser.parse("Find the best Python jobs")
        assert result["filters"]["min_score"] == 8

    def test_apply_keyword(self):
        """'apply' keyword enables all actions."""
        parser = GoalParser()
        result = parser.parse("Find Python jobs and apply to them")
        assert result["actions"]["search"] is True
        assert result["actions"]["evaluate"] is True
        assert result["actions"]["tailor"] is True
        assert result["actions"]["letter"] is True

    def test_tech_keywords(self):
        """Extracts multiple tech keywords."""
        parser = GoalParser()
        result = parser.parse("Find senior React and Node.js jobs")
        query = result["query"].lower()
        assert "react" in query
        assert "senior" in query


# ===========================================================================
# Task 2: Autonomous Mode
# ===========================================================================

class TestAutonomousMode:
    """Tests for Orchestrator autonomous mode."""

    def test_creates_with_auto(self):
        """Orchestrator can be created with auto=True."""
        orch = Orchestrator(goal="test", auto=True)
        assert orch._auto is True

    def test_creates_with_yes(self):
        """Orchestrator can be created with yes=True."""
        orch = Orchestrator(goal="test", auto=True, yes=True)
        assert orch._yes is True

    def test_creates_with_semi(self):
        """Orchestrator can be created with semi=True."""
        orch = Orchestrator(goal="test", auto=True, semi=True)
        assert orch._semi is True

    def test_execute_dry_run_auto(self):
        """dry_run in auto mode returns plan."""
        orch = Orchestrator(goal="Find Python jobs", auto=True)
        result = orch.execute(dry_run=True)
        assert result["status"] == "planned"
        assert len(result["plan"]) > 0

    def test_goal_parser_integration(self):
        """Orchestrator uses GoalParser when auto=True."""
        orch = Orchestrator(goal="Find remote Python jobs paying 100k", auto=True)
        plan = orch.plan()
        assert len(plan.steps) > 0


# ===========================================================================
# Task 3: Human-in-the-Loop Gates
# ===========================================================================

class TestGates:
    """Tests for human-in-the-loop gates."""

    def test_gate_checks_cost(self):
        """Gate triggers when cost exceeds 50% of budget."""
        orch = Orchestrator(goal="test", max_cost=1.0, auto=True)
        orch._accumulated_cost = 0.6  # 60% of budget
        assert orch._should_gate("cost") is True

    def test_gate_skipped_with_yes(self):
        """Gate is skipped when yes=True."""
        orch = Orchestrator(goal="test", auto=True, yes=True)
        orch._accumulated_cost = 0.6
        assert orch._should_gate("cost") is False

    def test_gate_checks_error_rate(self):
        """Gate triggers when error rate > 30%."""
        orch = Orchestrator(goal="test", auto=True)
        orch._call_count = 10
        orch._error_count = 4  # 40%
        assert orch._should_gate("error_rate") is True

    def test_gate_passes_normal(self):
        """Gate passes when conditions normal."""
        orch = Orchestrator(goal="test", auto=True)
        orch._accumulated_cost = 0.1
        orch._call_count = 10
        orch._error_count = 1
        assert orch._should_gate("cost") is False
        assert orch._should_gate("error_rate") is False


# ===========================================================================
# Task 4: Run Summary Report
# ===========================================================================

class TestReporter:
    """Tests for RunReporter."""

    def test_generates_report(self):
        """Report output is non-empty string."""
        reporter = RunReporter()
        data = {
            "goal": "Find Python jobs",
            "duration_s": 120.5,
            "total_cost": 0.05,
            "stages": [
                {"name": "search", "status": "ok", "count": 47},
                {"name": "details", "status": "ok", "count": 35},
                {"name": "evaluate", "status": "ok", "count": 35},
            ],
            "top_jobs": [
                {"title": "Python Dev", "company": "Stripe", "score": 9},
                {"title": "Backend Eng", "company": "Notion", "score": 8},
            ],
            "errors": [],
        }
        report = reporter.generate(data)
        assert len(report) > 0
        assert "Python" in report

    def test_includes_stats(self):
        """Report has pipeline stats."""
        reporter = RunReporter()
        data = {
            "goal": "test",
            "duration_s": 60,
            "total_cost": 0.01,
            "stages": [{"name": "search", "status": "ok", "count": 10}],
            "top_jobs": [],
            "errors": [],
        }
        report = reporter.generate(data)
        assert "search" in report.lower() or "10" in report

    def test_includes_cost(self):
        """Report includes cost breakdown."""
        reporter = RunReporter()
        data = {
            "goal": "test",
            "duration_s": 30,
            "total_cost": 0.042,
            "stages": [],
            "top_jobs": [],
            "errors": [],
        }
        report = reporter.generate(data)
        assert "0.042" in report or "$0.04" in report

    def test_handles_errors(self):
        """Report shows errors when present."""
        reporter = RunReporter()
        data = {
            "goal": "test",
            "duration_s": 10,
            "total_cost": 0.0,
            "stages": [],
            "top_jobs": [],
            "errors": ["Scraping failed on site X"],
        }
        report = reporter.generate(data)
        assert "error" in report.lower() or "Scraping" in report


# ===========================================================================
# Task 5: CLI Integration
# ===========================================================================

class TestCLIAutonomy:
    """Tests for CLI autonomous flags."""

    def test_run_help_shows_auto(self):
        """'joborion run --help' shows --auto flag."""
        from joborion.cli import app
        from typer.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--auto" in result.output

    def test_run_help_shows_yes(self):
        """'joborion run --help' shows --yes flag."""
        from joborion.cli import app
        from typer.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(app, ["run", "--help"])
        assert "--yes" in result.output

    def test_run_help_shows_semi(self):
        """'joborion run --help' shows --semi flag."""
        from joborion.cli import app
        from typer.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(app, ["run", "--help"])
        assert "--semi" in result.output
