"""Reflector — analyzes pipeline runs and generates actionable insights.

After each run, the reflector examines outcomes, identifies failures,
checks scoring calibration, and produces recommendations for improvement.
"""

from __future__ import annotations

import sqlite3
from collections import Counter


class Reflector:
    """Analyzes pipeline run outcomes and generates reflections.

    Uses database connection to query run data, jobs, and site memory.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def analyze_run(self, run_id: str) -> dict:
        """Analyze a run and produce a reflection record.

        Args:
            run_id: The run ID to analyze.

        Returns:
            Dict with keys: overall_rating, what_went_well, what_failed,
            strategy_changes, memory_updates, recommendations,
            scoring_calibration, cost_analysis.
        """
        data = self._collect_run_data(run_id)
        outcomes = self._analyze_outcomes(data)
        failures = self._identify_failures(data)
        calibration = self._check_scoring_calibration(data)
        memory_updates = self._update_site_memory(data)
        recommendations = self._generate_recommendations(data, failures, calibration)

        rating = self._compute_rating(data, failures)

        return {
            "run_id": run_id,
            "overall_rating": rating,
            "what_went_well": outcomes.get("went_well", []),
            "what_failed": [f["description"] for f in failures],
            "strategy_changes": [],
            "memory_updates": memory_updates,
            "recommendations": recommendations,
            "scoring_calibration": calibration,
            "cost_analysis": self._cost_analysis(data),
        }

    def _collect_run_data(self, run_id: str) -> dict:
        """Gather all data from the run being analyzed."""
        # Get run info
        run_row = self._conn.execute(
            "SELECT * FROM run_log WHERE run_id = ?", (run_id,)
        ).fetchone()

        run_info = {}
        if run_row:
            cols = [d[0] for d in self._conn.execute("SELECT * FROM run_log LIMIT 0").description]
            run_info = dict(zip(cols, run_row))

        # Get jobs discovered during this run (approximate by timestamp)
        discovered_at = run_info.get("started_at", "")
        jobs = []
        if discovered_at:
            rows = self._conn.execute(
                "SELECT url, title, site, full_description, fit_score, "
                "tailored_resume_path, applied_at, detail_error, "
                "cover_letter_path, apply_status "
                "FROM jobs WHERE discovered_at >= ? ORDER BY discovered_at DESC",
                (discovered_at,),
            ).fetchall()
            jobs = [
                {
                    "url": r[0], "title": r[1], "site": r[2],
                    "has_description": r[3] is not None,
                    "fit_score": r[4], "has_tailored": r[5] is not None,
                    "applied": r[6] is not None, "detail_error": r[7],
                    "has_cover": r[8] is not None, "apply_status": r[9],
                }
                for r in rows
            ]

        # Get cost data
        costs = []
        if discovered_at:
            cost_rows = self._conn.execute(
                "SELECT tool, cost_usd FROM cost_ledger WHERE run_id = ?",
                (run_id,),
            ).fetchall()
            costs = [{"tool": r[0], "cost": r[1]} for r in cost_rows]

        return {
            "run_id": run_id,
            "run_info": run_info,
            "jobs": jobs,
            "costs": costs,
        }

    def _analyze_outcomes(self, data: dict) -> dict:
        """Compare planned vs actual outcomes."""
        jobs = data["jobs"]
        went_well = []

        if not jobs:
            return {"went_well": ["Run completed without errors"]}

        # Count successes per stage
        enriched = sum(1 for j in jobs if j["has_description"])
        scored = sum(1 for j in jobs if j["fit_score"] is not None)
        tailored = sum(1 for j in jobs if j["has_tailored"])
        covered = sum(1 for j in jobs if j["has_cover"])
        applied = sum(1 for j in jobs if j["applied"])

        total = len(jobs)
        went_well.append(f"Discovered {total} jobs")

        if enriched > 0:
            went_well.append(f"Enriched {enriched}/{total} jobs")
        if scored > 0:
            went_well.append(f"Scored {scored} jobs")
        if tailored > 0:
            went_well.append(f"Tailored {tailored} resumes")
        if covered > 0:
            went_well.append(f"Wrote {covered} cover letters")
        if applied > 0:
            went_well.append(f"Applied to {applied} jobs")

        return {"went_well": went_well}

    def _identify_failures(self, data: dict) -> list[dict]:
        """Categorize every failure."""
        failures = []
        jobs = data["jobs"]

        # Detail extraction failures
        detail_errors = [j for j in jobs if j.get("detail_error")]
        if detail_errors:
            error_types = Counter(j["detail_error"] for j in detail_errors)
            for error, count in error_types.items():
                failures.append({
                    "type": "extraction",
                    "description": f"{count} jobs failed detail extraction: {error}",
                    "count": count,
                })

        # Jobs with no score (should have been scored)
        unscored = [j for j in jobs if j["has_description"] and j["fit_score"] is None]
        if unscored:
            failures.append({
                "type": "scoring",
                "description": f"{len(unscored)} enriched jobs were not scored",
                "count": len(unscored),
            })

        # Apply failures
        apply_errors = [j for j in jobs if j.get("apply_status") == "failed"]
        if apply_errors:
            failures.append({
                "type": "application",
                "description": f"{len(apply_errors)} applications failed",
                "count": len(apply_errors),
            })

        return failures

    def _check_scoring_calibration(self, data: dict) -> dict:
        """Analyze score distribution and calibration."""
        jobs = data["jobs"]
        scored_jobs = [j for j in jobs if j["fit_score"] is not None]

        if not scored_jobs:
            return {
                "score_distribution": {},
                "avg_score": 0,
                "score_range": 0,
                "assessment": "No jobs scored",
            }

        scores = [j["fit_score"] for j in scored_jobs]
        dist = Counter(scores)
        avg = sum(scores) / len(scores)
        score_range = max(scores) - min(scores)

        # Assessment
        if score_range <= 2:
            assessment = "Scores cluster tightly — consider widening range"
        elif avg > 8:
            assessment = "Scores skew high — threshold may be too low"
        elif avg < 5:
            assessment = "Scores skew low — check scoring criteria"
        else:
            assessment = "Score distribution looks healthy"

        # Score-vs-outcome correlation
        applied_scores = [j["fit_score"] for j in scored_jobs if j["applied"]]
        correlation = {}
        if applied_scores:
            avg_applied = sum(applied_scores) / len(applied_scores)
            correlation = {
                "avg_applied_score": round(avg_applied, 2),
                "total_applied": len(applied_scores),
            }

        return {
            "score_distribution": dict(dist),
            "avg_score": round(avg, 2),
            "score_range": score_range,
            "assessment": assessment,
            "correlation": correlation,
        }

    def _update_site_memory(self, data: dict) -> list[dict]:
        """Propose memory updates based on site performance."""
        jobs = data["jobs"]
        updates = []

        site_stats = {}
        for j in jobs:
            site = j.get("site", "unknown")
            if site not in site_stats:
                site_stats[site] = {"total": 0, "errors": 0, "scored": 0}
            site_stats[site]["total"] += 1
            if j.get("detail_error"):
                site_stats[site]["errors"] += 1
            if j.get("fit_score") is not None:
                site_stats[site]["scored"] += 1

        for site, stats in site_stats.items():
            error_rate = stats["errors"] / stats["total"] if stats["total"] > 0 else 0
            if error_rate > 0.5:
                updates.append({
                    "site": site,
                    "action": "flag_unreliable",
                    "reason": f"{stats['errors']}/{stats['total']} extractions failed",
                })
            elif error_rate == 0 and stats["total"] > 3:
                updates.append({
                    "site": site,
                    "action": "mark_reliable",
                    "reason": f"{stats['total']} successful extractions",
                })

        return updates

    def _generate_recommendations(
        self, data: dict, failures: list[dict], calibration: dict
    ) -> list[str]:
        """Generate actionable recommendations."""
        recs = []

        # From failures
        for f in failures:
            if f["type"] == "extraction":
                recs.append("Investigate extraction errors on affected sites")
            elif f["type"] == "scoring":
                recs.append(f"Check why {f['count']} enriched jobs were not scored")
            elif f["type"] == "application":
                recs.append(f"Review {f['count']} failed applications for patterns")

        # From calibration
        if calibration.get("score_range", 10) <= 2:
            recs.append("Scoring range is narrow — consider adjusting scoring prompt")
        if calibration.get("avg_score", 0) > 8:
            recs.append("Average score is high — consider raising minimum threshold")

        # From site memory
        unreliable = [u for u in data.get("memory_updates", []) if u.get("action") == "flag_unreliable"]
        if unreliable:
            sites = [u["site"] for u in unreliable]
            recs.append(f"Consider blocking unreliable sites: {', '.join(sites)}")

        if not recs:
            recs.append("Run looks healthy — no immediate changes needed")

        return recs

    def _compute_rating(self, data: dict, failures: list[dict]) -> str:
        """Compute overall rating based on outcomes."""
        jobs = data["jobs"]
        if not jobs:
            return "ok"

        total = len(jobs)
        error_count = sum(1 for f in failures for _ in range(f.get("count", 1)))
        error_rate = error_count / total if total > 0 else 0

        if error_rate < 0.1:
            return "good"
        elif error_rate < 0.3:
            return "ok"
        else:
            return "poor"

    def _cost_analysis(self, data: dict) -> dict:
        """Analyze cost breakdown."""
        costs = data["costs"]
        if not costs:
            return {"total": 0.0, "by_tool": {}}

        total = sum(c["cost"] for c in costs)
        by_tool = {}
        for c in costs:
            tool = c["tool"]
            by_tool[tool] = by_tool.get(tool, 0.0) + c["cost"]

        return {
            "total": round(total, 4),
            "by_tool": {k: round(v, 4) for k, v in by_tool.items()},
        }
