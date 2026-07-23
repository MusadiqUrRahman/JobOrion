"""Scoring tools — wrap fit scorer and resume tailor as composable tools."""

from __future__ import annotations

import time

from joborion.agent.tools import Tool, ActionResult


class ScoreSingleJobTool(Tool):
    """Score a single job against the user's resume."""

    name = "score_single_job"
    description = "Score how well a job fits the user's resume (1-10 scale)."
    parameters = {
        "url": {"type": "string", "description": "Job URL to score"},
    }

    def execute(self, **params) -> ActionResult:
        t0 = time.time()
        url = params.get("url", "")
        if not url:
            return ActionResult(self.name, "error", {}, 0.0, 0, "url is required")

        try:
            from joborion.scoring.fit_scorer import score_jobs
            result = score_jobs(limit=1)
            elapsed_ms = int((time.time() - t0) * 1000)
            return ActionResult(
                action=self.name,
                status="ok",
                details={"url": url, "scored": result.get("scored", 0)},
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


class ScoreBatchTool(Tool):
    """Score all unscored jobs in batch mode."""

    name = "score_batch"
    description = "Score all unscored jobs that have full descriptions."
    parameters = {
        "limit": {"type": "integer", "description": "Max jobs to score", "default": 0},
        "rescore": {"type": "boolean", "description": "Rescore already-scored jobs", "default": False},
    }

    def execute(self, **params) -> ActionResult:
        t0 = time.time()
        try:
            from joborion.scoring.fit_scorer import score_jobs
            result = score_jobs(
                limit=params.get("limit", 0),
                rescore=params.get("rescore", False),
            )
            elapsed_ms = int((time.time() - t0) * 1000)
            return ActionResult(
                action=self.name,
                status="ok",
                details={
                    "scored": result.get("scored", 0),
                    "errors": result.get("errors", 0),
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
