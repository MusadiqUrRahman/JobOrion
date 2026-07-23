"""Orchestrator — main agent loop for goal-driven pipeline execution.

Takes a user goal, plans the execution, and runs tools in sequence while
tracking budget, handling errors, and recording results.
"""

from __future__ import annotations

import logging

from joborion.agent.planner import Planner, Plan
from joborion.agent.context import ContextManager
from joborion.agent.tools import ActionResult
from joborion.agent.registry import build_default_registry, ToolRegistry

log = logging.getLogger(__name__)


class BudgetExceeded(Exception):
    """Raised when the orchestrator's budget is exceeded."""


class Orchestrator:
    """Goal-driven pipeline orchestrator.

    Takes a user goal, generates an execution plan, and runs tools
    while tracking budget, handling errors, and recording results.
    """

    def __init__(
        self,
        goal: str,
        max_cost: float = 5.0,
        max_calls: int = 50,
        registry: ToolRegistry | None = None,
    ) -> None:
        self.goal = goal
        self.max_cost = max_cost
        self.max_calls = max_calls
        self._accumulated_cost: float = 0.0
        self._call_count: int = 0
        self._planner = Planner()
        self.context = ContextManager()
        self._registry = registry or build_default_registry()
        self._failed_tools: set[str] = set()

    def plan(self) -> Plan:
        """Generate an execution plan without running it.

        Returns:
            Plan with ordered steps and cost estimates.
        """
        return self._planner.plan(self.goal)

    def execute(self, dry_run: bool = False) -> dict:
        """Execute the plan.

        Args:
            dry_run: If True, return the plan without executing tools.

        Returns:
            Dict with keys: status, plan (list of step descriptions),
            results (list of ActionResults), total_cost, errors.
        """
        plan = self.plan()

        if dry_run:
            return {
                "status": "planned",
                "plan": [s.description for s in plan.steps],
                "results": [],
                "total_cost": 0.0,
                "errors": [],
            }

        results: list[ActionResult] = []
        errors: list[str] = []

        for step in plan.steps:
            # Check budget before each step
            self._check_budget()

            # Check if the tool has failed before
            if step.tool in self._failed_tools:
                log.warning("Skipping previously failed tool: %s", step.tool)
                continue

            # Execute the tool
            try:
                result = self._registry.dispatch(step.tool, **step.params)
                self._call_count += 1
                self._accumulated_cost += result.cost

                self._record_result(result)
                results.append(result)

                if result.status == "error":
                    errors.append(f"{step.tool}: {result.error}")
                    self._failed_tools.add(step.tool)
                    log.error("Tool '%s' failed: %s", step.tool, result.error)
                else:
                    log.info("Tool '%s' completed: %s", step.tool, result.status)

            except KeyError as e:
                error_msg = f"Tool not found: {e}"
                errors.append(error_msg)
                log.error(error_msg)
            except Exception as e:
                error_msg = f"Unexpected error in {step.tool}: {e}"
                errors.append(error_msg)
                log.error(error_msg)

        return {
            "status": "completed" if not errors else "partial",
            "plan": [s.description for s in plan.steps],
            "results": results,
            "total_cost": self._accumulated_cost,
            "errors": errors,
        }

    def _check_budget(self) -> None:
        """Raise BudgetExceeded if budget would be exceeded."""
        if self._accumulated_cost >= self.max_cost:
            raise BudgetExceeded(
                f"Budget exhausted: ${self._accumulated_cost:.4f} / ${self.max_cost:.2f}"
            )
        if self._call_count >= self.max_calls:
            raise BudgetExceeded(
                f"Call limit exhausted: {self._call_count} / {self.max_calls}"
            )

    def _record_result(self, result: ActionResult) -> None:
        """Record a tool result in context and cost ledger."""
        self.context.add_action(result)

        # Record to cost ledger if we have a run_id
        if result.cost > 0:
            try:
                from joborion.database import record_cost, start_run
                # Use a lazy-initialized run_id
                if not hasattr(self, "_run_id"):
                    self._run_id = start_run(goal=self.goal)
                record_cost(
                    run_id=self._run_id,
                    action=result.action,
                    tool=result.action,
                    cost_usd=result.cost,
                )
            except Exception:
                pass  # Don't let cost recording break execution
