"""Tests for Phase F2: goal-driven search via the new sourcing providers."""

from joborion.sources.base import ProviderResult
from joborion.tools.discovery import SearchProvidersTool


class TestSearchProvidersTool:
    def test_runs_providers_and_reports(self, monkeypatch):
        captured = {}

        def fake_run(intent, providers=None, conn=None, caps=None):
            captured["intent"] = intent
            return [
                ProviderResult(provider="jobspy", found=10, stored=8),
                ProviderResult(provider="workday", found=3, stored=2),
                ProviderResult(provider="adzuna", found=0, stored=0, errors=1, error="boom"),
            ]

        monkeypatch.setattr("joborion.sources.registry.run_providers", fake_run)
        tool = SearchProvidersTool()
        result = tool.execute(query="python", remote=True, min_salary=50000)
        assert result.status == "ok"
        assert result.details["providers_run"] == 3
        assert result.details["providers_ok"] == 2
        assert result.details["found"] == 13
        assert result.details["stored"] == 10
        assert result.details["errors"] == 1
        assert captured["intent"]["remote_only"] is True
        assert captured["intent"]["min_salary"] == 50000
        assert captured["intent"]["query"] == "python"

    def test_error_result(self, monkeypatch):
        def fake_run(intent, providers=None, conn=None, caps=None):
            raise RuntimeError("config missing")

        monkeypatch.setattr("joborion.sources.registry.run_providers", fake_run)
        tool = SearchProvidersTool()
        result = tool.execute(query="python")
        assert result.status == "error"
        assert "config missing" in result.error

    def test_registered_in_default_registry(self):
        from joborion.agent.registry import build_default_registry
        registry = build_default_registry()
        assert "search_providers" in registry.list_tools()

    def test_registry_dispatch_returns_ok(self, monkeypatch):
        from joborion.agent.registry import build_default_registry
        registry = build_default_registry()

        def fake_run(intent, providers=None, conn=None, caps=None):
            return [ProviderResult(provider="jobspy", found=5, stored=5)]

        monkeypatch.setattr("joborion.sources.registry.run_providers", fake_run)
        result = registry.dispatch("search_providers", query="python")
        assert result.status == "ok"
        assert result.details["found"] == 5


class TestPlannerProviders:
    def test_planner_emits_search_providers_for_providers_goal(self):
        from joborion.agent.planner import Planner
        plan = Planner().plan("find python jobs across all providers")
        assert any(s.tool == "search_providers" for s in plan.steps)

    def test_plain_search_goal_unchanged(self):
        from joborion.agent.planner import Planner
        plan = Planner().plan("find python jobs")
        tools = [s.tool for s in plan.steps]
        assert "scrape_jobspy" in tools
        assert "search_providers" not in tools
