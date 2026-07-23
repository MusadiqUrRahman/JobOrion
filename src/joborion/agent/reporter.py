"""Run Reporter — generates human-readable summary reports after pipeline runs.

Produces formatted reports with pipeline stats, top applications,
cost breakdown, and lessons learned.
"""

from __future__ import annotations


class RunReporter:
    """Generates human-readable run summary reports."""

    def generate(self, run_data: dict) -> str:
        """Generate a formatted run report.

        Args:
            run_data: Dict with keys: goal, duration_s, total_cost,
                      stages (list), top_jobs (list), errors (list).

        Returns:
            Formatted report string.
        """
        lines = []

        # Header
        lines.append("=" * 50)
        lines.append("  JobOrion Run Report")
        lines.append("=" * 50)
        lines.append(f"  Goal: {run_data.get('goal', '?')}")
        lines.append(f"  Duration: {self._format_duration(run_data.get('duration_s', 0))}")
        lines.append(f"  Cost: ${run_data.get('total_cost', 0):.4f}")
        lines.append("")

        # Pipeline stats
        stages = run_data.get("stages", [])
        if stages:
            lines.append("Pipeline:")
            for stage in stages:
                name = stage.get("name", "?")
                count = stage.get("count", "?")
                status = stage.get("status", "?")
                lines.append(f"  {name:<12s} {count} items ({status})")
            lines.append("")

        # Top applications
        top_jobs = run_data.get("top_jobs", [])
        if top_jobs:
            lines.append("Top applications:")
            for i, job in enumerate(top_jobs[:5], 1):
                title = job.get("title", "?")
                company = job.get("company", "?")
                score = job.get("score", "?")
                lines.append(f"  {i}. {title} @ {company} (score: {score})")
            lines.append("")

        # Errors
        errors = run_data.get("errors", [])
        if errors:
            lines.append("Errors:")
            for err in errors[:5]:
                lines.append(f"  - {err}")
            lines.append("")

        # Lessons learned (from reflection if available)
        lessons = run_data.get("lessons", [])
        if lessons:
            lines.append("Lessons learned:")
            for lesson in lessons:
                lines.append(f"  - {lesson}")
            lines.append("")

        lines.append("=" * 50)
        return "\n".join(lines)

    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable form."""
        if seconds < 60:
            return f"{seconds:.1f}s"
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        if minutes < 60:
            return f"{minutes}m {secs}s"
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours}h {mins}m {secs}s"
