"""Planner — decomposes goals into ordered tool execution steps.

Takes a natural language goal and produces a Plan with ordered PlanSteps,
each mapped to a specific tool with parameters and cost estimates.
"""

from __future__ import annotations

from dataclasses import dataclass, field


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
    "details": ["enrich", "detail", "description", "apply url"],
    "evaluate": ["score", "rating", "fit", "rank"],
    "tailor": ["tailor", "resume", "customize"],
    "letter": ["cover letter", "cover"],
    "export": ["pdf", "convert"],
}

# Tool sequences per pipeline stage
_STAGE_TOOLS: dict[str, list[tuple[str, dict, str, float, int]]] = {
    "search": [
        ("search_jobspy", {}, "Search job boards via JobSpy", 0.0, 30000),
        ("search_workday", {}, "Search corporate career sites", 0.0, 20000),
        ("search_ai_sites", {}, "AI-powered site scraping", 0.0, 15000),
    ],
    "details": [
        ("fetch_details", {"limit": 100}, "Fetch full job descriptions", 0.0, 45000),
    ],
    "evaluate": [
        ("evaluate_jobs", {}, "Score all enriched jobs against resume", 0.0, 60000),
    ],
    "tailor": [
        ("tailor_resume", {"min_score": 7}, "Generate tailored resumes for top jobs", 0.0, 30000),
    ],
    "letter": [
        ("write_letter", {"min_score": 7}, "Write cover letters for top jobs", 0.0, 20000),
    ],
    "export": [
        ("export_pdf", {}, "Convert documents to PDF", 0.0, 10000),
    ],
}


class Planner:
    """Decomposes natural language goals into ordered execution plans.

    Analyzes the goal text for keywords indicating which pipeline stages
    are needed, then builds an ordered plan with cost and duration estimates.
    """

    def plan(self, goal: str) -> Plan:
        """Generate an execution plan from a natural language goal.

        Args:
            goal: User's goal string (e.g., "Find 10 remote Python jobs").

        Returns:
            Plan with ordered steps, cost estimates, and duration estimates.
        """
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
        stage_order = ["search", "details", "evaluate", "tailor", "letter", "export"]
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
