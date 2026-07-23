"""Document tools — wrap resume tailoring, cover letters, and PDF conversion."""

from __future__ import annotations

import time

from joborion.agent.tools import Tool, ActionResult


class TailorResumeTool(Tool):
    """Generate a tailored resume for a specific job."""

    name = "tailor_resume"
    description = "Generate an ATS-optimized tailored resume for a specific job posting."
    parameters = {
        "url": {"type": "string", "description": "Job URL to tailor resume for"},
        "min_score": {"type": "integer", "description": "Minimum score threshold", "default": 7},
    }

    def execute(self, **params) -> ActionResult:
        t0 = time.time()
        try:
            from joborion.scoring.resume_tailor import tailor_resumes
            result = tailor_resumes(
                min_score=params.get("min_score", 7),
                limit=1,
            )
            elapsed_ms = int((time.time() - t0) * 1000)
            return ActionResult(
                action=self.name,
                status="ok",
                details={
                    "approved": result.get("approved", 0),
                    "failed": result.get("failed", 0),
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


class WriteCoverLetterTool(Tool):
    """Generate a cover letter for a specific job."""

    name = "write_cover_letter"
    description = "Write a concise, engineering-voice cover letter for a job posting."
    parameters = {
        "url": {"type": "string", "description": "Job URL to write cover letter for"},
        "min_score": {"type": "integer", "description": "Minimum score threshold", "default": 7},
    }

    def execute(self, **params) -> ActionResult:
        t0 = time.time()
        try:
            from joborion.scoring.cover_writer import write_cover_letters
            result = write_cover_letters(
                min_score=params.get("min_score", 7),
                limit=1,
            )
            elapsed_ms = int((time.time() - t0) * 1000)
            return ActionResult(
                action=self.name,
                status="ok",
                details={"generated": result.get("generated", 0)},
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


class ConvertToPdfTool(Tool):
    """Convert tailored resume or cover letter to PDF."""

    name = "convert_to_pdf"
    description = "Convert a tailored resume or cover letter text file to PDF."
    parameters = {
        "text_path": {"type": "string", "description": "Path to the text file to convert"},
    }

    def execute(self, **params) -> ActionResult:
        t0 = time.time()
        text_path = params.get("text_path", "")
        if not text_path:
            return ActionResult(self.name, "error", {}, 0.0, 0, "text_path is required")

        try:
            from pathlib import Path
            from joborion.scoring.document_converter import convert_to_pdf
            result = convert_to_pdf(Path(text_path))
            elapsed_ms = int((time.time() - t0) * 1000)
            return ActionResult(
                action=self.name,
                status="ok",
                details={"input": text_path, "output": str(result)},
                cost=0.0,
                duration_ms=elapsed_ms,
                error=None,
            )
        except Exception as e:
            elapsed_ms = int((time.time() - t0) * 1000)
            return ActionResult(
                action=self.name,
                status="error",
                details={"input": text_path},
                cost=0.0,
                duration_ms=elapsed_ms,
                error=str(e),
            )
