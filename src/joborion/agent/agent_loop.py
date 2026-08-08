"""Dynamic agent loop — ReAct-style tool selection driven by LLM observations.

Unlike the deterministic planner (which builds a fixed plan up front), the
agent loop lets the LLM pick the next tool at each step based on the observed
result of the previous action. It self-corrects on tool errors, blocks tools
that fail repeatedly, and stops when the goal is met or budget/iteration
limits are reached.

Architecture principle: determinism by default, agency by necessity. The
orchestrator only runs this loop when the user explicitly requests agentic
mode and an LLM client is available; otherwise it falls back to the
deterministic plan.
"""

from __future__ import annotations

import json
import logging
import re

from joborion.agent.context import ContextManager
from joborion.agent.registry import ToolRegistry
from joborion.agent.tools import ActionResult

log = logging.getLogger(__name__)

_MAX_MALFORMED = 2
_BLOCK_AFTER_FAILURES = 2


class BudgetExceeded(Exception):
    """Raised when the agent loop exceeds its budget or call limits."""


_SYSTEM_PROMPT = """You are JobOrion, an autonomous job-search agent. You act by calling tools one at a time.

Available tools:
{tools}

You MUST respond with exactly one JSON object and no other text. Choose one of two forms:

1. Call a tool:
{{"thought": "your reasoning", "tool": "<tool_name>", "params": {{...}}}}

2. Declare the goal satisfied:
{{"thought": "why the goal is satisfied", "done": true, "summary": "short summary of what was accomplished"}}

Rules:
- Only use tool names from the list above. Never invent a tool.
- Choose the next tool based on the goal and the previous observations.
- Prefer batch tools (enrich_batch, score_batch) over single-job tools when many jobs qualify.
- If a tool fails, do not call it again with the same parameters; try a different tool, adjust parameters, or declare the goal satisfied if appropriate.
- Stop as soon as the goal is reasonably met. Do not keep calling tools once the goal is satisfied.
- Never call apply-related tools (tailor_resume, write_cover_letter, convert_to_pdf) unless the goal explicitly asks for tailoring, cover letters, or PDFs.

Goal: {goal}
"""


class AgentLoop:
    """ReAct-style loop: LLM chooses each tool based on observed results.

    Attributes:
        goal: The user's goal string.
        max_iterations: Maximum number of LLM decision turns.
        max_cost: USD budget cap for tool + LLM costs combined.
        context: ContextManager tracking action history.
    """

    def __init__(
        self,
        goal: str,
        registry: ToolRegistry,
        client: object,
        max_iterations: int = 20,
        max_cost: float = 5.0,
        context: ContextManager | None = None,
    ) -> None:
        self.goal = goal
        self._registry = registry
        self._client = client
        self.max_iterations = max_iterations
        self.max_cost = max_cost
        self.context = context or ContextManager()
        self._cost: float = 0.0
        self._tool_calls: int = 0
        self._llm_calls: int = 0
        self._failures: dict[str, int] = {}
        self._blocked: set[str] = set()

    def run(self) -> dict:
        """Run the loop until done, iteration limit, or budget exhaustion.

        Returns:
            Dict with keys: status ("completed"|"partial"|"error"), summary,
            actions (list of action names), trace (list of per-turn dicts),
            total_cost, llm_calls, tool_calls, errors.
        """
        messages = [
            {"role": "system", "content": self._build_system_prompt()},
            {"role": "user", "content": self.goal},
        ]
        trace: list[dict] = []
        errors: list[str] = []
        status = "partial"
        summary = ""

        for _ in range(self.max_iterations):
            try:
                self._check_budget()
                raw = self._chat(messages)
            except BudgetExceeded as e:
                errors.append(str(e))
                summary = "Stopped: budget or call limit exhausted"
                status = "partial"
                break
            self._llm_calls += 1
            decision = _parse_decision(raw)

            if decision is None:
                trace.append({"thought": "", "observation": "Malformed LLM response"})
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": "Your response was not valid JSON. Respond with ONLY a JSON object "
                    "using the exact format specified in the system prompt.",
                })
                if _malformed_count(messages) >= _MAX_MALFORMED:
                    status = "error"
                    errors.append("Agent returned malformed JSON too many times")
                    summary = "Stopped: agent output could not be parsed"
                    break
                continue

            trace.append({"thought": decision.get("thought", "")})

            if decision.get("done"):
                status = "completed"
                summary = decision.get("summary", "Goal satisfied")
                trace[-1]["observation"] = summary
                break

            tool_name = decision.get("tool", "")
            params = decision.get("params", {}) if isinstance(decision.get("params"), dict) else {}

            if tool_name in self._blocked:
                observation = f"Tool '{tool_name}' is blocked after repeated failures"
                trace[-1]["observation"] = observation
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": f"{observation}. Choose a different tool or declare the goal satisfied.",
                })
                continue

            if self._registry.get_tool(tool_name) is None:
                observation = f"Unknown tool '{tool_name}'"
                trace[-1]["observation"] = observation
                messages.append({"role": "assistant", "content": raw})
                messages.append({
                    "role": "user",
                    "content": f"{observation}. Available tools: "
                    f"{', '.join(self._registry.list_tools())}. Choose one of these.",
                })
                continue

            try:
                result = self._registry.dispatch(tool_name, **params)
            except Exception as e:
                error_msg = f"{tool_name}: unexpected exception {e}"
                errors.append(error_msg)
                observation = f"{tool_name} raised an exception: {e}"
                self._register_failure(tool_name)
                trace[-1]["observation"] = observation
                messages.append({"role": "assistant", "content": raw})
                messages.append({"role": "user", "content": f"Observation: {observation}"})
                continue

            self._tool_calls += 1
            self._cost += result.cost
            self.context.add_action(result)

            observation = _summarize_result(result)
            trace[-1]["observation"] = observation
            messages.append({"role": "assistant", "content": raw})
            messages.append({"role": "user", "content": f"Observation: {observation}"})

            if result.status == "error":
                errors.append(f"{tool_name}: {result.error}")
                self._register_failure(tool_name)
            else:
                self._failures.pop(tool_name, None)
        else:
            summary = (
                f"Reached iteration limit ({self.max_iterations}) "
                f"with {self._tool_calls} tool calls"
            )

        return {
            "status": status,
            "summary": summary,
            "actions": [a.action for a in self.context.get_recent_actions()],
            "trace": trace,
            "total_cost": round(self._cost, 4),
            "llm_calls": self._llm_calls,
            "tool_calls": self._tool_calls,
            "errors": errors,
        }

    def _register_failure(self, tool_name: str) -> None:
        self._failures[tool_name] = self._failures.get(tool_name, 0) + 1
        if self._failures[tool_name] >= _BLOCK_AFTER_FAILURES:
            self._blocked.add(tool_name)

    def _build_system_prompt(self) -> str:
        tools_text = "\n".join(
            f"- {t['name']}: {t['description']} (params: {t['parameters']})"
            for t in self._registry.get_tool_descriptions()
        )
        return _SYSTEM_PROMPT.format(tools=tools_text, goal=self.goal)

    def _chat(self, messages: list[dict]) -> str:
        """Call the LLM client, returning the assistant text."""
        try:
            return self._client.chat(messages=messages, temperature=0.0, max_tokens=600)
        except Exception as e:
            log.warning("Agent loop LLM call failed: %s", e)
            raise BudgetExceeded(f"LLM call failed: {e}") from e

    def _check_budget(self) -> None:
        if self._cost >= self.max_cost:
            raise BudgetExceeded(
                f"Budget exhausted: ${self._cost:.4f}/{self.max_cost:.2f} used"
            )


def _malformed_count(messages: list[dict]) -> int:
    return sum(1 for m in messages if "was not valid JSON" in m.get("content", ""))


def _parse_decision(raw: str) -> dict | None:
    """Extract a JSON object from LLM output, tolerating code fences."""
    text = raw.strip()
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            try:
                data = json.loads(brace_match.group(0))
            except json.JSONDecodeError:
                return None
        else:
            return None
    if not isinstance(data, dict):
        return None
    return data


def _summarize_result(result: ActionResult) -> str:
    """Render an ActionResult as a compact observation for the LLM."""
    if result.status == "error":
        return f"{result.action} failed: {result.error}"
    details = result.details or {}
    compact = {k: v for k, v in details.items() if not isinstance(v, list)}
    if details.get("jobs"):
        compact["sample_jobs"] = details["jobs"][:5]
    return f"{result.action} ok ({result.duration_ms}ms): {compact}"
