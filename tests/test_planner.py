"""Tests for Planner — goal decomposition into execution plans."""

from joborion.agent.planner import Planner, Plan, PlanStep


class TestPlanner:
    def setup_method(self):
        self.planner = Planner()

    def test_plan_default_goal(self):
        plan = self.planner.plan("Find Python jobs")
        assert plan.goal == "Find Python jobs"
        assert len(plan.steps) > 0

    def test_plan_detects_search_stages(self):
        plan = self.planner.plan("Find Python jobs")
        tools = [s.tool for s in plan.steps]
        assert "search_jobspy" in tools

    def test_plan_with_query(self):
        plan = self.planner.plan("Find senior Python jobs")
        search_step = next(s for s in plan.steps if s.tool == "search_jobspy")
        assert "python" in search_step.params.get("search_query", "")

    def test_plan_tailor_goal(self):
        plan = self.planner.plan("Find and tailor resume for Python jobs")
        tools = [s.tool for s in plan.steps]
        assert "tailor_resume" in tools

    def test_plan_all_stages(self):
        plan = self.planner.plan("Find, enrich, score, tailor, and export PDF for Python jobs")
        tools = [s.tool for s in plan.steps]
        assert "search_jobspy" in tools
        assert "fetch_details" in tools
        assert "evaluate_jobs" in tools

    def test_plan_total_cost(self):
        plan = self.planner.plan("Find Python jobs")
        assert plan.total_cost >= 0.0

    def test_plan_total_duration(self):
        plan = self.planner.plan("Find Python jobs")
        assert plan.total_duration_ms > 0

    def test_plan_steps_have_descriptions(self):
        plan = self.planner.plan("Find Python jobs")
        for step in plan.steps:
            assert step.description
            assert isinstance(step.description, str)

    def test_plan_steps_have_params(self):
        plan = self.planner.plan("Find Python jobs")
        for step in plan.steps:
            assert isinstance(step.params, dict)

    def test_plan_high_score_detection(self):
        plan = self.planner.plan("Find best Python jobs")
        tailor_step = next((s for s in plan.steps if s.tool == "tailor_resume"), None)
        if tailor_step:
            assert tailor_step.params.get("min_score", 0) >= 8

    def test_plan_detects_evaluate(self):
        plan = self.planner.plan("Score and rank Python jobs")
        tools = [s.tool for s in plan.steps]
        assert "evaluate_jobs" in tools

    def test_plan_detects_letter(self):
        plan = self.planner.plan("Write cover letter for Python jobs")
        tools = [s.tool for s in plan.steps]
        assert "write_letter" in tools


class TestPlan:
    def test_plan_total_cost_empty(self):
        plan = Plan(goal="test")
        assert plan.total_cost == 0.0

    def test_plan_total_duration_empty(self):
        plan = Plan(goal="test")
        assert plan.total_duration_ms == 0

    def test_plan_step_dependencies(self):
        steps = [
            PlanStep(tool="a", params={}, description="first"),
            PlanStep(tool="b", params={}, description="second", depends_on=0),
        ]
        assert steps[1].depends_on == 0
        assert steps[0].depends_on is None
