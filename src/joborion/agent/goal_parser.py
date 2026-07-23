"""Goal Parser — converts natural language goals into structured parameters.

Parses user goals like "Find 10 remote Python jobs paying 150k+"
into structured dicts with query, filters, actions, and limits.
"""

from __future__ import annotations

import re


class GoalParser:
    """Parses natural language goals into structured execution parameters."""

    # Tech keywords to extract from goal text
    _TECH_KEYWORDS = [
        "python", "java", "javascript", "typescript", "go", "golang", "rust",
        "c++", "c#", "react", "angular", "vue", "node", "django", "fastapi",
        "rails", "spring", "docker", "kubernetes", "aws", "gcp", "azure",
        "data", "ml", "machine learning", "ai", "devops", "backend", "frontend",
        "full stack", "fullstack", "senior", "junior", "lead", "staff",
        "principal", "architect", "engineer", "developer", "sre", "platform",
    ]

    # Keywords that signal high minimum score
    _HIGH_SCORE_KEYWORDS = ["best", "top", "high", "excellent", "senior"]
    _GOOD_SCORE_KEYWORDS = ["good", "solid", "strong"]

    def parse(self, goal: str) -> dict:
        """Parse a natural language goal into structured parameters.

        Args:
            goal: User's goal string.

        Returns:
            Dict with keys: query, filters, actions, limits.
        """
        goal_lower = goal.lower()

        query = self._extract_query(goal_lower)
        filters = self._extract_filters(goal_lower)
        actions = self._extract_actions(goal_lower)
        limits = self._extract_limits(goal_lower)

        return {
            "query": query,
            "filters": filters,
            "actions": actions,
            "limits": limits,
        }

    def _extract_query(self, goal_lower: str) -> str:
        """Extract search query terms from goal."""
        found = [kw for kw in self._TECH_KEYWORDS if kw in goal_lower]
        return " ".join(found) if found else ""

    def _extract_filters(self, goal_lower: str) -> dict:
        """Extract filters (remote, salary, min_score)."""
        remote = any(kw in goal_lower for kw in ["remote", "work from home", "wfh", "anywhere"])
        min_salary = self._extract_salary(goal_lower)
        min_score = self._extract_min_score(goal_lower)

        return {
            "remote": remote,
            "min_salary": min_salary,
            "min_score": min_score,
        }

    def _extract_salary(self, goal_lower: str) -> int | None:
        """Extract salary threshold from goal text."""
        # Match patterns like "150k", "$150k", "150000", "$150,000"
        patterns = [
            r"\$?(\d+)k\+?",
            r"\$?(\d{2,3}),?000\+?",
            r"pay(?:ing|s)?\s+\$?(\d+)k",
            r"salary\s+\$?(\d+)k",
        ]
        for pattern in patterns:
            match = re.search(pattern, goal_lower)
            if match:
                num = int(match.group(1))
                # If followed by 'k', multiply by 1000
                if "k" in goal_lower[match.start():match.end() + 1]:
                    return num * 1000
                # If 3 digits, assume k (e.g., 150 → 150000)
                if num < 1000:
                    return num * 1000
                return num
        return None

    def _extract_min_score(self, goal_lower: str) -> int:
        """Extract minimum score from goal text."""
        if any(kw in goal_lower for kw in self._HIGH_SCORE_KEYWORDS):
            return 8
        if any(kw in goal_lower for kw in self._GOOD_SCORE_KEYWORDS):
            return 7
        return 7

    def _extract_actions(self, goal_lower: str) -> dict:
        """Determine which actions to enable based on goal text."""
        # Default: search + details + evaluate
        actions = {
            "search": True,
            "details": True,
            "evaluate": True,
            "tailor": False,
            "letter": False,
            "export": False,
        }

        # If "apply" is mentioned, enable everything
        if any(kw in goal_lower for kw in ["apply", "submit", "application"]):
            actions = {k: True for k in actions}

        # If "tailor" or "resume" mentioned, enable tailor
        elif any(kw in goal_lower for kw in ["tailor", "resume", "customize"]):
            actions["tailor"] = True
            actions["letter"] = True
            actions["export"] = True

        # If "cover" or "letter" mentioned, enable letter
        elif any(kw in goal_lower for kw in ["cover", "letter"]):
            actions["letter"] = True

        return actions

    def _extract_limits(self, goal_lower: str) -> dict:
        """Extract numeric limits from goal text."""
        max_jobs = None
        max_applications = None

        # Match "find 10 jobs", "5 python jobs", etc.
        job_match = re.search(r"find\s+(\d+)\s+", goal_lower)
        if job_match:
            max_jobs = int(job_match.group(1))

        # Match "apply to 5", "top 5", etc.
        apply_match = re.search(r"apply\s+to\s+(?:best\s+)?(\d+)", goal_lower)
        if apply_match:
            max_applications = int(apply_match.group(1))
        else:
            top_match = re.search(r"top\s+(\d+)", goal_lower)
            if top_match:
                max_applications = int(top_match.group(1))

        return {
            "max_jobs": max_jobs,
            "max_applications": max_applications,
        }
