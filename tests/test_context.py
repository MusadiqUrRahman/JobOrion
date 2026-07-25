"""Tests for ContextManager — working state and action history."""

from joborion.agent.context import ContextManager
from joborion.agent.tools import ActionResult


def _make_result(action="test_tool", status="ok", cost=0.0, error=None):
    return ActionResult(
        action=action,
        status=status,
        details={},
        cost=cost,
        duration_ms=0,
        error=error,
    )


class TestContextManager:
    def test_add_action(self):
        ctx = ContextManager()
        result = _make_result()
        ctx.add_action(result)
        assert ctx.action_count == 1

    def test_get_recent_actions_all(self):
        ctx = ContextManager()
        for i in range(5):
            ctx.add_action(_make_result(action=f"tool_{i}"))
        actions = ctx.get_recent_actions()
        assert len(actions) == 5

    def test_get_recent_actions_limited(self):
        ctx = ContextManager()
        for i in range(5):
            ctx.add_action(_make_result(action=f"tool_{i}"))
        actions = ctx.get_recent_actions(n=2)
        assert len(actions) == 2
        assert actions[0].action == "tool_3"
        assert actions[1].action == "tool_4"

    def test_get_working_state_empty(self):
        ctx = ContextManager()
        state = ctx.get_working_state()
        assert state["actions_completed"] == 0
        assert state["errors"] == 0
        assert state["total_cost"] == 0.0
        assert state["last_action"] is None

    def test_get_working_state_with_actions(self):
        ctx = ContextManager()
        ctx.add_action(_make_result(action="search", status="ok", cost=0.01))
        ctx.add_action(_make_result(action="score", status="error", cost=0.0))
        state = ctx.get_working_state()
        assert state["actions_completed"] == 2
        assert state["errors"] == 1
        assert state["total_cost"] == 0.01
        assert state["last_action"] == "score"
        assert state["last_status"] == "error"

    def test_compress_no_change_when_few(self):
        ctx = ContextManager(keep_recent=5)
        for i in range(3):
            ctx.add_action(_make_result(action=f"tool_{i}"))
        ctx.compress()
        assert ctx.action_count == 3

    def test_compress_keeps_recent(self):
        ctx = ContextManager(keep_recent=2)
        for i in range(5):
            ctx.add_action(_make_result(action=f"tool_{i}"))
        ctx.compress()
        assert ctx.action_count == 2
        actions = ctx.get_recent_actions()
        assert actions[0].action == "tool_3"
        assert actions[1].action == "tool_4"

    def test_compress_builds_summary(self):
        ctx = ContextManager(keep_recent=1)
        for i in range(4):
            ctx.add_action(_make_result(action=f"tool_{i}"))
        ctx.compress()
        state = ctx.get_working_state()
        assert "Previous 3 actions" in state["compressed_summary"]
        assert "3 ok" in state["compressed_summary"]

    def test_token_estimate_empty(self):
        ctx = ContextManager()
        assert ctx.token_estimate() == 0

    def test_token_estimate_grows(self):
        ctx = ContextManager()
        ctx.add_action(_make_result(action="a" * 100))
        small = ctx.token_estimate()
        ctx.add_action(_make_result(action="b" * 200))
        large = ctx.token_estimate()
        assert large > small
