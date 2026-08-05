"""Search intent building: user preferences -> provider kwargs + filter flags.

Phase A scope: map arrangement/locations/job_types onto the legacy search modes
(remote/local/sponsorship/all) plus the filter flags used by providers and the
relevance gate. Phase C/D extend this with query evolution.
"""

from __future__ import annotations


def map_arrangement(prefs: dict) -> dict:
    """Translate preference arrangement into a legacy search mode + filter flags.

    Args:
        prefs: Preference dict (see joborion.wizard.preferences schema).

    Returns:
        Dict with keys: mode, remote_only, locations, job_types, min_salary,
        seniority, sponsorship_ok.
    """
    arrangement = prefs.get("arrangement", "all")

    if arrangement == "remote":
        mode, remote_only = "remote", True
    elif arrangement in ("hybrid", "onsite"):
        mode, remote_only = "local", False
    else:
        mode, remote_only = "all", False

    return {
        "mode": mode,
        "remote_only": remote_only,
        "locations": prefs.get("locations", ["worldwide"]),
        "job_types": prefs.get("job_types", ["all"]),
        "min_salary": prefs.get("min_salary"),
        "seniority": prefs.get("seniority", []),
        "sponsorship_ok": prefs.get("sponsorship_ok", True),
    }
