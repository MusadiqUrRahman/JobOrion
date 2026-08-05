"""Structured job normalization: raw job fields -> deterministic, LLM-free fields.

Phase C scope: turn a raw job row (title/company/location/description/salary)
into structured fields (country, city, is_remote, job_type, seniority, salary
parts) that the relevance gate uses and that get persisted to the jobs table.

Every function here is pure and deterministic: no LLM, no network, no global
state beyond immutable lookup tables built at import time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pycountry
from rapidfuzz import fuzz

from joborion.sources.base import looks_remote

_HOURS_PER_YEAR = 2080
_DAYS_PER_YEAR = 250

_REGIONS = ("europe", "emea", "apac", "asia", "middle east", "latin america", "north america", "africa")
_ANYWHERE_MARKERS = ("worldwide", "global", "anywhere", "flexible", "tbd", "to be determined", "multiple locations")

# US state / province tokens that are not cities or countries.
_US_STATES = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id", "il", "in", "ia",
    "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj",
    "nm", "ny", "nc", "nd", "oh", "ok", "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt",
    "va", "wa", "wv", "wi", "wy",
}

COUNTRY_ALIASES: dict[str, str] = {
    "uk": "GB", "u.k.": "GB", "great britain": "GB", "britain": "GB", "england": "GB",
    "scotland": "GB", "wales": "GB", "northern ireland": "GB", "n. ireland": "GB",
    "usa": "US", "u.s.": "US", "u.s.a.": "US", "america": "US",
    "uae": "AE", "emirates": "AE",
    "holland": "NL", "the netherlands": "NL",
    "south korea": "KR", "korea": "KR", "russia": "RU", "vietnam": "VN",
    "czech republic": "CZ", "czechia": "CZ", "south africa": "ZA", "saudi arabia": "SA",
    "united states": "US", "united kingdom": "GB",
}


def _build_country_candidates() -> list[tuple[str, str]]:
    """(lowercase match_name, alpha_2) pairs for fuzzy country detection."""
    candidates: list[tuple[str, str]] = []
    for country in pycountry.countries:
        names = {country.name}
        for attr in ("official_name", "common_name"):
            value = getattr(country, attr, None)
            if value:
                names.add(value)
        for name in names:
            candidates.append((name.lower(), country.alpha_2))
    candidates.extend((alias.lower(), code) for alias, code in COUNTRY_ALIASES.items())
    return candidates


_COUNTRY_CANDIDATES: list[tuple[str, str]] = _build_country_candidates()

_COUNTRY_MATCH_THRESHOLD = 80


def _is_marker(part: str) -> bool:
    """Is a location segment a remote/region/state marker rather than a city?"""
    p = part.strip().lower()
    if p in _US_STATES:
        return True
    if p in _REGIONS or p in _ANYWHERE_MARKERS:
        return True
    return any(hint in p for hint in ("remote", "anywhere", "work from home", "wfh", "virtual"))


def _city_from_parts(parts: list[str], country_idx: int | None) -> str:
    for idx, part in enumerate(parts):
        if idx == country_idx or _is_marker(part):
            continue
        return part.strip()
    return ""


def country_code_for(text: str) -> str:
    """Best-effort country alpha_2 for a free-form string, or '' if unknown."""
    if not text or not text.strip():
        return ""
    segment = " ".join(text.split()).lower()
    if segment in COUNTRY_ALIASES:
        return COUNTRY_ALIASES[segment]
    best = ("", 0)
    for name, code in _COUNTRY_CANDIDATES:
        score = fuzz.token_set_ratio(segment, name)
        if score > best[1]:
            best = (code, score)
    return best[0] if best[1] >= _COUNTRY_MATCH_THRESHOLD else ""


def extract_country_city(location: str) -> tuple[str, str]:
    """Extract (country_alpha2, city) from a free-form job location string.

    Examples:
        "London, United Kingdom"   -> ("GB", "London")
        "San Francisco, CA, US"    -> ("US", "San Francisco")
        "Remote"                   -> ("", "Remote")
        "Europe"                   -> ("", "")
    """
    if not location or not location.strip():
        return "", ""

    parts = [p.strip() for p in location.split(",") if p.strip()]
    if not parts:
        return "", ""

    full = " ".join(parts).lower()
    if any(region in full for region in _REGIONS):
        return "", ""

    best: tuple[str, float, int | None] = ("", 0.0, None)
    for idx, part in enumerate(parts):
        segment = " ".join(part.split()).lower()
        if segment in COUNTRY_ALIASES:
            return COUNTRY_ALIASES[segment], _city_from_parts(parts, idx)
        for name, code in _COUNTRY_CANDIDATES:
            score = fuzz.token_set_ratio(segment, name)
            if score > best[1]:
                best = (code, score, idx)

    if best[0] and best[1] >= _COUNTRY_MATCH_THRESHOLD:
        return best[0], _city_from_parts(parts, best[2])
    return "", _city_from_parts(parts, None)


def normalize_title(title: str) -> str:
    """Order-independent, lowercase dedup key for a job title."""
    t = re.sub(r"[^a-z0-9 ]+", " ", title.lower())
    return " ".join(sorted(t.split()))


def normalize_company(name: str) -> str:
    """Lowercase company name with legal-suffix noise stripped."""
    n = re.sub(r"[^a-z0-9 ]+", " ", name.lower())
    n = re.sub(
        r"\b(inc|llc|ltd|limited|corp|corporation|gmbh|sa|sas|bv|plc|co|company|group|ag|labs|technologies|technology)\b",
        " ",
        n,
    )
    return " ".join(n.split())


_CURRENCY_PATTERNS = [
    (r"£|gbp", "GBP"),
    (r"€|eur", "EUR"),
    (r"c\$|cad", "CAD"),
    (r"a\$|aud", "AUD"),
    (r"\$|usd", "USD"),
]


def _detect_currency(text: str) -> str:
    for pattern, currency in _CURRENCY_PATTERNS:
        if re.search(pattern, text, re.I):
            return currency
    return "USD"


_INTERVAL_PATTERNS = [
    (r"per\s*(hour|hr)\b|/hr\b|hourly|an hour|a hour", "hourly"),
    (r"per\s*day\b|/day\b|daily", "daily"),
    (r"per\s*week\b|/wk\b|/week\b|weekly", "weekly"),
    (r"per\s*month\b|/mo\b|/month\b|monthly", "monthly"),
    (r"per\s*(year|annum)\b|/yr\b|/year\b|p\.?a\.?|annually|a year|annual", "annual"),
]


def _detect_interval(text: str) -> str:
    for pattern, interval in _INTERVAL_PATTERNS:
        if re.search(pattern, text, re.I):
            return interval
    return ""


_NUM_RE = re.compile(r"(\d[\d,]*\.?\d*)\s*(k|thousand)?", re.I)


def _extract_amounts(text: str, require_marker: bool, min_value: float = 1000.0) -> list[float]:
    """Money-like numbers from a string, k/thousand scaled. Noise-filtered."""
    has_marker = bool(re.search(r"\$|€|£|k|thousand|salary", text, re.I))
    amounts: list[float] = []
    for m in _NUM_RE.finditer(text):
        raw, scale = m.group(1), (m.group(2) or "").lower()
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        if scale in ("k", "thousand"):
            value *= 1000.0
        if not (min_value <= value <= 2_000_000.0):
            continue
        if require_marker and not (has_marker or scale in ("k", "thousand")):
            continue
        amounts.append(value)
    return amounts


def _dedupe(amounts: list[float]) -> list[float]:
    out: list[float] = []
    for a in amounts:
        if not out or abs(a - out[-1]) > 0.01:
            out.append(a)
    return out


def parse_salary(
    salary_text: str | None,
    description: str = "",
) -> tuple[float | None, float | None, str, str]:
    """Parse (min, max, currency, interval) from a salary string + description.

    Falls back to scanning the description only when the salary text has no
    numbers, so stray figures in prose don't get misread as compensation.
    """
    text = (salary_text or "").strip()
    currency = _detect_currency(text) if text else ""
    interval = _detect_interval(text) if text else ""
    min_value = 1.0 if (currency or interval) else 1000.0
    amounts = _extract_amounts(text, require_marker=False, min_value=min_value) if text else []

    if not amounts and description:
        amounts = _dedupe(_extract_amounts(description, require_marker=True))
        if amounts:
            currency = _detect_currency(description)
            interval = _detect_interval(description)

    if not amounts:
        return None, None, "", ""

    if not interval and any(a >= 20000 for a in amounts):
        interval = "annual"

    low = high = None
    if len(amounts) >= 2:
        low, high = amounts[0], amounts[1]
    else:
        low = high = amounts[0]
        if re.search(r"up\s*to", text or description, re.I):
            low = None

    return low, high, currency or "USD", interval or ""


_JOB_TYPE_PATTERNS = [
    ("internship", re.compile(r"\b(intern|internship|co.?op|placement|graduate program|graduate role)\b", re.I)),
    ("contract", re.compile(r"\b(contract|contractor|freelance|temporary)\b", re.I)),
    ("fulltime", re.compile(r"\bfull[\s-]*time\b|fulltime", re.I)),
    ("parttime", re.compile(r"\bpart[\s-]*time\b|parttime", re.I)),
]


def parse_job_type(text: str) -> str:
    """Classify job_type (fulltime|parttime|contract|internship) from title+desc."""
    haystack = text[:2000]
    for job_type, pattern in _JOB_TYPE_PATTERNS:
        if pattern.search(haystack):
            return job_type
    return ""


_SENIORITY_PATTERNS = [
    ("staff", re.compile(r"\bstaff\b", re.I)),
    ("lead", re.compile(r"\b(lead|principal|tech\s?lead|head of)\b", re.I)),
    ("senior", re.compile(r"\b(senior|sr\.?)\b|(?:^|\s)(iii|iv)(?:\s|$)", re.I)),
    ("mid", re.compile(r"\bmid[\s-]*level\b|intermediate|(?:^|\s)ii(?:\s|$)", re.I)),
    ("entry", re.compile(r"\b(entry[\s-]*level|junior|jr\.?|associate|graduate|new\s?grad|recent\s?grad)\b", re.I)),
]


def parse_seniority(title: str, description: str = "") -> str:
    """Classify seniority (entry|mid|senior|lead|staff) from title + short desc."""
    haystack = f"{title[:150]} {description[:150]}"
    for level, pattern in _SENIORITY_PATTERNS:
        if pattern.search(haystack):
            return level
    return ""


def annualize(value: float, interval: str) -> float:
    """Convert a salary amount to an annual figure."""
    if interval == "hourly":
        return value * _HOURS_PER_YEAR
    if interval == "daily":
        return value * _DAYS_PER_YEAR
    if interval == "weekly":
        return value * 52
    if interval == "monthly":
        return value * 12
    return value


@dataclass
class NormalizedJob:
    """Structured fields for one job, used by the relevance gate."""

    title: str
    company: str
    location: str
    description: str
    url: str
    country: str = ""
    city: str = ""
    is_remote: bool = False
    job_type: str = ""
    seniority: str = ""
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str = ""
    salary_interval: str = ""
    source_provider: str = ""
    apply_url_direct: str = ""
    posted_at: str = ""
    normalized_title: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self.normalized_title = normalize_title(self.title)


def normalize_job(row: dict) -> NormalizedJob:
    """Normalize a jobs-table row (or RawJob-like dict) into structured fields."""
    title = (row.get("title") or "").strip()
    company = (row.get("company") or "").strip()
    location = (row.get("location") or "").strip()
    description = (row.get("description") or row.get("full_description") or "").strip()
    url = (row.get("url") or "").strip()

    country, city = extract_country_city(location)
    combined = f"{title} {description[:600]}"
    salary_min, salary_max, salary_currency, salary_interval = parse_salary(row.get("salary"), description)

    return NormalizedJob(
        title=title,
        company=company,
        location=location,
        description=description,
        url=url,
        country=country,
        city=city,
        is_remote=looks_remote(location, description),
        job_type=parse_job_type(combined),
        seniority=parse_seniority(title, description),
        salary_min=salary_min,
        salary_max=salary_max,
        salary_currency=salary_currency,
        salary_interval=salary_interval,
        source_provider=(
            row.get("source_provider") or row.get("site") or row.get("source") or ""
        ).strip(),
        apply_url_direct=(row.get("application_url") or url),
        posted_at=(row.get("discovered_at") or row.get("posted_at") or ""),
    )
