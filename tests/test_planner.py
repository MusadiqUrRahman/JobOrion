"""Tests for Planner — goal decomposition into execution plans."""

from unittest.mock import MagicMock

from joborion.agent.planner import (
    Planner, Plan, PlanStep, LLMPlanner, _parse_llm_response, _validate_steps,
)


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
        assert "scrape_jobspy" in tools

    def test_plan_with_query(self):
        plan = self.planner.plan("Find senior Python jobs")
        search_step = next(s for s in plan.steps if s.tool == "scrape_jobspy")
        assert "python" in search_step.params.get("search_query", "")

    def test_plan_with_non_tech_query(self):
        plan = self.planner.plan("Find 10 remote accounting jobs")
        search_step = next(s for s in plan.steps if s.tool == "scrape_jobspy")
        assert search_step.params.get("search_query", "") == "accounting"

    def test_plan_tailor_goal(self):
        plan = self.planner.plan("Find and tailor resume for Python jobs")
        tools = [s.tool for s in plan.steps]
        assert "tailor_resume" in tools

    def test_plan_all_stages(self):
        plan = self.planner.plan("Find, enrich, score, tailor, and export PDF for Python jobs")
        tools = [s.tool for s in plan.steps]
        assert "scrape_jobspy" in tools
        assert "enrich_batch" in tools
        assert "score_batch" in tools

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
        assert "score_batch" in tools

    def test_plan_detects_letter(self):
        plan = self.planner.plan("Write cover letter for Python jobs")
        tools = [s.tool for s in plan.steps]
        assert "write_cover_letter" in tools

    def test_plan_uses_llm_when_available(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = '''[
            {"tool": "scrape_jobspy", "params": {"search_query": "senior python remote"}, "description": "Search job boards"},
            {"tool": "enrich_batch", "params": {"limit": 50}, "description": "Enrich jobs"},
            {"tool": "score_batch", "params": {}, "description": "Score jobs"}
        ]'''
        planner = Planner(client=mock_client)
        plan = planner.plan("Find senior remote Python jobs")
        tools = [s.tool for s in plan.steps]
        assert "scrape_jobspy" in tools
        assert "enrich_batch" in tools
        assert "score_batch" in tools
        mock_client.chat.assert_called_once()

    def test_plan_fallback_on_llm_failure(self):
        mock_client = MagicMock()
        mock_client.chat.side_effect = RuntimeError("API error")
        planner = Planner(client=mock_client)
        plan = planner.plan("Find Python jobs")
        # Should fall back to keyword planner and still produce steps
        assert len(plan.steps) > 0
        tools = [s.tool for s in plan.steps]
        assert "scrape_jobspy" in tools

    def test_plan_fallback_on_llm_empty_response(self):
        mock_client = MagicMock()
        mock_client.chat.return_value = "I don't know how to plan that."
        planner = Planner(client=mock_client)
        plan = planner.plan("Find Python jobs")
        assert len(plan.steps) > 0

    def test_plan_no_client_uses_keyword(self):
        planner = Planner(client=None)
        plan = planner.plan("Find Python jobs")
        assert len(plan.steps) > 0
        tools = [s.tool for s in plan.steps]
        assert "scrape_jobspy" in tools


class TestLLMPlanner:
    def setup_method(self):
        self.mock_client = MagicMock()

    def test_plan_valid_response(self):
        self.mock_client.chat.return_value = '''[
            {"tool": "scrape_jobspy", "params": {"search_query": "python"}, "description": "Search boards"},
            {"tool": "score_batch", "params": {}, "description": "Score jobs"}
        ]'''
        planner = LLMPlanner(self.mock_client)
        plan = planner.plan("Find Python jobs")
        assert plan is not None
        assert len(plan.steps) == 2
        assert plan.steps[0].tool == "scrape_jobspy"
        assert plan.steps[0].params == {"search_query": "python"}

    def test_plan_with_code_fences(self):
        self.mock_client.chat.return_value = '''```json
[
    {"tool": "scrape_jobspy", "params": {}, "description": "Search"}
]
```'''
        planner = LLMPlanner(self.mock_client)
        plan = planner.plan("Find jobs")
        assert plan is not None
        assert len(plan.steps) == 1

    def test_plan_filters_unknown_tools(self):
        self.mock_client.chat.return_value = '''[
            {"tool": "scrape_jobspy", "params": {}, "description": "Search"},
            {"tool": "nonexistent_tool", "params": {}, "description": "Bad tool"}
        ]'''
        planner = LLMPlanner(self.mock_client)
        plan = planner.plan("Find jobs")
        assert plan is not None
        assert len(plan.steps) == 1
        assert plan.steps[0].tool == "scrape_jobspy"

    def test_plan_returns_none_on_llm_error(self):
        self.mock_client.chat.side_effect = RuntimeError("API down")
        planner = LLMPlanner(self.mock_client)
        plan = planner.plan("Find jobs")
        assert plan is None

    def test_plan_returns_none_on_invalid_json(self):
        self.mock_client.chat.return_value = "This is not JSON at all."
        planner = LLMPlanner(self.mock_client)
        plan = planner.plan("Find jobs")
        assert plan is None

    def test_plan_returns_none_on_empty_array(self):
        self.mock_client.chat.return_value = "[]"
        planner = LLMPlanner(self.mock_client)
        plan = planner.plan("Find jobs")
        assert plan is None

    def test_plan_step_dependencies(self):
        self.mock_client.chat.return_value = '''[
            {"tool": "scrape_jobspy", "params": {}, "description": "Search"},
            {"tool": "enrich_batch", "params": {}, "description": "Enrich"},
            {"tool": "score_batch", "params": {}, "description": "Score"}
        ]'''
        planner = LLMPlanner(self.mock_client)
        plan = planner.plan("Find and score jobs")
        assert plan.steps[0].depends_on is None
        assert plan.steps[1].depends_on == 0
        assert plan.steps[2].depends_on == 1


class TestParseLLMResponse:
    def test_parse_valid_json(self):
        raw = '[{"tool": "scrape_jobspy", "params": {}, "description": "Search"}]'
        result = _parse_llm_response(raw)
        assert result is not None
        assert len(result) == 1

    def test_parse_with_code_fences(self):
        raw = '```json\n[{"tool": "scrape_jobspy", "params": {}, "description": "Search"}]\n```'
        result = _parse_llm_response(raw)
        assert result is not None
        assert len(result) == 1

    def test_parse_with_surrounding_text(self):
        raw = 'Here is the plan:\n[{"tool": "scrape_jobspy", "params": {}, "description": "Search"}]\nDone.'
        result = _parse_llm_response(raw)
        assert result is not None

    def test_parse_invalid_returns_none(self):
        result = _parse_llm_response("no json here")
        assert result is None

    def test_parse_non_array_returns_none(self):
        result = _parse_llm_response('{"tool": "scrape_jobspy"}')
        assert result is None

    def test_parse_empty_array(self):
        result = _parse_llm_response("[]")
        assert result is not None
        assert len(result) == 0


class TestValidateSteps:
    def test_validate_valid_steps(self):
        raw = [
            {"tool": "scrape_jobspy", "params": {"search_query": "python"}, "description": "Search"},
            {"tool": "score_batch", "params": {}, "description": "Score"},
        ]
        steps = _validate_steps(raw)
        assert len(steps) == 2
        assert steps[0].tool == "scrape_jobspy"
        assert steps[0].params == {"search_query": "python"}
        assert steps[1].depends_on == 0

    def test_validate_skips_unknown_tools(self):
        raw = [
            {"tool": "scrape_jobspy", "params": {}, "description": "Search"},
            {"tool": "fake_tool", "params": {}, "description": "Fake"},
        ]
        steps = _validate_steps(raw)
        assert len(steps) == 1

    def test_validate_fills_defaults(self):
        raw = [{"tool": "scrape_jobspy"}]
        steps = _validate_steps(raw)
        assert len(steps) == 1
        assert steps[0].params == {}
        assert steps[0].description == "Execute scrape_jobspy"

    def test_validate_empty_list(self):
        steps = _validate_steps([])
        assert steps == []


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


class TestPlannerToolNameSync:
    """Drift guard: every tool name the planner emits must be registered."""

    def test_stage_tools_all_registered(self):
        from joborion.agent.planner import _STAGE_TOOLS
        from joborion.agent.registry import build_default_registry
        registered = set(build_default_registry().list_tools())
        emitted = {name for stage in _STAGE_TOOLS.values() for name, _, _, _, _ in stage}
        assert emitted <= registered, f"Unregistered planner tools: {emitted - registered}"

    def test_known_tools_all_registered(self):
        from joborion.agent.planner import _KNOWN_TOOLS
        from joborion.agent.registry import build_default_registry
        registered = set(build_default_registry().list_tools())
        known = {t["name"] for t in _KNOWN_TOOLS}
        assert known <= registered, f"Unregistered known tools: {known - registered}"
