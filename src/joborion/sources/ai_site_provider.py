"""AI-site provider: wraps discovery.ai_scraper.scrape_ai_sites as a JobProvider.

The smart-extract pipeline is LLM-heavy and best-effort; it runs last in the
provider order (lowest reliability) and its stats map onto ProviderResult.
"""

from __future__ import annotations

from joborion.discovery.ai_scraper import scrape_ai_sites
from joborion.sources.base import ProviderResult


class AiSiteProvider:
    """Smart-extract job boards from sites.yaml via LLM + Playwright."""

    name = "ai_sites"
    uses_llm = True

    def __init__(self, cfg: dict):
        self.cfg = cfg or {}

    def search(self, intent: dict) -> ProviderResult:
        stats = scrape_ai_sites(workers=self.cfg.get("workers", 1))
        return ProviderResult(
            provider=self.name,
            found=stats.get("total_new", 0) + stats.get("total_existing", 0),
            stored=stats.get("total_new", 0),
            errors=0,
        )
