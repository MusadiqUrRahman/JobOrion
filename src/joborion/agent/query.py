"""Field-agnostic search query extraction from natural language goals.

Extracts the role terms from a goal like "find 10 remote accountant jobs"
for ANY field — no hardcoded tech keyword list. Strips filler words,
limits, salary and arrangement phrasing, then falls back to the profile's
target role when nothing substantive remains.
"""

from __future__ import annotations

import re

_FILLER_WORDS = frozenset({
    "a", "an", "the", "and", "or", "for", "of", "in", "at", "to", "with",
    "find", "look", "search", "looking", "job", "jobs", "role", "roles",
    "position", "positions", "opening", "openings", "vacancy", "vacancies",
    "remote", "onsite", "hybrid", "wfh", "apply", "applications", "me",
    "paying", "salary", "that", "which", "top", "best", "good", "great",
    "suitable", "get", "grab", "scrape", "discover", "my", "next",
    "some", "any", "just", "want", "would", "like", "please", "now",
})

_SALARY_PATTERN = re.compile(r"\$?\d+(?:\.\d+)?k?\+?")
_NUMBER_PATTERN = re.compile(r"\b\d+\b")


def _strip_noise(text: str) -> str:
    """Remove salary figures, standalone numbers, and filler words."""
    text = _SALARY_PATTERN.sub(" ", text)
    text = _NUMBER_PATTERN.sub(" ", text)
    words = [w for w in text.split() if w.lower() not in _FILLER_WORDS]
    return " ".join(words)


def _profile_target_role() -> str:
    """The user's configured target role, or an empty string."""
    try:
        from joborion.config import load_profile
        profile = load_profile()
    except Exception:
        return ""
    return ((profile.get("experience") or {}).get("target_role") or "").strip()


def extract_query(goal: str, fallback: str | None = None) -> str:
    """Extract a search query from a goal for any field.

    Args:
        goal: The user's goal text (e.g. "find 10 remote accountant jobs").
        fallback: Value to use when nothing substantive remains. When None,
            falls back to the profile's target role.

    Returns:
        The extracted query string (possibly empty).
    """
    cleaned = _strip_noise(goal).strip()
    if cleaned:
        return cleaned
    if fallback is not None:
        return fallback
    return _profile_target_role()
