"""Workday provider: wraps discovery.workday.scrape_workday as a JobProvider."""

from __future__ import annotations

from joborion.discovery.workday import scrape_workday
from joborion.sources.base import ProviderResult


class WorkdayProvider:
    """Search employer Workday career portals via the CXS JSON API."""

    name = "workday"

    def __init__(self, cfg: dict):
        self.cfg = cfg or {}

    def search(self, intent: dict) -> ProviderResult:
        stats = scrape_workday(workers=self.cfg.get("workers", 1))
        return ProviderResult(
            provider=self.name,
            found=stats.get("found", 0),
            stored=stats.get("new", 0),
            errors=0,
            companies=stats.get("companies"),
        )
