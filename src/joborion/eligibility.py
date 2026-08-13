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

import re
from dataclasses import dataclass

# Keywords that mark a posting as remote / location-independent
REMOTE_WORDS = ("remote", "anywhere", "work from home", "wfh", "distributed")

# Best-effort spelling -> canonical country map. Lowercase keys.
COMMON_COUNTRIES = {
    "us": "us", "usa": "us", "united states": "us", "u.s.": "us", "america": "us",
    # US states (names only; two-letter codes collide as substrings, e.g. "in" in "India")
    "alabama": "us", "alaska": "us", "arizona": "us", "arkansas": "us",
    "california": "us", "colorado": "us", "connecticut": "us", "delaware": "us",
    "district of columbia": "us", "florida": "us", "hawaii": "us", "idaho": "us",
    "illinois": "us", "indiana": "us", "iowa": "us", "kansas": "us",
    "kentucky": "us", "louisiana": "us", "maine": "us", "maryland": "us",
    "massachusetts": "us", "michigan": "us", "minnesota": "us", "mississippi": "us",
    "missouri": "us", "montana": "us", "nebraska": "us", "nevada": "us",
    "new hampshire": "us", "new jersey": "us", "new mexico": "us", "new york": "us",
    "north carolina": "us", "north dakota": "us", "ohio": "us", "oklahoma": "us",
    "oregon": "us", "pennsylvania": "us", "rhode island": "us", "south carolina": "us",
    "south dakota": "us", "tennessee": "us", "texas": "us", "utah": "us",
    "vermont": "us", "virginia": "us", "washington": "us", "west virginia": "us",
    "wisconsin": "us", "wyoming": "us",
    "uk": "uk", "united kingdom": "uk", "britain": "uk", "england": "uk", "scotland": "uk",
    # Canadian provinces/territories (names only; "can" falls back below, "on"/"bc" collide)
    "alberta": "canada", "british columbia": "canada", "manitoba": "canada",
    "new brunswick": "canada", "newfoundland": "canada", "nova scotia": "canada",
    "ontario": "canada", "prince edward island": "canada", "quebec": "canada",
    "saskatchewan": "canada", "yukon": "canada", "northwest territories": "canada",
    "nunavut": "canada",
    "canada": "canada", "can": "canada",
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
    "deutschland": "germany",
    "luxembourg": "luxembourg",
    "ksa": "saudi arabia",
}

# City name -> canonical country (word-boundary match). Ambiguous cities
# (London, Cambridge, Windsor...) are omitted; jobs with them stay unresolved.
CITY_TO_COUNTRY = {
    # India
    "bengaluru": "india", "bangalore": "india", "mumbai": "india", "delhi": "india",
    "new delhi": "india", "kolkata": "india", "chennai": "india", "hyderabad": "india",
    "pune": "india", "gurgaon": "india", "noida": "india", "jaipur": "india",
    "ahmedabad": "india", "ajmer": "india", "rajkot": "india", "ranchi": "india",
    "jabalpur": "india", "jamshedpur": "india", "roorkee": "india", "kanpur": "india",
    "lucknow": "india", "indore": "india", "nagpur": "india", "surat": "india",
    "amritsar": "india", "bhubaneswar": "india", "kochi": "india", "coimbatore": "india",
    "wayanad": "india", "tiruchirappalli": "india", "kharagpur": "india",
    "gandhinagar": "india", "visakhapatnam": "india", "vadodara": "india",
    "patna": "india", "guwahati": "india", "dehradun": "india", "thane": "india",
    "nashik": "india", "mangalore": "india", "mysore": "india", "amet": "india",
    "anupgarh": "india", "hunterganj": "india", "krishnagiri": "india", "tikamgarh": "india",
    # Germany
    "munich": "germany", "münchen": "germany", "berlin": "germany", "hamburg": "germany",
    "cologne": "germany", "köln": "germany", "düsseldorf": "germany", "frankfurt": "germany",
    "stuttgart": "germany", "leipzig": "germany", "potsdam": "germany", "münster": "germany",
    "nürnberg": "germany", "hallbergmoos": "germany", "kaarst": "germany",
    "dresden": "germany", "hanover": "germany", "bremen": "germany", "dortmund": "germany",
    "essen": "germany", "bielefeld": "germany", "bonn": "germany", "freiburg": "germany",
    # UK
    "london": "uk", "manchester": "uk", "leeds": "uk", "belfast": "uk",
    "birmingham": "uk", "edinburgh": "uk", "glasgow": "uk", "bristol": "uk",
    "sheffield": "uk", "newcastle": "uk", "nottingham": "uk", "cardiff": "uk",
    "bradford": "uk", "leicester": "uk", "coventry": "uk", "plymouth": "uk",
    # Canada
    "toronto": "canada", "vancouver": "canada", "calgary": "canada", "edmonton": "canada",
    "winnipeg": "canada", "ottawa": "canada", "montreal": "canada", "montréal": "canada",
    "hamilton": "canada", "kitchener": "canada", "brampton": "canada",
    "regina": "canada", "saskatoon": "canada", "kamloops": "canada", "thunder bay": "canada",
    "sudbury": "canada", "mississauga": "canada", "oakville": "canada", "halifax": "canada",
    "st john's": "canada", "victoria": "canada", "kelowna": "canada",
    "swift current": "canada", "the pas": "canada", "corunna": "canada", "blyth": "canada",
    "enfield": "canada", "front of yonge": "canada", "fort good hope": "canada",
    "heart's content": "canada", "open hall": "canada", "three hills": "canada",
    "loch sport": "canada", "timmins": "canada", "collingwood": "canada",
    # Australia / NZ
    "sydney": "australia", "melbourne": "australia", "brisbane": "australia",
    "perth": "australia", "adelaide": "australia", "canberra": "australia",
    "gold coast": "australia", "banksmeadow": "australia", "bondi junction": "australia",
    "shepparton": "australia", "chinchilla": "australia", "auckland": "new zealand",
    "wellington": "new zealand", "christchurch": "new zealand",
    # US
    "new york": "us", "san francisco": "us", "los angeles": "us", "chicago": "us",
    "boston": "us", "austin": "us", "seattle": "us", "denver": "us", "miami": "us",
    "houston": "us", "dallas": "us", "atlanta": "us", "phoenix": "us",
    "portland": "us", "san diego": "us", "philadelphia": "us", "washington dc": "us",
    "temecula": "us", "anchorage": "us", "redstone arsenal": "us",
    "charlotte": "us", "nashville": "us", "baltimore": "us", "kansas city": "us",
    # Other
    "dublin": "ireland", "tokyo": "japan", "osaka": "japan", "singapore": "singapore",
    "hong kong": "hong kong", "dubai": "uae", "abu dhabi": "uae", "riyadh": "saudi arabia",
    "doha": "qatar", "manama": "bahrain", "kuwait city": "kuwait", "muscat": "oman",
    "são paulo": "brazil", "sao paulo": "brazil", "rio de janeiro": "brazil",
    "buenos aires": "argentina", "mexico city": "mexico", "monterrey": "mexico",
    "warsaw": "poland", "krakow": "poland", "amsterdam": "netherlands",
    "rotterdam": "netherlands", "madrid": "spain", "barcelona": "spain",
    "rome": "italy", "milan": "italy", "zurich": "switzerland", "geneva": "switzerland",
    "stockholm": "sweden", "oslo": "norway", "copenhagen": "denmark", "helsinki": "finland",
    "brussels": "belgium", "vienna": "austria", "lisbon": "portugal",
    "athens": "greece", "budapest": "hungary", "prague": "czech republic",
    "bucharest": "romania", "kiev": "ukraine", "kyiv": "ukraine",
    "seoul": "south korea", "istanbul": "turkey",
    "tel aviv": "israel", "cairo": "egypt", "lagos": "nigeria", "nairobi": "kenya",
    "cape town": "south africa", "johannesburg": "south africa",
}

# Two-letter US state abbreviations -> "us" (exact token match only).
US_STATE_CODES = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id",
    "il", "in", "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms",
    "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok",
    "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv",
    "wi", "wy",
}

# Canadian province/territory codes -> "canada" (exact token match only).
CA_PROVINCE_CODES = {
    "ab", "bc", "mb", "nb", "nl", "ns", "nt", "nu", "on", "pe", "qc", "sk", "yt",
}

# Country codes -> canonical country (exact token match only).
COUNTRY_CODES = {
    "us": "us", "usa": "us", "uk": "uk", "gb": "uk", "gbr": "uk",
    "can": "canada", "de": "germany", "deu": "germany", "fr": "france",
    "aus": "australia", "au": "australia", "ie": "ireland", "irl": "ireland",
    "nl": "netherlands", "br": "brazil", "ar": "argentina", "mx": "mexico",
    "jp": "japan", "jpn": "japan", "sg": "singapore", "kr": "south korea",
    "in": "india", "pk": "pakistan", "pl": "poland", "es": "spain", "it": "italy",
    "ch": "switzerland", "se": "sweden", "no": "norway", "dk": "denmark",
    "fi": "finland", "be": "belgium", "at": "austria", "pt": "portugal",
    "gr": "greece", "hu": "hungary", "cz": "czech republic", "ro": "romania",
    "ua": "ukraine", "tr": "turkey", "il": "israel", "eg": "egypt",
    "za": "south africa", "ng": "nigeria", "ke": "kenya", "sa": "saudi arabia",
    "ae": "uae", "qa": "qatar", "bh": "bahrain", "kw": "kuwait", "om": "oman",
}

VALID_MODES = ("remote", "local", "sponsorship", "all")

# Stable reason codes surfaced to the UI and stored in the DB
REASON_NOT_REMOTE = "not_remote"
REASON_LOCATION = "not_eligible_location"
REASON_SPONSORSHIP = "requires_sponsorship"
REASON_COUNTRY_RESTRICTED = "country_restricted"


def location_country(loc: str | None) -> str | None:
    """Best-effort canonical country extracted from a location string.

    Matching order: full country/state names (substring, longest first), then
    city names (word-boundary), then two-letter country/province/state codes
    (exact token). Codes never match as substrings, so "on" only resolves via
    a standalone token like "ON" and "in" can't collide with words like "India".
    """
    if not loc:
        return None
    original = loc
    loc = loc.lower()

    for token, code in sorted(COMMON_COUNTRIES.items(), key=lambda kv: len(kv[0]), reverse=True):
        if token in loc:
            return code

    for city, code in sorted(CITY_TO_COUNTRY.items(), key=lambda kv: len(kv[0]), reverse=True):
        if re.search(rf"(?<![a-z]){re.escape(city)}(?![a-z])", loc):
            return code

    # Two-letter codes only count when uppercase in the original string, so
    # English words like "in"/"on" can never be mistaken for country codes.
    upper_tokens = set(w.lower() for w in re.findall(r"[A-Z]{2}", original))
    if upper_tokens:
        for code in COUNTRY_CODES:
            if code in upper_tokens:
                return COUNTRY_CODES[code]
        for code in CA_PROVINCE_CODES:
            if code in upper_tokens:
                return "canada"
        for code in US_STATE_CODES:
            if code in upper_tokens:
                return "us"
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


def url_location(url: str | None) -> str:
    """Extract a usable location string from a job URL, or ''.

    Workday career sites embed the posting location in the URL path as
    /job/<Location>/<Title>_REQ... e.g.
    ".../job/Brazil-So-Paulo-So-Paulo/Senior-..._JREQ200885" or
    ".../job/Warsaw---Poland/Senior-..._R19416". This gives the eligibility
    gate a country signal for jobs whose `location` column is blank.
    """
    if not url:
        return ""
    m = re.search(r"/job/([^/]+)/", url)
    if not m:
        return ""
    return m.group(1).replace("-", " ").replace("_", " ").strip()


def evaluate_job(job: dict, profile: dict, mode: str = "all") -> EligibilityResult:
    """Evaluate whether a job is eligible for the candidate.

    Args:
        job: Job dict with a "location" key (may be None/empty). Falls back to
            the application URL when the location column is blank.
        profile: User profile dict.
        mode: Search mode — one of VALID_MODES.

    Returns:
        EligibilityResult with reason/suggestion populated when ineligible.
    """
    if mode not in VALID_MODES:
        mode = "all"

    c = constraints_from_profile(profile)
    loc_text = job.get("location")
    if not loc_text:
        loc_text = url_location(job.get("application_url") or job.get("url"))
    loc = classify_location(loc_text)
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
