"""Enrichment tools — wrap page scraper as composable tools."""

from __future__ import annotations

import time

from joborion.agent.tools import Tool, ActionResult


class EnrichSingleJobTool(Tool):
    """Enrich a single job with full description and apply URL."""

    name = "enrich_single_job"
    description = "Fetch full description and application URL for a single job posting."
    parameters = {
        "url": {"type": "string", "description": "Job URL to enrich"},
    }

    def execute(self, **params) -> ActionResult:
        t0 = time.time()
        url = params.get("url", "")
        if not url:
            return ActionResult(self.name, "error", {}, 0.0, 0, "url is required")

        try:
            from joborion.database import get_connection
            from joborion.enrichment.page_scraper import scrape_site_batch

            conn = get_connection()
            row = conn.execute("SELECT url, title, site FROM jobs WHERE url = ?", (url,)).fetchone()
            if not row:
                return ActionResult(self.name, "error", {"url": url}, 0.0, 0, f"Job not found: {url}")

            site = row[2]
            result = scrape_site_batch(conn, site, [(row[0], row[1])], delay=0)

            elapsed_ms = int((time.time() - t0) * 1000)
            return ActionResult(
                action=self.name,
                status="ok",
                details={"url": url, "ok": result.get("ok", 0), "error": result.get("error", 0)},
                cost=0.0,
                duration_ms=elapsed_ms,
                error=None,
            )
        except Exception as e:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ActionResult(
                action=self.name,
                status="error",
                details={"url": url},
                cost=0.0,
                duration_ms=elapsed_ms,
                error=str(e),
            )


class EnrichBatchTool(Tool):
    """Enrich a batch of pending jobs with full descriptions."""

    name = "enrich_batch"
    description = "Fetch full descriptions for all pending jobs (batch mode)."
    parameters = {
        "limit": {"type": "integer", "description": "Max jobs to enrich", "default": 100},
        "workers": {"type": "integer", "description": "Parallel threads", "default": 1},
    }

    def execute(self, **params) -> ActionResult:
        t0 = time.time()
        try:
            from joborion.enrichment.page_scraper import enrich_jobs
            result = enrich_jobs(
                limit=params.get("limit", 100),
                workers=params.get("workers", 1),
            )
            elapsed_ms = int((time.time() - t0) * 1000)
            return ActionResult(
                action=self.name,
                status="ok",
                details={
                    "processed": result.get("processed", 0),
                    "ok": result.get("ok", 0),
                    "error": result.get("error", 0),
                },
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
