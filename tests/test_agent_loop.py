"""Tests for AgentLoop — ReAct-style dynamic tool selection."""

import json
from unittest.mock import MagicMock

from joborion.agent.agent_loop import AgentLoop
from joborion.agent.registry import ToolRegistry
from joborion.agent.tools import ActionResult


def _result(action="query_jobs", status="ok", cost=0.0, details=None, error=None):
    return ActionResult(
        action=action, status=status, details=details or {}, cost=cost,
        duration_ms=10, error=error,
    )


class FakeClient:
    """Scripted LLM client: returns the next response from a queue."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def chat(self, messages, temperature=0.0, max_tokens=600):
        self.calls += 1
        assert self.responses, "FakeClient exhausted its scripted responses"
        response = self.responses.pop(0)
        return json.dumps(response) if isinstance(response, dict) else response


def _make_tool(name, result):
    tool = MagicMock()
    tool.name = name
    tool.description = f"Mock {name}"
    tool.parameters = {}
    tool.execute.return_value = ActionResult(
        action=name, status=result.status, details=result.details,
        cost=result.cost, duration_ms=result.duration_ms, error=result.error,
    )
    return tool


def _make_registry(tools):
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


def _decision(tool=None, done=False, params=None, summary=None):
    if done:
        return {'thought': 'finished', 'done': True, 'summary': summary or 'done'}
    return {'thought': 'proceed', 'tool': tool, 'params': params or {}}


class TestAgentLoopHappyPath:
    def test_query_then_done(self):
        client = FakeClient([
            _decision(tool="query_jobs"),
            _decision(done=True, summary="found 3 jobs"),
        ])
        registry = _make_registry([_make_tool("query_jobs", _result(details={"count": 3}))])
        loop = AgentLoop(goal="count jobs", registry=registry, client=client)
        result = loop.run()
        assert result["status"] == "completed"
        assert result["summary"] == "found 3 jobs"
        assert result["actions"] == ["query_jobs"]
        assert result["tool_calls"] == 1
        assert result["llm_calls"] == 2


class TestAgentLoopSelfCorrection:
    def test_tool_error_then_adapt(self):
        failing = _make_tool("enrich_batch", _result(status="error", error="timeout"))
        ok = _make_tool("query_jobs", _result(details={"count": 1}))
        client = FakeClient([
            _decision(tool="enrich_batch"),
            _decision(tool="query_jobs"),
            _decision(done=True, summary="adapted ok"),
        ])
        registry = _make_registry([failing, ok])
        loop = AgentLoop(goal="get jobs", registry=registry, client=client)
        result = loop.run()
        assert result["status"] == "completed"
        assert result["actions"] == ["enrich_batch", "query_jobs"]
        assert any("failed: timeout" in t["observation"] for t in result["trace"])

    def test_tool_blocked_after_two_failures(self):
        failing = _make_tool("enrich_batch", _result(status="error", error="boom"))
        ok = _make_tool("query_jobs", _result(details={"count": 1}))
        client = FakeClient([
            _decision(tool="enrich_batch"),
            _decision(tool="enrich_batch"),
            _decision(tool="enrich_batch"),
            _decision(done=True, summary="switched away"),
        ])
        registry = _make_registry([failing, ok])
        loop = AgentLoop(goal="get jobs", registry=registry, client=client)
        result = loop.run()
        assert failing.execute.call_count == 2
        assert result["status"] == "completed"

    def test_unknown_tool_feedback(self):
        ok = _make_tool("query_jobs", _result(details={"count": 1}))
        client = FakeClient([
            _decision(tool="not_a_real_tool"),
            _decision(tool="query_jobs"),
            _decision(done=True),
        ])
        registry = _make_registry([ok])
        loop = AgentLoop(goal="get jobs", registry=registry, client=client)
        result = loop.run()
        assert result["status"] == "completed"
        assert "Unknown tool 'not_a_real_tool'" in [t["observation"] for t in result["trace"]]


class TestAgentLoopTermination:
    def test_malformed_json_twice_errors(self):
        client = FakeClient([
            "not json at all",
            "still not json",
        ])
        registry = _make_registry([])
        loop = AgentLoop(goal="get jobs", registry=registry, client=client)
        result = loop.run()
        assert result["status"] == "error"
        assert result["tool_calls"] == 0

    def test_malformed_then_valid_recovers(self):
        ok = _make_tool("query_jobs", _result(details={"count": 1}))
        client = FakeClient([
            "garbage",
            _decision(tool="query_jobs"),
            _decision(done=True),
        ])
        registry = _make_registry([ok])
        loop = AgentLoop(goal="get jobs", registry=registry, client=client)
        result = loop.run()
        assert result["status"] == "completed"

    def test_iteration_limit(self):
        client = FakeClient([
            _decision(tool="query_jobs"),
            _decision(tool="query_jobs"),
            _decision(tool="query_jobs"),
            _decision(tool="query_jobs"),
        ])
        registry = _make_registry([_make_tool("query_jobs", _result(details={"count": 1}))])
        loop = AgentLoop(goal="get jobs", registry=registry, client=client, max_iterations=4)
        result = loop.run()
        assert result["status"] == "partial"
        assert "iteration limit" in result["summary"]
        assert result["tool_calls"] == 4


class TestAgentLoopBudget:
    def test_budget_exhaustion_stops_run(self):
        client = FakeClient([
            _decision(tool="query_jobs"),
            _decision(done=True),
        ])
        registry = _make_registry([_make_tool("query_jobs", _result(cost=0.05))])
        loop = AgentLoop(goal="get jobs", registry=registry, client=client, max_cost=0.03)
        result = loop.run()
        assert result["status"] == "partial"
        assert "budget" in result["summary"].lower()

    def test_llm_failure_raises_gracefully(self):
        class BrokenClient:
            def chat(self, messages, temperature=0.0, max_tokens=600):
                raise RuntimeError("network down")

        registry = _make_registry([_make_tool("query_jobs", _result())])
        loop = AgentLoop(goal="get jobs", registry=registry, client=BrokenClient())
        result = loop.run()
        assert result["status"] == "partial"
        assert "LLM call failed" in result["errors"][0]


class TestAgentLoopHelpers:
    def test_parse_decision_fenced_json(self):
        from joborion.agent.agent_loop import _parse_decision
        raw = '```json\n{"thought": "x", "tool": "query_jobs"}\n```'
        assert _parse_decision(raw)["tool"] == "query_jobs"

    def test_parse_decision_bare_text(self):
        from joborion.agent.agent_loop import _parse_decision
        assert _parse_decision("no json here") is None

    def test_system_prompt_lists_tools(self):
        registry = _make_registry([_make_tool("query_jobs", _result())])
        client = FakeClient([_decision(done=True)])
        loop = AgentLoop(goal="get jobs", registry=registry, client=client)
        prompt = loop._build_system_prompt()
        assert "query_jobs" in prompt
        assert "Goal: get jobs" in prompt
