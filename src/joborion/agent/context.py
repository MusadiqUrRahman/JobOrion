"""Context Manager — manages working state and action history for the orchestrator.

Tracks all actions taken during a run, provides summaries of progress,
and compresses old actions to manage context size.
"""

from __future__ import annotations

from joborion.agent.tools import ActionResult


class ContextManager:
    """Manages working context for the orchestrator.

    Tracks action history, provides progress summaries, and compresses
    old actions to keep context manageable.
    """

    def __init__(self, keep_recent: int = 5) -> None:
        self._actions: list[ActionResult] = []
        self._keep_recent = keep_recent
        self._compressed_summary: str = ""

    @property
    def action_count(self) -> int:
        """Total number of recorded actions."""
        return len(self._actions)

    def add_action(self, result: ActionResult) -> None:
        """Record an action result.

        Args:
            result: The ActionResult from a tool execution.
        """
        self._actions.append(result)

    def get_recent_actions(self, n: int | None = None) -> list[ActionResult]:
        """Get the most recent N actions.

        Args:
            n: Number of actions to return. None returns all.

        Returns:
            List of recent ActionResult objects.
        """
        if n is None:
            return list(self._actions)
        return list(self._actions[-n:])

    def get_working_state(self) -> dict:
        """Get a summary of current progress.

        Returns:
            Dict with keys: actions_completed, errors, total_cost,
            stages_completed, last_action.
        """
        errors = sum(1 for a in self._actions if a.status == "error")
        total_cost = sum(a.cost for a in self._actions)
        stages = list({a.action for a in self._actions if a.status == "ok"})
        last = self._actions[-1] if self._actions else None

        return {
            "actions_completed": len(self._actions),
            "errors": errors,
            "total_cost": total_cost,
            "stages_completed": stages,
            "last_action": last.action if last else None,
            "last_status": last.status if last else None,
            "compressed_summary": self._compressed_summary,
        }

    def compress(self, keep_recent: int | None = None) -> None:
        """Compress old actions into a summary, keeping recent ones.

        Args:
            keep_recent: How many recent actions to keep. Defaults to self._keep_recent.
        """
        k = keep_recent if keep_recent is not None else self._keep_recent
        if len(self._actions) <= k:
            return

        old_actions = self._actions[:-k]
        recent_actions = self._actions[-k:]

        # Build summary of old actions
        ok_count = sum(1 for a in old_actions if a.status == "ok")
        err_count = sum(1 for a in old_actions if a.status == "error")
        total_cost = sum(a.cost for a in old_actions)
        tools_used = list({a.action for a in old_actions})

        self._compressed_summary = (
            f"Previous {len(old_actions)} actions: "
            f"{ok_count} ok, {err_count} errors, "
            f"${total_cost:.4f} cost, tools: {', '.join(tools_used)}"
        )
        self._actions = recent_actions

    def token_estimate(self) -> int:
        """Estimate the number of tokens used by the current context.

        Rough heuristic: ~4 chars per token for English text.
        """
        total_chars = 0
        for action in self._actions:
            total_chars += len(action.action)
            total_chars += len(str(action.details))
            if action.error:
                total_chars += len(action.error)
        total_chars += len(self._compressed_summary)
        return total_chars // 4
