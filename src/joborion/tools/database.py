"""Database query tools — wrap database functions as composable tools."""

from __future__ import annotations

import time

from joborion.agent.tools import Tool, ActionResult


class QueryJobsTool(Tool):
    """Query jobs filtered by pipeline stage."""

    name = "query_jobs"
    description = "Query jobs from the database filtered by pipeline stage and score."
    parameters = {
        "stage": {
            "type": "string",
            "description": "Pipeline stage filter",
            "enum": ["discovered", "pending_detail", "enriched", "pending_score",
                      "scored", "pending_tailor", "tailored", "pending_apply", "applied"],
        },
        "min_score": {"type": "integer", "description": "Minimum fit score", "default": 7},
        "limit": {"type": "integer", "description": "Max results", "default": 100},
    }

    def execute(self, **params) -> ActionResult:
        t0 = time.time()
        try:
            from joborion.database import get_jobs_by_stage
            jobs = get_jobs_by_stage(
                stage=params.get("stage", "discovered"),
                min_score=params.get("min_score"),
                limit=params.get("limit", 100),
            )
            elapsed_ms = int((time.time() - t0) * 1000)
            return ActionResult(
                action=self.name,
                status="ok",
                details={"count": len(jobs), "jobs": jobs[:10]},
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


class GetJobDetailTool(Tool):
    """Get full details for a specific job by URL."""

    name = "get_job_detail"
    description = "Retrieve the full record for a specific job posting."
    parameters = {
        "url": {"type": "string", "description": "Job URL"},
    }

    def execute(self, **params) -> ActionResult:
        t0 = time.time()
        url = params.get("url", "")
        if not url:
            return ActionResult(self.name, "error", {}, 0.0, 0, "url is required")

        try:
            from joborion.database import get_connection
            conn = get_connection()
            row = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
            elapsed_ms = int((time.time() - t0) * 1000)

            if row:
                job = dict(zip(row.keys(), row))
                return ActionResult(
                    action=self.name,
                    status="ok",
                    details=job,
                    cost=0.0,
                    duration_ms=elapsed_ms,
                    error=None,
                )
            return ActionResult(
                action=self.name,
                status="ok",
                details={"found": False, "url": url},
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


class GetPipelineStatsTool(Tool):
    """Get current pipeline statistics."""

    name = "get_pipeline_stats"
    description = "Get job counts at each pipeline stage (total, scored, tailored, etc.)."
    parameters = {}

    def execute(self, **params) -> ActionResult:
        t0 = time.time()
        try:
            from joborion.database import get_stats
            stats = get_stats()
            elapsed_ms = int((time.time() - t0) * 1000)
            return ActionResult(
                action=self.name,
                status="ok",
                details=stats,
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
