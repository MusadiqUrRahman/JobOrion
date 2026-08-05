"""JobOrion search preferences: the 4-question preference questionnaire.

Writes ~/.joborion/preferences.yaml. Values drive sourcing intent (arrangement,
locations, job types, salary, seniority) across all providers.

Arrangement semantics:
  remote  -> worldwide remote-only search
  hybrid  -> concrete places, may include remote postings
  onsite  -> concrete places only
  all     -> no arrangement restriction
"""

from __future__ import annotations

from pathlib import Path

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from joborion import config

console = Console()

ARRANGEMENTS = ("remote", "hybrid", "onsite", "all")
JOB_TYPES = ("fulltime", "parttime", "contract", "internship", "all")
SENIORITY_LEVELS = ("entry", "mid", "senior", "lead", "staff")

DEFAULT_PREFERENCES: dict = {
    "arrangement": "all",
    "locations": ["worldwide"],
    "job_types": ["all"],
    "min_salary": None,
    "seniority": ["mid", "senior"],
    "sponsorship_ok": True,
    "industries": [],
}


def validate(prefs: dict) -> list[str]:
    """Return a list of problems with the preference dict (empty if valid)."""
    errors: list[str] = []

    arrangement = prefs.get("arrangement")
    if arrangement not in ARRANGEMENTS:
        errors.append(f"arrangement must be one of {', '.join(ARRANGEMENTS)}, got {arrangement!r}")

    for key in ("locations", "job_types", "seniority", "industries"):
        value = prefs.get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            errors.append(f"{key} must be a list of strings")

    if not set(prefs.get("job_types", [])).issubset(set(JOB_TYPES)):
        errors.append(f"job_types must be a subset of {', '.join(JOB_TYPES)}")
    if not set(prefs.get("seniority", [])).issubset(set(SENIORITY_LEVELS)):
        errors.append(f"seniority must be a subset of {', '.join(SENIORITY_LEVELS)}")

    min_salary = prefs.get("min_salary")
    if min_salary is not None and (not isinstance(min_salary, (int, float)) or min_salary < 0):
        errors.append("min_salary must be a non-negative number")

    return errors


def _merge_defaults(raw: dict) -> dict:
    """Merge raw preferences over the defaults so all keys are present."""
    merged = dict(DEFAULT_PREFERENCES)
    merged.update(raw)
    return merged


def load_preferences(path: Path | None = None) -> dict:
    """Load preferences, merging over defaults. Returns defaults if missing."""
    path = path or config.PREFERENCES_PATH
    if not path.exists():
        return dict(DEFAULT_PREFERENCES)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    prefs = _merge_defaults(raw)
    problems = validate(prefs)
    if problems:
        raise ValueError("Invalid preferences: " + "; ".join(problems))
    return prefs


def save_preferences(prefs: dict, path: Path | None = None) -> None:
    """Validate and write preferences to YAML (default: ~/.joborion/preferences.yaml)."""
    path = path or config.PREFERENCES_PATH
    problems = validate(prefs)
    if problems:
        raise ValueError("Invalid preferences: " + "; ".join(problems))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(prefs, sort_keys=False, allow_unicode=True), encoding="utf-8")


def apply_flags(
    prefs: dict,
    arrangement: str | None = None,
    locations: str | None = None,
    job_type: str | None = None,
    min_salary: int | None = None,
) -> dict:
    """Apply CLI flag overrides onto a preference dict (scripting mode)."""
    updated = dict(prefs)
    if arrangement is not None:
        updated["arrangement"] = arrangement.lower()
    if locations is not None:
        updated["locations"] = [v.strip().lower() for v in locations.split(",") if v.strip()] or ["worldwide"]
    if job_type is not None:
        updated["job_types"] = [v.strip().lower() for v in job_type.split(",") if v.strip()] or ["all"]
    if min_salary is not None:
        updated["min_salary"] = min_salary
    return updated


def _parse_list(value: str, default: list[str]) -> list[str]:
    """Parse a comma-separated prompt answer, lowercased, with a fallback."""
    items = [v.strip().lower() for v in value.split(",") if v.strip()]
    return items or list(default)


def run_preferences_wizard(existing: dict | None = None) -> dict:
    """Ask the 4 preference questions and return the resulting preference dict.

    Does not write anything — callers persist via save_preferences().
    Pre-fills each answer from `existing` (one Enter each to keep).
    """
    current = _merge_defaults(existing or {})

    console.print(Panel("[bold]Search Preferences[/bold]\nFour quick questions — one Enter each keeps your last answer."))

    arrangement = Prompt.ask(
        "1. Work arrangement?",
        choices=list(ARRANGEMENTS),
        default=current["arrangement"],
        show_choices=True,
    )

    locations_default = ", ".join(current["locations"]) if current["locations"] else "worldwide"
    locations_raw = Prompt.ask(
        "2. Preferred locations? (comma-separated; 'worldwide' = anywhere)",
        default=locations_default,
    )
    locations = [v.strip().lower() for v in locations_raw.split(",") if v.strip()] or ["worldwide"]

    job_types = _parse_list(
        Prompt.ask("3. Job types?", default=", ".join(current["job_types"])),
        ["all"],
    )

    min_salary_raw = Prompt.ask(
        "4. Minimum annual salary in USD? (blank for none)",
        default="" if current.get("min_salary") is None else str(current["min_salary"]),
    )
    min_salary = int(min_salary_raw) if min_salary_raw.strip() else None

    seniority = _parse_list(
        Prompt.ask("Other — seniority levels? (entry, mid, senior, lead, staff)",
                   default=", ".join(current["seniority"])),
        ["mid", "senior"],
    )

    sponsorship_ok = Confirm.ask(
        "Other — willing to take visa sponsorship / relocation?",
        default=bool(current.get("sponsorship_ok")),
    )

    industries = _parse_list(
        Prompt.ask("Other — preferred industries? (comma-separated, optional)",
                   default=", ".join(current.get("industries", []))),
        [],
    )

    prefs = {
        "arrangement": arrangement,
        "locations": locations,
        "job_types": job_types,
        "min_salary": min_salary,
        "seniority": seniority,
        "sponsorship_ok": sponsorship_ok,
        "industries": industries,
    }
    problems = validate(prefs)
    if problems:
        raise ValueError("Invalid preferences collected: " + "; ".join(problems))
    return prefs
