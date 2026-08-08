"""Orchestrator — main agent loop for goal-driven pipeline execution.

Takes a user goal, plans the execution, and runs tools in sequence while
tracking budget, handling errors, and recording results.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from joborion.agent.planner import Planner, Plan
from joborion.agent.context import ContextManager
from joborion.agent.tools import ActionResult
from joborion.agent.registry import build_default_registry, ToolRegistry

log = logging.getLogger(__name__)

_APPLY_TOOLS = frozenset({"tailor_resume", "write_cover_letter", "convert_to_pdf"})


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
        auto: bool = False,
        yes: bool = False,
        semi: bool = False,
        prompt_fn: Callable[[str], str] | None = None,
    ) -> None:
        self.goal = goal
        self.max_cost = max_cost
        self.max_calls = max_calls
        self._accumulated_cost: float = 0.0
        self._call_count: int = 0
        self._error_count: int = 0
        self._planner = self._build_planner()
        self.context = ContextManager()
        self._registry = registry or build_default_registry()
        self._failed_tools: set[str] = set()
        self._auto = auto
        self._yes = yes
        self._semi = semi
        self._prompt = prompt_fn or input

    @staticmethod
    def _build_planner() -> Planner:
        """Create a Planner with LLM client if available, keyword fallback otherwise."""
        try:
            from joborion.llm import get_client
            client = get_client()
            return Planner(client=client)
        except Exception:
            return Planner()

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

            # Check gates in autonomous mode
            if self._auto:
                if not self._check_gate("cost"):
                    log.info("Skipping step '%s' after cost gate declined", step.tool)
                    continue
                if not self._check_gate("error_rate"):
                    log.info("Skipping step '%s' after error-rate gate declined", step.tool)
                    continue

            # Semi mode: approve before each application-related step
            if self._semi and step.tool in _APPLY_TOOLS and not self._check_gate("apply"):
                log.info("Skipping apply step '%s' after gate declined", step.tool)
                continue

            # Execute the tool
            try:
                result = self._registry.dispatch(step.tool, **step.params)
                self._call_count += 1
                self._accumulated_cost += result.cost

                if result.status == "error":
                    self._error_count += 1

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
                self._error_count += 1
                log.error(error_msg)
            except Exception as e:
                error_msg = f"Unexpected error in {step.tool}: {e}"
                errors.append(error_msg)
                self._error_count += 1
                log.error(error_msg)

        return {
            "status": "completed" if not errors else "partial",
            "plan": [s.description for s in plan.steps],
            "results": results,
            "total_cost": self._accumulated_cost,
            "errors": errors,
        }

    def execute_autonomous(self) -> dict:
        """Execute in autonomous mode: plan → execute → reflect → report.

        Returns:
            Dict with keys: status, plan, results, total_cost, errors,
            reflection, report.
        """
        # 1. Parse goal
        from joborion.agent.goal_parser import GoalParser
        parser = GoalParser()
        parsed = parser.parse(self.goal)

        # 2. Generate plan
        plan = self.plan()

        # 3. Execute
        result = self.execute()

        # 4. Reflect + report
        reflection, report = self._reflect_and_report(result, plan)

        return {
            "status": result["status"],
            "plan": [s.description for s in plan.steps],
            "results": result.get("results", []),
            "total_cost": self._accumulated_cost,
            "errors": result.get("errors", []),
            "reflection": reflection,
            "report": report,
            "parsed_goal": parsed,
        }

    def execute_agentic(self) -> dict:
        """Execute in agentic mode: dynamic ReAct loop → reflect → report.

        Uses the LLM to choose each tool based on observed results. Falls back
        to the deterministic autonomous path when no LLM client is available.

        Returns:
            Dict with keys: status, summary, trace, actions, results,
            total_cost, llm_calls, tool_calls, errors, reflection, report.
        """
        try:
            from joborion.llm import get_client
            client = get_client()
        except Exception as e:
            log.warning("No LLM client available for agentic mode; falling back to deterministic: %s", e)
            return self.execute_autonomous()

        from joborion.agent.agent_loop import AgentLoop
        loop = AgentLoop(
            goal=self.goal,
            registry=self._registry,
            client=client,
            max_cost=self.max_cost,
        )
        loop_result = loop.run()

        reflection, report = self._reflect_and_report(loop_result)

        return {
            "status": loop_result["status"],
            "summary": loop_result["summary"],
            "trace": loop_result["trace"],
            "actions": loop_result["actions"],
            "results": [a.action for a in loop.context.get_recent_actions()],
            "total_cost": loop_result["total_cost"],
            "llm_calls": loop_result["llm_calls"],
            "tool_calls": loop_result["tool_calls"],
            "errors": loop_result["errors"],
            "reflection": reflection,
            "report": report,
        }

    def _reflect_and_report(self, execution: dict, plan: Plan | None = None) -> tuple[dict | None, str]:
        """Reflect on a run and generate the human-readable report.

        Args:
            execution: Result dict from execute() or the agent loop.
            plan: The execution plan, if one was used (drives stage names).

        Returns:
            Tuple of (reflection dict or None, report string).
        """
        # Reflect (store reflection)
        reflection = None
        try:
            from joborion.agent.reflector import Reflector
            from joborion.database import get_connection, store_reflection
            conn = get_connection()
            reflector = Reflector(conn)
            if hasattr(self, "_run_id"):
                reflection = reflector.analyze_run(self._run_id)
                store_reflection(reflection, conn=conn)
        except Exception as e:
            log.warning("Reflection failed: %s", e)

        # Generate report
        from joborion.agent.reporter import RunReporter
        reporter = RunReporter()
        if plan is not None:
            stages = [
                {"name": step.tool, "status": "ok", "count": 1}
                for step in plan.steps
            ]
        else:
            stages = [
                {"name": action, "status": "ok", "count": 1}
                for action in execution.get("actions", [])
            ]
        report_data = {
            "goal": self.goal,
            "duration_s": 0.0,
            "total_cost": execution.get("total_cost", self._accumulated_cost),
            "stages": stages,
            "top_jobs": [],
            "errors": execution.get("errors", []),
            "lessons": reflection.get("recommendations", []) if reflection else [],
        }
        return reflection, reporter.generate(report_data)

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

    def _should_gate(self, gate_type: str) -> bool:
        """Check if a human-in-the-loop gate should trigger.

        Args:
            gate_type: One of "cost", "error_rate", "apply".

        Returns:
            True if gate should trigger (user needs to approve).
        """
        if self._yes:
            return False

        if gate_type == "cost":
            return self._accumulated_cost >= self.max_cost * 0.5
        elif gate_type == "error_rate":
            return self._error_rate() > 0.3
        elif gate_type == "apply":
            return self._semi

        return False

    def _check_gate(self, gate_type: str) -> bool:
        """Check a human-in-the-loop gate and prompt the user if it triggers.

        Args:
            gate_type: One of "cost", "error_rate", "apply".

        Returns:
            True if the step may proceed, False if the user declined.
        """
        if self._yes or not self._should_gate(gate_type):
            return True
        warning = self._gate_warning(gate_type)
        log.warning(warning)
        return self._confirm(f"{warning}\nProceed? [y/N]: ")

    def _gate_warning(self, gate_type: str) -> str:
        """Build a human-readable warning message for a triggered gate."""
        if gate_type == "cost":
            return (
                f"Cost gate triggered at ${self._accumulated_cost:.4f} / "
                f"${self.max_cost:.2f} (50% threshold)"
            )
        if gate_type == "error_rate":
            return f"Error rate gate triggered at {self._error_rate() * 100:.0f}%"
        if gate_type == "apply":
            return "Application gate: approve before submitting this application"
        return f"Gate '{gate_type}' triggered"

    def _confirm(self, prompt_text: str) -> bool:
        """Prompt the user for a yes/no answer."""
        try:
            raw = self._prompt(prompt_text)
        except (EOFError, KeyboardInterrupt):
            return False
        return raw.strip().lower() in ("y", "yes")

    def _error_rate(self) -> float:
        """Calculate current error rate."""
        if self._call_count == 0:
            return 0.0
        return self._error_count / self._call_count

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
