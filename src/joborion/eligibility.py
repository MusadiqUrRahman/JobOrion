"""Candidate eligibility engine: profile-driven rules for any country.

Pure logic module (no LLM calls, no I/O). Used by both the fit scorer
(during evaluate) and the apply location check so the same rules govern
every stage.

Search modes:
- "remote":        only remote / work-from-anywhere jobs.
- "local":         only jobs in the candidate's home country.
- "sponsorship":   remote + international jobs the candidate could take
                   (relocation-willing or already authorized there).
- "all":           everything; strict profile eligibility still applies.
"""

from __future__ import annotations

from dataclasses import dataclass

# Keywords that mark a posting as remote / location-independent
REMOTE_WORDS = ("remote", "anywhere", "work from home", "wfh", "distributed")

# Best-effort spelling -> canonical country map. Lowercase keys.
COMMON_COUNTRIES = {
    "us": "us", "usa": "us", "united states": "us", "u.s.": "us", "america": "us",
    "uk": "uk", "united kingdom": "uk", "britain": "uk", "england": "uk", "scotland": "uk",
    "canada": "canada",
    "germany": "germany",
    "france": "france",
    "australia": "australia",
    "india": "india",
    "pakistan": "pakistan",
    "uae": "uae", "united arab emirates": "uae", "dubai": "uae",
    "saudi arabia": "saudi arabia", "saudi": "saudi arabia",
    "qatar": "qatar",
    "bahrain": "bahrain",
    "kuwait": "kuwait",
    "oman": "oman",
    "netherlands": "netherlands",
    "singapore": "singapore",
    "ireland": "ireland",
    "japan": "japan",
    "china": "china",
    "poland": "poland",
    "brazil": "brazil",
    "mexico": "mexico",
    "philippines": "philippines",
    "bangladesh": "bangladesh",
    "sri lanka": "sri lanka",
    "nepal": "nepal",
    "egypt": "egypt",
    "turkey": "turkey",
    "nigeria": "nigeria",
    "kenya": "kenya",
    "south africa": "south africa",
    "vietnam": "vietnam",
    "indonesia": "indonesia",
    "malaysia": "malaysia",
    "new zealand": "new zealand",
    "spain": "spain",
    "italy": "italy",
    "switzerland": "switzerland",
    "sweden": "sweden",
    "norway": "norway",
    "denmark": "denmark",
    "finland": "finland",
    "belgium": "belgium",
    "austria": "austria",
    "portugal": "portugal",
    "romania": "romania",
    "ukraine": "ukraine",
    "south korea": "south korea", "korea": "south korea",
    "hong kong": "hong kong",
    "taiwan": "taiwan",
    "thailand": "thailand",
    "argentina": "argentina",
    "chile": "chile",
    "colombia": "colombia",
    "israel": "israel",
    "lithuania": "lithuania",
    "latvia": "latvia",
    "estonia": "estonia",
    "czech republic": "czech republic", "czechia": "czech republic",
    "greece": "greece",
    "hungary": "hungary",
    "croatia": "croatia",
    "bulgaria": "bulgaria",
    "serbia": "serbia",
    "georgia": "georgia",
    "armenia": "armenia",
    "moldova": "moldova",
    "albania": "albania",
    "morocco": "morocco",
    "tunisia": "tunisia",
    "jordan": "jordan",
    "lebanon": "lebanon",
    "iraq": "iraq",
    "iran": "iran",
    "afghanistan": "afghanistan",
    "kazakhstan": "kazakhstan",
    "uzbekistan": "uzbekistan",
    "peru": "peru",
    "venezuela": "venezuela",
    "ecuador": "ecuador",
    "uruguay": "uruguay",
    "paraguay": "paraguay",
    "costa rica": "costa rica",
    "panama": "panama",
    "dominican republic": "dominican republic",
    "jamaica": "jamaica",
    "ethiopia": "ethiopia",
    "ghana": "ghana",
    "cameroon": "cameroon",
    "ivory coast": "ivory coast", "cote d'ivoire": "ivory coast",
    "angola": "angola",
    "mozambique": "mozambique",
    "zimbabwe": "zimbabwe",
    "zambia": "zambia",
    "tanzania": "tanzania",
    "uganda": "uganda",
    "rwanda": "rwanda",
    "europe": "europe",
}

VALID_MODES = ("remote", "local", "sponsorship", "all")

# Stable reason codes surfaced to the UI and stored in the DB
REASON_NOT_REMOTE = "not_remote"
REASON_LOCATION = "not_eligible_location"
REASON_SPONSORSHIP = "requires_sponsorship"
REASON_COUNTRY_RESTRICTED = "country_restricted"


def location_country(loc: str) -> str | None:
    """Best-effort canonical country extracted from a location string."""
    loc = loc.lower()
    for token, code in COMMON_COUNTRIES.items():
        if token in loc:
            return code
    return None


def classify_location(location: str | None) -> dict:
    """Classify a job location string.

    Returns:
        {"is_remote": bool, "country": str | None, "has_country": bool}
    """
    if not location:
        return {"is_remote": False, "country": None, "has_country": False}

    loc = location.lower()
    is_remote = any(r in loc for r in REMOTE_WORDS)
    country = location_country(loc)
    return {
        "is_remote": is_remote,
        "country": country,
        "has_country": country is not None,
    }


@dataclass(frozen=True)
class EligibilityResult:
    """Outcome of an eligibility check."""

    eligible: bool
    reason: str | None = None
    suggestion: str | None = None


def constraints_from_profile(profile: dict) -> dict:
    """Build the candidate constraint context used by rules and prompts.

    Tolerates missing keys in the profile (defaults to safe values).
    """
    personal = profile.get("personal", {})
    home_country = location_country(personal.get("country") or "") or (
        personal.get("country") or ""
    ).strip().lower()

    wa = profile.get("work_authorization", {})
    legally_authorized = wa.get("legally_authorized_to_work")
    sponsorship_needed = wa.get("require_sponsorship", True)
    work_permit_type = wa.get("work_permit_type", "")

    if legally_authorized is None:
        work_auth = "unknown"
    elif legally_authorized:
        work_auth = f"legally authorized in {home_country or 'home country'}"
    else:
        work_auth = "not legally authorized to work"

    # Authorized countries: explicit list, else home country only.
    authorized = []
    for c in wa.get("authorized_countries", []):
        if not c or not c.strip():
            continue
        authorized.append(location_country(c) or c.strip().lower())
    if not authorized and home_country:
        authorized = [home_country]

    return {
        "home_country": home_country,
        "authorized_countries": authorized,
        "sponsorship_needed": bool(sponsorship_needed),
        "relocation_willing": bool(wa.get("relocation_willing", False)),
        "legally_authorized": bool(legally_authorized) if legally_authorized is not None else False,
        "work_permit_type": work_permit_type,
        "candidate_location": ", ".join(
            p for p in [personal.get("city"), personal.get("province_state"), home_country] if p
        ) or "unknown",
        "work_auth": work_auth,
        "sponsorship": "yes" if sponsorship_needed else "no",
        "country": home_country,
    }


def _suggestion(reason: str, country: str | None, mode: str) -> str:
    """Human-readable, actionable suggestion for a rejection reason."""
    if reason == REASON_NOT_REMOTE:
        return (
            f"This role requires onsite/hybrid attendance, but your search is in "
            f"{mode!r} mode (remote only). Run with --mode all to include such roles."
        )
    if reason == REASON_LOCATION:
        return (
            f"This role is onsite in {country or 'another country'}, which your profile "
            f"does not cover. Use --mode sponsorship to include international roles "
            f"you're willing to relocate for, or --mode local to stick to your home country."
        )
    if reason == REASON_COUNTRY_RESTRICTED:
        return (
            f"This role is listed as remote but restricted to {country or 'a specific country'}. "
            f"Switch to --mode sponsorship if you're willing to relocate there, or update "
            f"your authorized_countries in the profile."
        )
    if reason == REASON_SPONSORSHIP:
        return (
            "This role requires work authorization you don't currently hold. Check your "
            "profile's work_authorization, or look for roles that explicitly offer visa "
            "sponsorship."
        )
    return "Review your profile's country, work authorization, and relocation preferences."


def evaluate_job(job: dict, profile: dict, mode: str = "all") -> EligibilityResult:
    """Evaluate whether a job is eligible for the candidate.

    Args:
        job: Job dict with a "location" key (may be None/empty).
        profile: User profile dict.
        mode: Search mode — one of VALID_MODES.

    Returns:
        EligibilityResult with reason/suggestion populated when ineligible.
    """
    if mode not in VALID_MODES:
        mode = "all"

    c = constraints_from_profile(profile)
    loc = classify_location(job.get("location"))
    home = c["home_country"]
    authorized = c["authorized_countries"]
    relocation = c["relocation_willing"]

    # No location info at all — can't rule out, let the LLM decide.
    if not loc["country"] and not loc["is_remote"]:
        return EligibilityResult(eligible=True)

    def _can_work_in(country: str) -> bool:
        return country in authorized or (country == home and home)

    # ----- remote-only mode -----
    if mode == "remote":
        if not loc["is_remote"]:
            return EligibilityResult(False, REASON_NOT_REMOTE, _suggestion(REASON_NOT_REMOTE, None, mode))
        if loc["country"] and not _can_work_in(loc["country"]):
            return EligibilityResult(
                False, REASON_COUNTRY_RESTRICTED,
                _suggestion(REASON_COUNTRY_RESTRICTED, loc["country"], mode),
            )
        return EligibilityResult(True)

    # ----- local mode -----
    if mode == "local":
        if loc["is_remote"] and not loc["country"]:
            return EligibilityResult(True)
        if loc["country"] and loc["country"] != home:
            return EligibilityResult(False, REASON_LOCATION, _suggestion(REASON_LOCATION, loc["country"], mode))
        if not loc["is_remote"] and loc["country"] == home:
            return EligibilityResult(True)
        # Remote restricted to home country
        if loc["is_remote"] and loc["country"] == home:
            return EligibilityResult(True)
        return EligibilityResult(False, REASON_LOCATION, _suggestion(REASON_LOCATION, loc["country"], mode))

    # ----- sponsorship mode: international is OK if relocatable/authorized -----
    if mode == "sponsorship":
        if loc["country"] and not _can_work_in(loc["country"]) and not relocation:
            return EligibilityResult(
                False, REASON_LOCATION,
                _suggestion(REASON_LOCATION, loc["country"], mode),
            )
        return EligibilityResult(True)

    # ----- all mode: strict profile eligibility -----
    if loc["is_remote"] and not loc["country"]:
        return EligibilityResult(True)

    if loc["country"]:
        can_work = _can_work_in(loc["country"])
        if not can_work:
            if loc["is_remote"]:
                return EligibilityResult(
                    False, REASON_COUNTRY_RESTRICTED,
                    _suggestion(REASON_COUNTRY_RESTRICTED, loc["country"], mode),
                )
            # Onsite in a country they can't work in
            if c["sponsorship_needed"] and not relocation:
                return EligibilityResult(False, REASON_LOCATION, _suggestion(REASON_LOCATION, loc["country"], mode))
            if not c["sponsorship_needed"]:
                return EligibilityResult(
                    False, REASON_SPONSORSHIP,
                    _suggestion(REASON_SPONSORSHIP, loc["country"], mode),
                )
            # Sponsorship not needed but still can't work there and not willing to relocate
            return EligibilityResult(False, REASON_LOCATION, _suggestion(REASON_LOCATION, loc["country"], mode))

    return EligibilityResult(True)
