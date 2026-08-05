"""JobSpy provider: wraps discovery.jobspy.scrape_jobspy as a JobProvider.

The underlying module already handles config loading, retries, filtering,
and DB storage, so this provider is a thin adapter that maps its stats onto
the ProviderResult shape.
"""

from __future__ import annotations

from joborion import config
from joborion.discovery.jobspy import scrape_jobspy
from joborion.sources.base import ProviderResult


class JobSpyProvider:
    """Search Indeed/LinkedIn/ZipRecruiter via the JobSpy scraper."""

    name = "jobspy"

    def __init__(self, cfg: dict):
        self.cfg = cfg or {}

    def _search_config(self) -> dict:
        search_cfg = config.load_search_config()
        override: dict = {}
        if self.cfg.get("sites"):
            override["sites"] = self.cfg["sites"]
        defaults = {}
        if "results_per_site" in self.cfg:
            defaults["results_per_site"] = self.cfg["results_per_site"]
        if "hours_old" in self.cfg:
            defaults["hours_old"] = self.cfg["hours_old"]
        if defaults:
            override["defaults"] = {**search_cfg.get("defaults", {}), **defaults}
        if override:
            search_cfg = {**search_cfg, **override}
        return search_cfg

    def search(self, intent: dict) -> ProviderResult:
        mode = intent.get("mode") if intent else None
        stats = scrape_jobspy(cfg=self._search_config(), mode=mode)
        return ProviderResult(
            provider=self.name,
            found=stats.get("new", 0) + stats.get("existing", 0),
            stored=stats.get("new", 0),
            errors=stats.get("errors", 0),
        )
