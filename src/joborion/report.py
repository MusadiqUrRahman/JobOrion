"""JobOrion analytics report — read-only aggregation of pipeline telemetry.

Reads tables the pipeline already writes (jobs, provider_metrics, cost_ledger,
run_log, source_stats) and renders a deterministic text report. No LLM calls,
no network access, no writes.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from joborion.database import get_connection

_PROVIDER_SQL = """
    SELECT provider,
           COUNT(*) AS runs,
           SUM(found) AS found,
           SUM(stored) AS stored,
           SUM(passed) AS passed,
           SUM(scored) AS scored,
           SUM(applied) AS applied,
           SUM(rejected) AS rejected,
           SUM(errors) AS errors,
           AVG(avg_fit) AS avg_fit,
           AVG(latency_ms) AS avg_latency_ms
    FROM provider_metrics
    WHERE run_started_at >= ?
    GROUP BY provider
    ORDER BY stored DESC
    LIMIT ?
"""

_COST_TOTAL_SQL = (
    "SELECT COUNT(*) AS calls, COALESCE(SUM(cost_usd), 0) AS total_cost "
    "FROM cost_ledger WHERE recorded_at >= ?"
)

_COST_BY_TOOL_SQL = (
    "SELECT tool, COUNT(*) AS calls, COALESCE(SUM(cost_usd), 0) AS cost "
    "FROM cost_ledger WHERE recorded_at >= ? "
    "GROUP BY tool ORDER BY cost DESC LIMIT 5"
)

_RUNS_SQL = (
    "SELECT run_id, started_at, goal, status, jobs_discovered, jobs_applied, "
    "total_cost, total_duration_ms "
    "FROM run_log WHERE started_at >= ? ORDER BY started_at DESC LIMIT ?"
)

_DISABLED_SQL = "SELECT source_name, disabled FROM source_stats"

# Legacy databases (pre provider_metrics) tagged jobs with old strategy
# strings. Map them back to the provider names used by source_stats so the
# Providers section is meaningful without a data migration.
_LEGACY_STRATEGY_PROVIDERS = {
    "jobspy": "jobspy",
    "workday_api": "workday",
    "css_selectors": "smartextract",
}

_LEGACY_RUNS_SQL = (
    "SELECT source_name, total_runs, failed_runs, total_passed, avg_fit "
    "FROM source_stats WHERE total_runs > 0"
)

_JOBS_BY_STRATEGY_SQL = "SELECT strategy, COUNT(*) AS n FROM jobs GROUP BY strategy"


def _cutoff(days: int) -> str:
    """UTC ISO timestamp marking the report window start (matches stored format)."""
    return (datetime.now(timezone.utc) - timedelta(days=max(int(days), 0))).isoformat()


def pipeline_funnel(conn) -> dict:
    """Job counts per pipeline stage, regardless of run window."""
    queries = {
        "discovered": "SELECT COUNT(*) FROM jobs",
        "enriched": "SELECT COUNT(*) FROM jobs WHERE full_description IS NOT NULL",
        "scored": "SELECT COUNT(*) FROM jobs WHERE fit_score IS NOT NULL",
        "tailored": "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL",
        "applied": "SELECT COUNT(*) FROM jobs WHERE applied_at IS NOT NULL",
    }
    return {name: conn.execute(sql).fetchone()[0] for name, sql in queries.items()}


def provider_report(conn, days: int = 30, top: int = 10) -> list[dict]:
    """Aggregate per-provider metrics over the window, best stored first."""
    rows = conn.execute(_PROVIDER_SQL, (_cutoff(days), max(int(top), 1))).fetchall()
    disabled = {
        row["source_name"]: bool(row["disabled"])
        for row in conn.execute(_DISABLED_SQL).fetchall()
    }
    if not rows:
        rows = _legacy_provider_rows(conn, disabled, top)
    result = []
    for row in rows:
        result.append({
            "provider": row["provider"],
            "runs": row["runs"],
            "found": row["found"] or 0,
            "stored": row["stored"] or 0,
            "passed": row["passed"] or 0,
            "scored": row["scored"] or 0,
            "applied": row["applied"] or 0,
            "rejected": row["rejected"] or 0,
            "errors": row["errors"] or 0,
            "avg_fit": round(row["avg_fit"], 2) if row["avg_fit"] is not None else 0.0,
            "avg_latency_ms": round(row["avg_latency_ms"], 1) if row["avg_latency_ms"] is not None else 0.0,
            "disabled": disabled.get(row["provider"], False),
        })
    return result


def _legacy_provider_rows(conn, disabled: dict[str, bool], top: int) -> list[dict]:
    """Provider rows for DBs created before provider_metrics existed.

    Built from source_stats run history and legacy job strategy counts so the
    report stays truthful on old databases without writing any data.
    """
    found_by_provider: dict[str, int] = {}
    for row in conn.execute(_JOBS_BY_STRATEGY_SQL).fetchall():
        provider = _LEGACY_STRATEGY_PROVIDERS.get(row["strategy"])
        if provider:
            found_by_provider[provider] = found_by_provider.get(provider, 0) + row["n"]

    rows = []
    for row in conn.execute(_LEGACY_RUNS_SQL).fetchall():
        found = found_by_provider.get(row["source_name"], 0)
        rows.append({
            "provider": row["source_name"],
            "runs": row["total_runs"],
            "found": found,
            "stored": found,
            "passed": row["total_passed"],
            "scored": 0,
            "applied": 0,
            "rejected": 0,
            "errors": row["failed_runs"],
            "avg_fit": row["avg_fit"],
            "avg_latency_ms": 0,
            "disabled": disabled.get(row["source_name"], False),
        })
    rows.sort(key=lambda r: r["stored"], reverse=True)
    return rows[: max(int(top), 1)]


def cost_report(conn, days: int = 30) -> dict:
    """Total LLM cost and call count in the window, with top tools."""
    cutoff = _cutoff(days)
    total = conn.execute(_COST_TOTAL_SQL, (cutoff,)).fetchone()
    tools = [
        {
            "tool": row["tool"] or "unknown",
            "calls": row["calls"],
            "cost_usd": round(row["cost"], 4),
        }
        for row in conn.execute(_COST_BY_TOOL_SQL, (cutoff,)).fetchall()
    ]
    return {
        "calls": total["calls"],
        "total_cost_usd": round(total["total_cost"], 4),
        "by_tool": tools,
    }


def run_history(conn, days: int = 30, top: int = 10) -> list[dict]:
    """Recent runs in the window, newest first."""
    rows = conn.execute(_RUNS_SQL, (_cutoff(days), max(int(top), 1))).fetchall()
    return [
        {
            "run_id": row["run_id"],
            "started_at": row["started_at"],
            "goal": row["goal"] or "",
            "status": row["status"] or "",
            "jobs_discovered": row["jobs_discovered"] or 0,
            "jobs_applied": row["jobs_applied"] or 0,
            "total_cost": round(row["total_cost"] or 0.0, 4),
            "total_duration_ms": row["total_duration_ms"] or 0,
        }
        for row in rows
    ]


def build_report(conn=None, days: int = 30, top: int = 10) -> dict:
    """Compose all report sections into one structure."""
    if conn is None:
        conn = get_connection()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_days": days,
        "funnel": pipeline_funnel(conn),
        "providers": provider_report(conn, days, top),
        "cost": cost_report(conn, days),
        "recent_runs": run_history(conn, days, top),
    }


def _fmt_money(usd: float) -> str:
    return f"${usd:.4f}"


def render_report(report: dict) -> str:
    """Render the report dict as a deterministic plain-text report."""
    lines: list[str] = []
    sep = "=" * 62
    lines.append(sep)
    lines.append("  JobOrion Report")
    lines.append(sep)
    lines.append(f"  Window: last {report.get('window_days', 30)} day(s)")
    lines.append("")

    funnel = report.get("funnel") or {}
    if funnel:
        lines.append("Pipeline funnel:")
        lines.append(
            f"  discovered: {funnel.get('discovered', 0):<6} "
            f"enriched: {funnel.get('enriched', 0):<6} "
            f"scored: {funnel.get('scored', 0):<6} "
            f"tailored: {funnel.get('tailored', 0):<6} "
            f"applied: {funnel.get('applied', 0)}"
        )
        lines.append("")

    providers = report.get("providers") or []
    lines.append("Providers:")
    if not providers:
        lines.append("  (no provider data in window)")
    else:
        header = (
            f"  {'provider':<14} {'runs':>5} {'found':>6} {'stored':>6} {'passed':>6} "
            f"{'scored':>6} {'applied':>7} {'rejected':>8} {'errors':>6} {'avg_fit':>8} "
            f"{'avg_ms':>9} state"
        )
        lines.append(header)
        for p in providers:
            state = "disabled" if p.get("disabled") else "ok"
            lines.append(
                f"  {p['provider']:<14} {p['runs']:>5} {p['found']:>6} {p['stored']:>6} "
                f"{p['passed']:>6} {p['scored']:>6} {p['applied']:>7} {p['rejected']:>8} "
                f"{p['errors']:>6} {p['avg_fit']:>8} {p['avg_latency_ms']:>9} {state}"
            )
    lines.append("")

    cost = report.get("cost") or {}
    lines.append("Cost:")
    if not cost or not cost.get("calls"):
        lines.append("  (no LLM cost data in window)")
    else:
        lines.append(
            f"  total: {_fmt_money(cost.get('total_cost_usd', 0.0))} over "
            f"{cost.get('calls', 0)} call(s)"
        )
        for tool in cost.get("by_tool") or []:
            lines.append(
                f"  {tool['tool']:<22} {_fmt_money(tool['cost_usd']):>10}  ({tool['calls']} calls)"
            )
    lines.append("")

    runs = report.get("recent_runs") or []
    lines.append("Recent runs:")
    if not runs:
        lines.append("  (no runs in window)")
    else:
        for r in runs:
            goal = r["goal"][:40] if r["goal"] else "(no goal)"
            lines.append(
                f"  {r['started_at']:<22} {goal:<40} {r['status']:<10} "
                f"{r['jobs_discovered']:>3} jobs | {r['jobs_applied']:>3} applied | "
                f"{_fmt_money(r['total_cost'])} | {r['total_duration_ms']} ms"
            )
        lines.append("")
    lines.append(sep)
    return "\n".join(lines)
