"""Tests for Orchestrator — goal-driven execution loop."""

from unittest.mock import MagicMock, patch

import pytest
from joborion.agent.orchestrator import Orchestrator, BudgetExceeded
from joborion.agent.planner import Plan, PlanStep
from joborion.agent.tools import ActionResult
from joborion.agent.registry import ToolRegistry


def _make_result(action="test", status="ok", cost=0.0):
    return ActionResult(action=action, status=status, details={}, cost=cost, duration_ms=0, error=None)


def _make_registry(tool_names=None):
    registry = ToolRegistry()
    for name in (tool_names or ["search_jobspy", "evaluate_jobs"]):
        tool = MagicMock()
        tool.name = name
        tool.description = f"Mock {name}"
        tool.parameters = {}
        tool.execute.return_value = _make_result(action=name)
        registry.register(tool)
    return registry


class TestOrchestratorPlan:
    def test_plan_returns_plan(self):
        orch = Orchestrator(goal="Find Python jobs")
        plan = orch.plan()
        assert isinstance(plan, Plan)
        assert len(plan.steps) > 0

    def test_plan_dry_run(self):
        orch = Orchestrator(goal="Find Python jobs")
        result = orch.execute(dry_run=True)
        assert result["status"] == "planned"
        assert len(result["results"]) == 0
        assert result["total_cost"] == 0.0


class TestOrchestratorExecute:
    def test_execute_with_mocked_tools(self):
        registry = _make_registry(["search_jobspy", "search_workday", "search_ai_sites"])
        orch = Orchestrator(goal="Find Python jobs", registry=registry)
        result = orch.execute()
        assert result["status"] == "completed"
        assert result["total_cost"] >= 0.0

    def test_execute_tool_failure(self):
        registry = ToolRegistry()
        tool = MagicMock()
        tool.name = "search_jobspy"
        tool.description = "Mock"
        tool.parameters = {}
        tool.execute.return_value = _make_result(action="search_jobspy", status="error")
        registry.register(tool)
        orch = Orchestrator(goal="Find Python jobs", registry=registry)
        result = orch.execute()
        assert len(result["errors"]) > 0

    def test_execute_budget_check(self):
        orch = Orchestrator(goal="Find Python jobs", max_cost=0.0, max_calls=0)
        with pytest.raises(BudgetExceeded, match="Budget exhausted"):
            orch.execute()


class TestOrchestratorGates:
    def test_error_rate_gate(self):
        orch = Orchestrator(goal="test", auto=True)
        orch._call_count = 10
        orch._error_count = 4
        assert orch._error_rate() == 0.4
        assert orch._should_gate("error_rate") is True

    def test_error_rate_gate_no_trigger(self):
        orch = Orchestrator(goal="test", auto=True)
        orch._call_count = 10
        orch._error_count = 2
        assert orch._error_rate() == 0.2
        assert orch._should_gate("error_rate") is False

    def test_cost_gate(self):
        orch = Orchestrator(goal="test", auto=True, max_cost=1.0)
        orch._accumulated_cost = 0.6
        assert orch._should_gate("cost") is True

    def test_cost_gate_no_trigger(self):
        orch = Orchestrator(goal="test", auto=True, max_cost=1.0)
        orch._accumulated_cost = 0.3
        assert orch._should_gate("cost") is False

    def test_yes_skips_gates(self):
        orch = Orchestrator(goal="test", auto=True, yes=True)
        orch._accumulated_cost = 0.9
        assert orch._should_gate("cost") is False

    def test_apply_gate_semi(self):
        orch = Orchestrator(goal="test", semi=True)
        assert orch._should_gate("apply") is True

    def test_apply_gate_not_semi(self):
        orch = Orchestrator(goal="test", semi=False)
        assert orch._should_gate("apply") is False


class TestOrchestratorBudget:
    def test_check_budget_within_limit(self):
        orch = Orchestrator(goal="test", max_cost=1.0, max_calls=10)
        orch._accumulated_cost = 0.5
        orch._call_count = 5
        orch._check_budget()  # Should not raise

    def test_check_budget_exceeded_cost(self):
        orch = Orchestrator(goal="test", max_cost=1.0)
        orch._accumulated_cost = 1.5
        with pytest.raises(BudgetExceeded, match="Budget exhausted"):
            orch._check_budget()

    def test_check_budget_exceeded_calls(self):
        orch = Orchestrator(goal="test", max_calls=5)
        orch._call_count = 6
        with pytest.raises(BudgetExceeded, match="Call limit exhausted"):
            orch._check_budget()


class TestOrchestratorFailedTools:
    def test_failed_tool_skipped(self):
        registry = _make_registry(["search_jobspy", "evaluate_jobs"])
        orch = Orchestrator(goal="Find and score Python jobs", registry=registry)
        orch._failed_tools.add("search_jobspy")
        # execute should skip search_jobspy
        result = orch.execute()
        # The search_jobspy tool should not have been dispatched
        assert "search_jobspy" not in [
            r.action for r in result["results"] if r.status == "ok"
        ]


class TestOrchestratorAutonomous:
    @patch("joborion.agent.orchestrator.Orchestrator.execute")
    @patch("joborion.agent.orchestrator.Orchestrator.plan")
    def test_execute_autonomous_calls_reflect(self, mock_plan, mock_execute):
        mock_plan.return_value = Plan(
            goal="test",
            steps=[PlanStep(tool="search_jobspy", params={}, description="Search")],
        )
        mock_execute.return_value = {
            "status": "completed",
            "results": [],
            "total_cost": 0.0,
            "errors": [],
        }
        orch = Orchestrator(goal="test")
        with patch("joborion.agent.reflector.Reflector") as mock_ref:
            mock_ref.return_value.analyze_run.return_value = {
                "recommendations": [], "what_went_well": [],
            }
            with patch("joborion.database.store_reflection"):
                with patch("joborion.database.get_connection"):
                    result = orch.execute_autonomous()
        assert "status" in result
        assert "report" in result
