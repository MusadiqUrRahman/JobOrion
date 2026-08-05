"""Relevance gate: decide PASS/DROP for a normalized job against a search intent.

Phase C scope: arrangement, location, job_type, min_salary, seniority, and
title-relevance checks. Entirely deterministic and LLM-free. The gate can
deduplicate against recently stored jobs and apply itself to the jobs table
(see apply_relevance_gate), which the pipeline invokes after discovery.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from joborion.sourcing.normalize import (
    NormalizedJob,
    annualize,
    country_code_for,
    normalize_company,
    normalize_job,
    normalize_title,
)

log = logging.getLogger(__name__)

_FUZZY_TITLE_THRESHOLD = 80
_CITY_THRESHOLD = 88
_DUP_TITLE_THRESHOLD = 90
_DUP_COMPANY_THRESHOLD = 80


@dataclass
class FilterDecision:
    """Outcome of one relevance evaluation."""

    passed: bool
    reasons: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Individual gates
# ---------------------------------------------------------------------------


def _arrangement_fails(norm: NormalizedJob, intent: dict) -> bool:
    return bool(intent.get("remote_only")) and not norm.is_remote


def location_matches(norm: NormalizedJob, locations: list[str]) -> bool:
    """Does a job's country/city match any preferred location?"""
    for pref in locations:
        pref = (pref or "").strip()
        if not pref:
            continue
        lower = pref.lower()
        if lower in ("worldwide", "global", "anywhere", "remote"):
            return True
        code = country_code_for(pref)
        if code:
            if norm.country == code:
                return True
            continue
        if norm.city and fuzz.token_set_ratio(lower, norm.city.lower()) >= _CITY_THRESHOLD:
            return True
        if norm.country and fuzz.token_set_ratio(lower, norm.country.lower()) >= _CITY_THRESHOLD:
            return True
    return False


def _location_fails(norm: NormalizedJob, intent: dict) -> bool:
    locations = intent.get("locations") or ["worldwide"]
    if not locations or "worldwide" in locations:
        return False
    return not location_matches(norm, locations)


def _job_type_fails(norm: NormalizedJob, intent: dict) -> bool:
    allowed = intent.get("job_types") or ["all"]
    if not allowed or "all" in allowed:
        return False
    if not norm.job_type:
        return False  # unknown -> keep; dropping on unknown would lose good jobs
    return norm.job_type not in allowed


def _salary_fails(norm: NormalizedJob, intent: dict) -> bool:
    min_salary = intent.get("min_salary")
    if not min_salary:
        return False
    if norm.salary_min is None and norm.salary_max is None:
        return False  # unknown -> keep
    if norm.salary_currency and norm.salary_currency != "USD":
        return False  # cross-currency comparison is unreliable -> keep

    high = annualize(norm.salary_max, norm.salary_interval) if norm.salary_max is not None else None
    low = annualize(norm.salary_min, norm.salary_interval) if norm.salary_min is not None else None
    best = high if high is not None else low
    if best is None:
        return False
    # Only trust figures we can annualize confidently: explicit interval, or a
    # k-style/annual-scale number. Sub-20k amounts without an interval are
    # ambiguous (monthly/hourly scale) and are not enforced.
    if norm.salary_interval not in ("annual", "monthly", "weekly", "daily", "hourly"):
        if best < 20000:
            return False
    return best < min_salary


def _seniority_fails(norm: NormalizedJob, intent: dict) -> bool:
    allowed = intent.get("seniority") or []
    if not allowed or not norm.seniority:
        return False
    return norm.seniority not in allowed


def title_matches(title: str, keywords: list[str]) -> bool:
    """Does a job title relate to any target keyword (role or skill term)?"""
    t = normalize_title(title)
    title_tokens = set(t.split())
    for kw in keywords:
        kw = (kw or "").strip()
        if not kw:
            continue
        k = normalize_title(kw)
        if k and fuzz.token_set_ratio(t, k) >= _FUZZY_TITLE_THRESHOLD:
            return True
        kw_tokens = {tok for tok in k.split() if len(tok) >= 3}
        if kw_tokens & title_tokens:
            return True
    return False


def _title_fails(norm: NormalizedJob, intent: dict) -> bool:
    keywords = intent.get("keywords") or []
    if not keywords:
        return False
    return not title_matches(norm.title, keywords)


def evaluate(norm: NormalizedJob, intent: dict) -> FilterDecision:
    """Run every relevance gate; the first failed gate becomes the drop reason."""
    checks = (
        ("arrangement", _arrangement_fails),
        ("location", _location_fails),
        ("job_type", _job_type_fails),
        ("salary", _salary_fails),
        ("seniority", _seniority_fails),
        ("title", _title_fails),
    )
    reasons = [name for name, check in checks if check(norm, intent)]
    return FilterDecision(passed=not reasons, reasons=reasons)


# ---------------------------------------------------------------------------
# Dedup + gate application
# ---------------------------------------------------------------------------


def is_duplicate(conn, norm: NormalizedJob) -> bool:
    """Is this job already stored under a near-identical title+company pair?"""
    if not norm.normalized_title or not norm.company:
        return False
    title = norm.normalized_title
    company = normalize_company(norm.company)
    rows = conn.execute(
        "SELECT title, company FROM jobs "
        "WHERE is_remote IS NOT NULL "
        "ORDER BY discovered_at DESC LIMIT 500"
    ).fetchall()
    for row in rows:
        other_title = normalize_title(row["title"] or "")
        other_company = normalize_company(row["company"] or "")
        if not other_title or not other_company:
            continue
        if fuzz.token_set_ratio(company, other_company) < _DUP_COMPANY_THRESHOLD:
            continue
        if fuzz.token_set_ratio(title, other_title) >= _DUP_TITLE_THRESHOLD:
            return True
    return False


_UPDATE_SQL = (
    "UPDATE jobs SET is_remote = ?, country = ?, city = ?, job_type = ?, seniority = ?, "
    "salary_min = ?, salary_max = ?, salary_currency = ?, salary_interval = ?, "
    "source_provider = ?, apply_url_direct = ?, posted_at = ? WHERE url = ?"
)


def apply_relevance_gate(conn, intent: dict, dedup: bool = True) -> dict:
    """Normalize + filter every unfiltered job in the table.

    Rows with ``is_remote IS NULL`` are untouched by the gate; this pass fills
    their structured columns on PASS and deletes DROPped jobs. Returns a
    summary dict for reporting.

    Returns:
        {"processed", "passed", "dropped", "reasons", "by_provider"}
    """
    rows = conn.execute("SELECT * FROM jobs WHERE is_remote IS NULL ORDER BY discovered_at").fetchall()
    summary: dict = {
        "processed": 0, "passed": 0, "dropped": 0,
        "reasons": {}, "by_provider": {}, "by_company": {},
    }

    for row in rows:
        summary["processed"] += 1
        norm = normalize_job(dict(row))
        decision = evaluate(norm, intent)
        provider = norm.source_provider or "unknown"
        provider_stats = summary["by_provider"].setdefault(provider, {"found": 0, "passed": 0, "dropped": 0})
        provider_stats["found"] += 1
        company_stats = summary["by_company"].setdefault(
            provider, {}
        ).setdefault(norm.company or "unknown", {"found": 0, "passed": 0})
        company_stats["found"] += 1

        drop_reason = None
        if decision.passed and dedup and is_duplicate(conn, norm):
            drop_reason = "duplicate"

        if decision.passed and drop_reason is None:
            conn.execute(
                _UPDATE_SQL,
                (
                    int(norm.is_remote),
                    norm.country or None,
                    norm.city or None,
                    norm.job_type or None,
                    norm.seniority or None,
                    norm.salary_min,
                    norm.salary_max,
                    norm.salary_currency or None,
                    norm.salary_interval or None,
                    norm.source_provider or None,
                    norm.apply_url_direct or None,
                    norm.posted_at or None,
                    row["url"],
                ),
            )
            summary["passed"] += 1
            provider_stats["passed"] += 1
            company_stats["passed"] += 1
        else:
            conn.execute("DELETE FROM jobs WHERE url = ?", (row["url"],))
            summary["dropped"] += 1
            provider_stats["dropped"] += 1
            reason = drop_reason or (decision.reasons[0] if decision.reasons else "filter")
            summary["reasons"][reason] = summary["reasons"].get(reason, 0) + 1

    conn.commit()
    return summary
