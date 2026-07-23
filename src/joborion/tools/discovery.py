"""Discovery tools — wrap scraping modules as composable tools."""

from __future__ import annotations

import time

from joborion.agent.tools import Tool, ActionResult


class ScrapeJobSpyTool(Tool):
    """Scrape job boards (Indeed, LinkedIn, Glassdoor, ZipRecruiter) via JobSpy."""

    name = "scrape_jobspy"
    description = "Search multiple job boards simultaneously using JobSpy. Returns new jobs found."
    parameters = {
        "search_query": {"type": "string", "description": "Job search query"},
        "location": {"type": "string", "description": "Location filter", "default": ""},
        "remote_only": {"type": "boolean", "description": "Remote jobs only", "default": False},
    }

    def execute(self, **params) -> ActionResult:
        t0 = time.time()
        try:
            from joborion.discovery.jobspy import search_jobs
            result = search_jobs(
                query=params.get("search_query", ""),
                location=params.get("location", ""),
                remote_only=params.get("remote_only", False),
            )
            elapsed_ms = int((time.time() - t0) * 1000)
            return ActionResult(
                action=self.name,
                status="ok",
                details={"new": result.get("new", 0), "existing": result.get("existing", 0)},
                cost=0.0,
                duration_ms=elapsed_ms,
                error=None,
            )
        except Exception as e:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ActionResult(
                action=self.name,
                status="error",
                details={},
                cost=0.0,
                duration_ms=elapsed_ms,
                error=str(e),
            )


class ScrapeWorkdayTool(Tool):
    """Scrape Workday-powered corporate career portals."""

    name = "scrape_workday"
    description = "Search Workday corporate career sites (NVIDIA, Salesforce, etc.)."
    parameters = {
        "search_query": {"type": "string", "description": "Job search query"},
        "workers": {"type": "integer", "description": "Parallel threads", "default": 1},
    }

    def execute(self, **params) -> ActionResult:
        t0 = time.time()
        try:
            from joborion.discovery.workday import scrape_workday
            result = scrape_workday(workers=params.get("workers", 1))
            elapsed_ms = int((time.time() - t0) * 1000)
            return ActionResult(
                action=self.name,
                status="ok",
                details={"new": result.get("new", 0), "found": result.get("found", 0)},
                cost=0.0,
                duration_ms=elapsed_ms,
                error=None,
            )
        except Exception as e:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ActionResult(
                action=self.name,
                status="error",
                details={},
                cost=0.0,
                duration_ms=elapsed_ms,
                error=str(e),
            )


class ScrapeAISitesTool(Tool):
    """AI-powered smart extraction from arbitrary job sites."""

    name = "scrape_ai_sites"
    description = "Use AI-powered scraping to extract jobs from arbitrary websites."
    parameters = {
        "workers": {"type": "integer", "description": "Parallel threads", "default": 1},
    }

    def execute(self, **params) -> ActionResult:
        t0 = time.time()
        try:
            from joborion.discovery.ai_scraper import scrape_ai_sites
            result = scrape_ai_sites(workers=params.get("workers", 1))
            elapsed_ms = int((time.time() - t0) * 1000)
            return ActionResult(
                action=self.name,
                status="ok",
                details={"new": result.get("total_new", 0), "total": result.get("total", 0)},
                cost=0.0,
                duration_ms=elapsed_ms,
                error=None,
            )
        except Exception as e:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ActionResult(
                action=self.name,
                status="error",
                details={},
                cost=0.0,
                duration_ms=elapsed_ms,
                error=str(e),
            )
