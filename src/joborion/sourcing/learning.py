"""Source learning: per-provider metrics, reliability ordering, auto-disable.

Writes per-run rows to ``provider_metrics`` and maintains the reliability
state in ``source_stats`` (consecutive_failures / disabled / avg_fit). Pure
data layer -- never touches providers directly, so it is safe to call from
any stage.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from joborion.database import get_connection

DEFAULT_DISABLE_THRESHOLD = 3

_METRICS_INSERT = (
    "INSERT INTO provider_metrics "
    "(provider, run_id, run_started_at, found, stored, passed, scored, applied, "
    " rejected, errors, latency_ms, avg_fit) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def record_provider_run(
    conn: sqlite3.Connection | None,
    name: str,
    *,
    found: int = 0,
    stored: int = 0,
    passed: int = 0,
    scored: int = 0,
    applied: int = 0,
    rejected: int = 0,
    errors: int = 0,
    latency_ms: int = 0,
    avg_fit: float | None = None,
    error: str | None = None,
    run_id: str | None = None,
    disable_threshold: int = DEFAULT_DISABLE_THRESHOLD,
) -> dict:
    """Persist one provider run and update its reliability state.

    A successful run (``errors == 0``) clears ``consecutive_failures`` and
    re-enables the provider; a failed run increments the counter and disables
    the provider once it reaches ``disable_threshold``.

    Returns the provider's updated ``source_stats`` row as a dict.
    """
    if conn is None:
        conn = get_connection()

    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        _METRICS_INSERT,
        (name, run_id, now, found, stored, passed, scored, applied, rejected,
         errors, latency_ms, avg_fit),
    )

    success = errors == 0
    row = conn.execute(
        "SELECT * FROM source_stats WHERE source_name = ?", (name,)
    ).fetchone()

    if row:
        total_runs = row["total_runs"] + 1
        success_runs = row["success_runs"] + (1 if success else 0)
        failed_runs = row["failed_runs"] + (0 if success else 1)
        total_jobs = row["total_jobs"] + found
        total_passed = row["total_passed"] + passed
        consecutive = 0 if success else row["consecutive_failures"] + 1
        disabled = 0 if success else (1 if consecutive >= disable_threshold else row["disabled"])
        disabled_at = None if success else (now if disabled and not row["disabled"] else row["disabled_at"])
        total_fit = (row["total_fit"] or 0.0) + (avg_fit or 0.0)
        avg_fit_stored = total_fit / total_runs if avg_fit is not None else row["avg_fit"]

        conn.execute(
            """UPDATE source_stats SET
                total_runs = ?, success_runs = ?, failed_runs = ?, total_jobs = ?,
                total_passed = ?, avg_jobs_per_run = ?, consecutive_failures = ?,
                disabled = ?, disabled_at = ?, total_fit = ?, avg_fit = ?,
                last_success_at = CASE WHEN ? THEN ? ELSE last_success_at END,
                last_failure_at = CASE WHEN NOT ? THEN ? ELSE last_failure_at END,
                last_error = CASE WHEN NOT ? THEN ? ELSE last_error END
            WHERE source_name = ?""",
            (
                total_runs, success_runs, failed_runs, total_jobs, total_passed,
                total_jobs / total_runs, consecutive, disabled, disabled_at,
                total_fit, avg_fit_stored,
                success, now, success, now, success, error, name,
            ),
        )
    else:
        consecutive = 0 if success else 1
        disabled = 1 if consecutive >= disable_threshold else 0
        conn.execute(
            """INSERT INTO source_stats
                (source_name, total_runs, success_runs, failed_runs, total_jobs,
                 total_passed, avg_jobs_per_run, consecutive_failures, disabled,
                 disabled_at, total_fit, avg_fit, last_success_at, last_failure_at,
                 last_error)
            VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                name, 1 if success else 0, 0 if success else 1, found, passed,
                float(found), consecutive, disabled, now if disabled else None,
                avg_fit or 0.0, avg_fit or 0.0,
                now if success else None, now if not success else None,
                error if not success else None,
            ),
        )

    conn.commit()
    row = conn.execute(
        "SELECT * FROM source_stats WHERE source_name = ?", (name,)
    ).fetchone()
    return dict(zip(row.keys(), row))


def provider_states(conn: sqlite3.Connection | None = None) -> list[dict]:
    """Return reliability state for every recorded provider."""
    if conn is None:
        conn = get_connection()
    rows = conn.execute("SELECT * FROM source_stats ORDER BY source_name").fetchall()
    return [dict(zip(row.keys(), row)) for row in rows] if rows else []


def is_provider_disabled(conn: sqlite3.Connection | None, name: str) -> bool:
    """True if the provider is currently marked disabled."""
    if conn is None:
        conn = get_connection()
    row = conn.execute(
        "SELECT disabled FROM source_stats WHERE source_name = ?", (name,)
    ).fetchone()
    return bool(row and row["disabled"])


def auto_disable(
    conn: sqlite3.Connection | None = None,
    threshold: int = DEFAULT_DISABLE_THRESHOLD,
) -> list[str]:
    """Sweep: disable every provider whose consecutive_failures >= threshold.

    Returns the names disabled in this sweep. Providers recover on the next
    successful run via record_provider_run.
    """
    if conn is None:
        conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    rows = conn.execute(
        "SELECT source_name FROM source_stats "
        "WHERE consecutive_failures >= ? AND disabled = 0",
        (threshold,),
    ).fetchall()
    names = [row["source_name"] for row in rows]
    for name in names:
        conn.execute(
            "UPDATE source_stats SET disabled = 1, disabled_at = ? WHERE source_name = ?",
            (now, name),
        )
    conn.commit()
    return names


def reliability_ordering(conn: sqlite3.Connection | None, providers: list) -> list:
    """Sort providers so reliable sources run first and disabled ones last.

    Primary sort is enabled-before-disabled; within each group, success rate
    descending, then average jobs per run descending. Providers with no
    history keep their relative order (stable sort). If the reliability state
    is unreadable, the original order is returned unchanged -- degraded, never
    fatal.
    """
    if conn is None:
        conn = get_connection()

    try:
        states: dict[str, tuple] = {}
        for s in provider_states(conn):
            rate = (s["success_runs"] / s["total_runs"]) if s["total_runs"] else 0.0
            states[s["source_name"]] = (
                int(s["disabled"] or 0),
                -rate,
                -(s["avg_jobs_per_run"] or 0.0),
            )
    except Exception:
        states = {}

    def key(provider) -> tuple:
        return states.get(getattr(provider, "name", "unknown"), (0, 0.0, 0.0))

    return sorted(providers, key=key)
