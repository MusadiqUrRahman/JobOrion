"""Planner — decomposes goals into ordered tool execution steps.

Takes a natural language goal and produces a Plan with ordered PlanSteps,
each mapped to a specific tool with parameters and cost estimates.
Supports LLM-powered planning with keyword-based fallback.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class PlanStep:
    """A single step in an execution plan.

    Attributes:
        tool: Tool name to dispatch.
        params: Parameters to pass to the tool.
        description: Human-readable description of this step.
        cost_estimate: Estimated USD cost.
        duration_estimate_ms: Estimated duration in milliseconds.
        depends_on: Index of step this depends on (None = no dependency).
    """
    tool: str
    params: dict
    description: str
    cost_estimate: float = 0.0
    duration_estimate_ms: int = 0
    depends_on: int | None = None


@dataclass
class Plan:
    """A complete execution plan with ordered steps.

    Attributes:
        goal: The original user goal.
        steps: Ordered list of PlanSteps.
        total_cost: Sum of all step cost estimates.
        total_duration_ms: Sum of all step duration estimates.
    """
    goal: str
    steps: list[PlanStep] = field(default_factory=list)

    @property
    def total_cost(self) -> float:
        return sum(s.cost_estimate for s in self.steps)

    @property
    def total_duration_ms(self) -> int:
        return sum(s.duration_estimate_ms for s in self.steps)


# Keyword-to-tool mapping for goal parsing
_GOAL_KEYWORDS: dict[str, list[str]] = {
    "search": ["find", "search", "discover", "scrape", "jobs"],
    "providers": ["providers", "all sources", "multi-source"],
    "details": ["enrich", "detail", "description", "apply url"],
    "evaluate": ["score", "rating", "fit", "rank"],
    "tailor": ["tailor", "resume", "customize"],
    "letter": ["cover letter", "cover"],
    "export": ["pdf", "convert"],
}

# Tool sequences per pipeline stage
_STAGE_TOOLS: dict[str, list[tuple[str, dict, str, float, int]]] = {
    "search": [
        ("scrape_jobspy", {}, "Search job boards via JobSpy", 0.0, 30000),
        ("scrape_workday", {}, "Search corporate career sites", 0.0, 20000),
        ("scrape_ai_sites", {}, "AI-powered site scraping", 0.0, 15000),
    ],
    "providers": [
        ("search_providers", {"max_results": 25}, "Search all configured job sources", 0.0, 60000),
    ],
    "details": [
        ("enrich_batch", {"limit": 100}, "Fetch full job descriptions", 0.0, 45000),
    ],
    "evaluate": [
        ("score_batch", {}, "Score all enriched jobs against resume", 0.0, 60000),
    ],
    "tailor": [
        ("tailor_resume", {"min_score": 7}, "Generate tailored resumes for top jobs", 0.0, 30000),
    ],
    "letter": [
        ("write_cover_letter", {"min_score": 7}, "Write cover letters for top jobs", 0.0, 20000),
    ],
    "export": [
        ("convert_to_pdf", {}, "Convert documents to PDF", 0.0, 10000),
    ],
}


_KNOWN_TOOLS: list[dict[str, str]] = [
    {"name": "scrape_jobspy", "description": "Search job boards via JobSpy (LinkedIn, Indeed, etc.)", "params": "search_query (optional), location (optional), remote_only (optional)"},
    {"name": "scrape_workday", "description": "Search corporate career sites (Workday)", "params": "search_query (optional), limit (optional)"},
    {"name": "scrape_ai_sites", "description": "AI-powered scraping of career pages", "params": "search_query (optional), limit (optional)"},
    {"name": "search_providers", "description": "Search all configured job sources in one pass", "params": "query (optional), remote (optional), min_salary (optional), max_results (optional)"},
    {"name": "enrich_single_job", "description": "Enrich a single job by URL with full description", "params": "url (required)"},
    {"name": "enrich_batch", "description": "Enrich multiple jobs with full descriptions", "params": "limit (optional)"},
    {"name": "score_single_job", "description": "Score a single job by URL against resume", "params": "url (required)"},
    {"name": "score_batch", "description": "Score multiple jobs against resume", "params": "limit (optional)"},
    {"name": "tailor_resume", "description": "Generate tailored resume for a job", "params": "url (required), min_score (optional)"},
    {"name": "write_cover_letter", "description": "Write cover letter for a job", "params": "url (required), min_score (optional)"},
    {"name": "convert_to_pdf", "description": "Convert documents to PDF", "params": "input_path (required)"},
    {"name": "query_jobs", "description": "Query jobs from the database with filters", "params": "stage (optional), min_score (optional), limit (optional)"},
    {"name": "get_job_detail", "description": "Get full details for a specific job by URL", "params": "url (required)"},
    {"name": "get_pipeline_stats", "description": "Get pipeline statistics and job counts by stage", "params": "none"},
]

_LLM_SYSTEM_PROMPT = """You are a job search pipeline planner. Given a user goal, produce a JSON array of execution steps.

Available tools:
{tools}

For each step, output a JSON object with:
- "tool": tool name (must match exactly)
- "params": dict of parameters to pass
- "description": human-readable description of this step

Rules:
- Order steps logically: search → details → evaluate → tailor → letter → export
- Use search_query parameter for search tools when the goal mentions specific skills/roles
- Use min_score=8 for "best/top/senior" goals, min_score=7 for "good" goals
- Only include tools relevant to the goal
- Return ONLY the JSON array, no other text

Example for "find senior Python jobs":
[
  {{"tool": "scrape_jobspy", "params": {{"search_query": "senior python"}}, "description": "Search job boards for senior Python roles"}},
  {{"tool": "scrape_workday", "params": {{"search_query": "senior python"}}, "description": "Search corporate career sites for senior Python roles"}},
  {{"tool": "enrich_batch", "params": {{"limit": 100}}, "description": "Enrich discovered jobs with full descriptions"}},
  {{"tool": "score_batch", "params": {{}}, "description": "Score all enriched jobs against resume"}}
]"""


class LLMPlanner:
    """LLM-powered planner that decomposes goals into tool execution steps.

    Uses an LLM client to understand natural language goals and produce
    structured execution plans. Falls back to None on any failure so
    the caller can use the keyword planner.
    """

    def __init__(self, client: object) -> None:
        self._client = client

    def plan(self, goal: str) -> Plan | None:
        """Generate an execution plan using the LLM.

        Args:
            goal: User's goal string.

        Returns:
            Plan with ordered steps, or None if LLM planning fails.
        """
        tools_text = "\n".join(
            f"- {t['name']}: {t['description']} (params: {t['params']})"
            for t in _KNOWN_TOOLS
        )
        system_prompt = _LLM_SYSTEM_PROMPT.format(tools=tools_text)

        try:
            raw = self._client.chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": goal},
                ],
                temperature=0.0,
                max_tokens=2048,
            )
        except Exception as e:
            log.warning("LLM planner call failed: %s", e)
            return None

        steps = _parse_llm_response(raw)
        if steps is None:
            return None

        plan_steps = _validate_steps(steps)
        if not plan_steps:
            return None

        return Plan(goal=goal, steps=plan_steps)


def _parse_llm_response(raw: str) -> list[dict] | None:
    """Extract a JSON array from LLM response text.

    Handles cases where the LLM wraps JSON in markdown code fences.
    """
    text = raw.strip()

    # Strip markdown code fences
    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find the first [ ... ] block
        bracket_match = re.search(r"\[.*\]", text, re.DOTALL)
        if bracket_match:
            try:
                data = json.loads(bracket_match.group(0))
            except json.JSONDecodeError:
                log.warning("Failed to parse LLM planner response as JSON")
                return None
        else:
            log.warning("No JSON array found in LLM planner response")
            return None

    if not isinstance(data, list):
        log.warning("LLM planner response is not a JSON array")
        return None

    return data


def _validate_steps(raw_steps: list[dict]) -> list[PlanStep]:
    """Validate and convert raw JSON steps into PlanStep objects.

    Filters out steps with unknown tools and fills in defaults.
    """
    known_tool_names = {t["name"] for t in _KNOWN_TOOLS}
    valid: list[PlanStep] = []

    for i, step in enumerate(raw_steps):
        tool = step.get("tool", "")
        if tool not in known_tool_names:
            log.warning("LLM planner suggested unknown tool '%s', skipping", tool)
            continue

        params = step.get("params", {})
        if not isinstance(params, dict):
            params = {}

        description = step.get("description", f"Execute {tool}")

        valid.append(PlanStep(
            tool=tool,
            params=params,
            description=description,
            cost_estimate=0.0,
            duration_estimate_ms=0,
            depends_on=i - 1 if i > 0 else None,
        ))

    return valid


class Planner:
    """Decomposes natural language goals into ordered execution plans.

    Tries LLM-powered planning first (if client provided), falls back to
    keyword-based stage detection and step building.
    """

    def __init__(self, client: object | None = None) -> None:
        self._client = client
        self._llm_planner = LLMPlanner(client) if client else None

    def plan(self, goal: str) -> Plan:
        """Generate an execution plan from a natural language goal.

        Tries LLM planner first if available, falls back to keyword matching.

        Args:
            goal: User's goal string (e.g., "Find 10 remote Python jobs").

        Returns:
            Plan with ordered steps, cost estimates, and duration estimates.
        """
        if self._llm_planner:
            llm_plan = self._llm_planner.plan(goal)
            if llm_plan and llm_plan.steps:
                log.info("LLM planner produced %d steps", len(llm_plan.steps))
                return llm_plan
            log.info("LLM planner returned no steps, falling back to keyword planner")

        goal_lower = goal.lower()
        stages = self._detect_stages(goal_lower)
        steps = self._build_steps(stages, goal_lower)
        return Plan(goal=goal, steps=steps)

    def _detect_stages(self, goal_lower: str) -> list[str]:
        """Detect which pipeline stages are needed from the goal text."""
        detected = []

        # Check for stage keywords
        for stage, keywords in _GOAL_KEYWORDS.items():
            if any(kw in goal_lower for kw in keywords):
                detected.append(stage)

        # If no specific stages detected, default to search + details + evaluate
        if not detected:
            detected = ["search", "details", "evaluate"]

        # Ensure stages are in pipeline order
        stage_order = ["search", "providers", "details", "evaluate", "tailor", "letter", "export"]
        detected = [s for s in stage_order if s in detected]

        return detected

    def _build_steps(self, stages: list[str], goal_lower: str) -> list[PlanStep]:
        """Build PlanSteps for the detected stages."""
        steps = []
        step_idx = 0

        for stage in stages:
            if stage not in _STAGE_TOOLS:
                continue
            for tool, params, desc, cost, duration in _STAGE_TOOLS[stage]:
                # Apply goal-specific params
                final_params = dict(params)
                if stage == "search":
                    # Extract query from goal
                    query = self._extract_query(goal_lower)
                    if query:
                        final_params["search_query"] = query
                elif stage == "providers":
                    query = self._extract_query(goal_lower)
                    if query:
                        final_params["query"] = query
                elif stage in ("tailor", "letter"):
                    # Check for min_score in goal
                    final_params["min_score"] = self._extract_min_score(goal_lower)

                steps.append(PlanStep(
                    tool=tool,
                    params=final_params,
                    description=desc,
                    cost_estimate=cost,
                    duration_estimate_ms=duration,
                    depends_on=step_idx - 1 if step_idx > 0 else None,
                ))
                step_idx += 1

        return steps

    def _extract_query(self, goal_lower: str) -> str:
        """Extract a search query from the goal text."""
        # Simple heuristic: look for job-related keywords
        tech_keywords = [
            "python", "java", "javascript", "typescript", "go", "rust", "c++",
            "react", "angular", "vue", "node", "django", "fastapi", "rails",
            "data", "ml", "machine learning", "ai", "devops", "backend", "frontend",
            "full stack", "senior", "junior", "lead", "staff", "principal",
        ]
        found = [kw for kw in tech_keywords if kw in goal_lower]
        return " ".join(found) if found else ""

    def _extract_min_score(self, goal_lower: str) -> int:
        """Extract minimum score threshold from goal text."""
        if "high" in goal_lower or "best" in goal_lower or "top" in goal_lower:
            return 8
        if "good" in goal_lower:
            return 7
        return 7  # default
