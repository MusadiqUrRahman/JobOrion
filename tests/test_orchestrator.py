"""Tests for joborion.agent.orchestrator, planner, and context manager."""

import sqlite3
from unittest.mock import patch, MagicMock

import pytest
from joborion.agent.planner import PlanStep, Planner
from joborion.agent.context import ContextManager
from joborion.agent.orchestrator import Orchestrator, BudgetExceeded
from joborion.agent.tools import ActionResult
from joborion.database import close_connection, init_db


@pytest.fixture
def conn(tmp_path):
    db_path = tmp_path / "test.db"
    close_connection(str(db_path))
    c = init_db(str(db_path))
    yield c
    close_connection(str(db_path))


# ===========================================================================
# Task 1: Planner
# ===========================================================================

class TestPlanStep:
    """Tests for PlanStep dataclass."""

    def test_plan_step_fields(self):
        """PlanStep has all required fields."""
        step = PlanStep(
            tool="scrape_jobspy",
            params={"search_query": "python"},
            description="Search for Python jobs",
            cost_estimate=0.0,
            duration_estimate_ms=5000,
        )
        assert step.tool == "scrape_jobspy"
        assert step.params["search_query"] == "python"
        assert step.description == "Search for Python jobs"

    def test_plan_step_optional_fields(self):
        """PlanStep has sensible defaults for optional fields."""
        step = PlanStep(tool="x", params={}, description="x")
        assert step.cost_estimate == 0.0
        assert step.duration_estimate_ms == 0
        assert step.depends_on is None


class TestPlanner:
    """Tests for Planner — goal parsing and plan generation."""

    def test_parse_goal_query(self):
        """Planner extracts search query from goal."""
        planner = Planner()
        plan = planner.plan("Find remote Python jobs paying 150k+")
        assert len(plan.steps) > 0
        # First step should be search
        assert plan.steps[0].tool == "search_jobspy"

    def test_plan_includes_all_stages(self):
        """Full goal produces search through export steps."""
        planner = Planner()
        plan = planner.plan("Find 10 Python jobs, score them, tailor resumes, apply")
        tools = [s.tool for s in plan.steps]
        assert "search_jobspy" in tools
        assert "evaluate_jobs" in tools
        assert "tailor_resume" in tools

    def test_plan_has_cost_estimates(self):
        """Each step has a cost estimate."""
        planner = Planner()
        plan = planner.plan("Find Python jobs")
        for step in plan.steps:
            assert isinstance(step.cost_estimate, float)

    def test_plan_total_cost(self):
        """Plan has a total cost estimate."""
        planner = Planner()
        plan = planner.plan("Find Python jobs, score, tailor")
        assert plan.total_cost >= 0.0

    def test_plan_total_duration(self):
        """Plan has a total duration estimate."""
        planner = Planner()
        plan = planner.plan("Find Python jobs")
        assert plan.total_duration_ms >= 0

    def test_plan_steps_ordered_by_deps(self):
        """Steps are in dependency order (search before details before evaluate)."""
        planner = Planner()
        plan = planner.plan("Find Python jobs, get full description, score them, tailor resume, write cover letter")
        tools = [s.tool for s in plan.steps]
        # search must come before details
        assert tools.index("search_jobspy") < tools.index("fetch_details")
        # details must come before evaluate
        assert tools.index("fetch_details") < tools.index("evaluate_jobs")
        # evaluate must come before tailor
        assert tools.index("evaluate_jobs") < tools.index("tailor_resume")
        # tailor must come before letter
        assert tools.index("tailor_resume") < tools.index("write_letter")

    def test_plan_search_only(self):
        """Search-only goal produces only search steps."""
        planner = Planner()
        plan = planner.plan("Find Python jobs")
        tools = [s.tool for s in plan.steps]
        assert "search_jobspy" in tools
        # Should NOT have evaluate or tailor
        assert "evaluate_jobs" not in tools
        assert "tailor_resume" not in tools


# ===========================================================================
# Task 2: Context Manager
# ===========================================================================

class TestContextManager:
    """Tests for ContextManager — working state and compression."""

    def test_add_action(self):
        """add_action records an action result."""
        ctx = ContextManager()
        result = ActionResult("scrape_jobspy", "ok", {"new": 10}, 0.0, 1500, None)
        ctx.add_action(result)
        assert ctx.action_count == 1

    def test_get_recent_actions(self):
        """get_recent_actions returns the last N actions."""
        ctx = ContextManager()
        for i in range(10):
            ctx.add_action(ActionResult(f"action_{i}", "ok", {}, 0.0, 0, None))
        recent = ctx.get_recent_actions(n=3)
        assert len(recent) == 3
        assert recent[0].action == "action_7"
        assert recent[2].action == "action_9"

    def test_get_working_state(self):
        """get_working_state returns a summary of progress."""
        ctx = ContextManager()
        ctx.add_action(ActionResult("scrape_jobspy", "ok", {"new": 5}, 0.0, 1000, None))
        ctx.add_action(ActionResult("enrich_batch", "ok", {"ok": 3}, 0.0, 2000, None))
        state = ctx.get_working_state()
        assert "actions_completed" in state
        assert state["actions_completed"] == 2

    def test_get_working_state_empty(self):
        """get_working_state works with no actions."""
        ctx = ContextManager()
        state = ctx.get_working_state()
        assert state["actions_completed"] == 0

    def test_compress_old_actions(self):
        """compress() summarizes old actions, keeps recent ones."""
        ctx = ContextManager()
        for i in range(20):
            ctx.add_action(ActionResult(f"action_{i}", "ok", {}, 0.0, 0, None))
        ctx.compress(keep_recent=5)
        assert ctx.action_count == 5
        recent = ctx.get_recent_actions(n=5)
        assert recent[0].action == "action_15"

    def test_token_estimate(self):
        """token_estimate returns a rough count of context size."""
        ctx = ContextManager()
        ctx.add_action(ActionResult("test", "ok", {"data": "x" * 100}, 0.0, 0, None))
        assert ctx.token_estimate() > 0


# ===========================================================================
# Task 3: Orchestrator
# ===========================================================================

class TestOrchestrator:
    """Tests for Orchestrator — main agent loop."""

    def test_orchestrator_creates(self):
        """Orchestrator can be instantiated."""
        orch = Orchestrator(goal="Find Python jobs")
        assert orch.goal == "Find Python jobs"

    def test_orchestrator_has_budget(self):
        """Orchestrator respects budget limits."""
        orch = Orchestrator(goal="test", max_cost=1.0)
        assert orch.max_cost == 1.0

    def test_orchestrator_plan_mode(self):
        """Orchestrator can generate a plan without executing."""
        orch = Orchestrator(goal="Find Python jobs")
        plan = orch.plan()
        assert len(plan.steps) > 0

    def test_orchestrator_budget_check(self):
        """BudgetExceeded raised when budget is exceeded."""
        orch = Orchestrator(goal="test", max_cost=0.0)
        with pytest.raises(BudgetExceeded):
            orch._check_budget()

    def test_orchestrator_tracks_cost(self):
        """Orchestrator tracks accumulated cost."""
        orch = Orchestrator(goal="test", max_cost=5.0)
        orch._accumulated_cost = 1.5
        assert orch._accumulated_cost == 1.5

    def test_orchestrator_execute_dry_run(self):
        """execute() in dry-run mode returns plan without running tools."""
        orch = Orchestrator(goal="Find Python jobs")
        result = orch.execute(dry_run=True)
        assert result["status"] == "planned"
        assert len(result["plan"]) > 0

    def test_orchestrator_error_recovery(self):
        """Orchestrator marks failed steps and continues."""
        orch = Orchestrator(goal="test")
        # Simulate a failed step
        result = ActionResult("search_jobspy", "error", {}, 0.0, 100, "timeout")
        orch._record_result(result)
        state = orch.context.get_working_state()
        assert state["errors"] == 1


# ===========================================================================
# Task 4: CLI Integration (mocked)
# ===========================================================================

class TestCLIIntegration:
    """Tests for CLI goal-oriented commands."""

    def test_plan_command_exists(self):
        """'plan' command is registered in the CLI app."""
        from joborion.cli import app
        from typer.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(app, ["plan", "--help"])
        assert result.exit_code == 0

    def test_run_accepts_goal(self):
        """'run' command accepts --goal flag."""
        from joborion.cli import app
        from typer.testing import CliRunner
        runner = CliRunner()
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--goal" in result.output
