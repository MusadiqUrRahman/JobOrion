"""Source providers: normalized job schema, provider protocol, shared storage.

Every sourcing provider (JobSpy, Workday, Adzuna, remote boards, ATS boards)
converts what it finds into RawJob objects or stores directly to the DB. The
RawJob dataclass is the canonical in-memory shape; store_raw_jobs is the single
insert path so all providers behave identically.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

log = logging.getLogger(__name__)

REMOTE_HINTS = ("remote", "anywhere", "work from home", "wfh", "distributed", "virtual", "telecommute")


def looks_remote(location: str, description: str = "") -> bool:
    """Heuristic: does a location/description read as remote-friendly?"""
    text = f"{location} {description[:500]}".lower()
    return any(hint in text for hint in REMOTE_HINTS)


@dataclass
class RawJob:
    """Normalized job found by any provider.

    Fields are stripped on construction. is_remote is derived from location
    (then description) when not explicitly set, so callers never need to
    guess.
    """

    title: str
    company: str = ""
    location: str = ""
    description: str = ""
    url: str = ""
    apply_url: str = ""
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str = ""
    salary_interval: str = ""
    job_type: str = ""
    is_remote: bool | None = None
    seniority: str = ""
    posted_at: str = ""
    source: str = ""
    site: str = ""

    def __post_init__(self) -> None:
        self.title = (self.title or "").strip()
        self.company = (self.company or "").strip()
        self.location = (self.location or "").strip()
        self.description = (self.description or "").strip()
        self.url = (self.url or "").strip()
        self.apply_url = (self.apply_url or "").strip() or self.url
        self.salary_currency = (self.salary_currency or "").strip()
        self.salary_interval = (self.salary_interval or "").strip()
        if self.is_remote is None:
            self.is_remote = looks_remote(self.location, self.description)

    def salary_text(self) -> str | None:
        """Render min/max/currency/interval as the legacy salary string."""
        if self.salary_min is None and self.salary_max is None:
            return None
        cur = self.salary_currency
        if self.salary_min is not None and self.salary_max is not None:
            text = f"{cur}{int(self.salary_min):,}-{cur}{int(self.salary_max):,}"
        elif self.salary_min is not None:
            text = f"{cur}{int(self.salary_min):,}"
        elif self.salary_max is not None:
            text = f"up to {cur}{int(self.salary_max):,}"
        else:
            return None
        if self.salary_interval:
            text += f"/{self.salary_interval}"
        return text


@dataclass
class ProviderResult:
    """Stats from one provider run, used for logging and dashboards."""

    provider: str
    found: int = 0
    stored: int = 0
    errors: int = 0
    error: str | None = None
    latency_ms: int = 0

    def ok(self) -> bool:
        return self.errors == 0


@runtime_checkable
class JobProvider(Protocol):
    """A sourcing provider: knows how to search once for an intent.

    Implementations are configured from a dict in config/sources.yaml and
    searched with a search intent (see joborion.sourcing.intent).
    """

    name: str

    def search(self, intent: dict) -> ProviderResult:
        """Run one search pass. Must never raise; returns stats instead."""
        ...


def store_raw_jobs(
    conn: sqlite3.Connection,
    jobs: list[RawJob],
    provider: str | None = None,
) -> tuple[int, int]:
    """Insert RawJobs into the jobs table. Returns (new, existing).

    ``provider`` names the sourcing provider that found these jobs; it is
    stored in ``source_provider`` (falling back to each job's own ``source``)
    so the relevance gate can attribute results per provider.
    """
    now = datetime.now(timezone.utc).isoformat()
    new = 0
    existing = 0

    for job in jobs:
        url = job.url
        if not url:
            log.debug("Skipping RawJob without url (title=%r)", job.title)
            continue

        description = job.description or None
        full_description = None
        detail_scraped_at = None
        if description and len(description) > 200:
            full_description = description
            detail_scraped_at = now

        site = job.site or job.source
        source_provider = provider or job.source

        try:
            conn.execute(
                "INSERT INTO jobs (url, title, company, salary, description, location, site, strategy, discovered_at, "
                "full_description, application_url, detail_scraped_at, source_provider) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    url,
                    job.title or None,
                    job.company or None,
                    job.salary_text(),
                    description,
                    job.location or None,
                    site or None,
                    "provider",
                    now,
                    full_description,
                    job.apply_url or None,
                    detail_scraped_at,
                    source_provider or None,
                ),
            )
            new += 1
        except sqlite3.IntegrityError:
            existing += 1

    conn.commit()
    return new, existing
