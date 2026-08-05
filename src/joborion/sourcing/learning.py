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


# ---------------------------------------------------------------------------
# Per-company yield tracking (zero-yield ATS/Workday pruning)
# ---------------------------------------------------------------------------


def note_company_run(
    conn: sqlite3.Connection | None,
    provider: str,
    company: str,
    found: int = 0,
) -> None:
    """Record that a company board was attempted in this run.

    ``found`` is the number of raw jobs the board produced. The company's
    ``consecutive_zero`` counter is only advanced by reconcile_company_yields
    (never here), so a run that fails before the gate cannot over-count.
    """
    if conn is None:
        conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "INSERT INTO company_yield (provider, company, total_runs, last_found, last_run_at) "
        "VALUES (?, ?, 1, ?, ?) "
        "ON CONFLICT(provider, company) DO UPDATE SET "
        "total_runs = total_runs + 1, last_found = excluded.last_found, "
        "last_run_at = excluded.last_run_at",
        (provider, company, found, now),
    )
    conn.commit()


def reconcile_company_yields(
    conn: sqlite3.Connection | None,
    by_company: dict,
    noted: list[tuple[str, str]] | None = None,
) -> None:
    """Apply gate outcomes to company yield counters.

    ``by_company`` maps provider -> company -> {"found", "passed"} for every
    company the relevance gate touched. ``noted`` is a list of (provider,
    company) pairs providers attempted this run. A company advances its
    ``consecutive_zero`` counter exactly once per run: when the gate saw its
    jobs and none passed, or when it produced zero raw jobs. Any passing job
    resets the counter.
    """
    if conn is None:
        conn = get_connection()

    for provider, companies in (by_company or {}).items():
        for company, counts in companies.items():
            passed = counts.get("passed", 0) if isinstance(counts, dict) else counts
            if passed > 0:
                conn.execute(
                    "UPDATE company_yield SET consecutive_zero = 0, last_pass_count = ? "
                    "WHERE provider = ? AND company = ?",
                    (passed, provider, company),
                )
            else:
                conn.execute(
                    "UPDATE company_yield SET consecutive_zero = consecutive_zero + 1, "
                    "last_pass_count = 0 WHERE provider = ? AND company = ?",
                    (provider, company),
                )

    for provider, company in noted or []:
        row = conn.execute(
            "SELECT last_found FROM company_yield WHERE provider = ? AND company = ?",
            (provider, company),
        ).fetchone()
        if row and row["last_found"] == 0:
            conn.execute(
                "UPDATE company_yield SET consecutive_zero = consecutive_zero + 1, "
                "last_pass_count = 0 WHERE provider = ? AND company = ?",
                (provider, company),
            )

    conn.commit()


def prune_zero_yield_companies(
    conn: sqlite3.Connection | None = None,
    threshold: int = 2,
) -> list[str]:
    """Mark companies disabled whose consecutive zero-pass runs reached threshold.

    Returns the pruned company keys as "provider:company" strings.
    """
    if conn is None:
        conn = get_connection()
    now = datetime.now(timezone.utc).isoformat()
    rows = conn.execute(
        "SELECT provider, company FROM company_yield "
        "WHERE consecutive_zero >= ? AND pruned = 0",
        (threshold,),
    ).fetchall()
    keys = [f"{row['provider']}:{row['company']}" for row in rows]
    for row in rows:
        conn.execute(
            "UPDATE company_yield SET pruned = 1, pruned_at = ? "
            "WHERE provider = ? AND company = ?",
            (now, row["provider"], row["company"]),
        )
    conn.commit()
    return keys


def pruned_companies(
    conn: sqlite3.Connection | None,
    provider: str,
) -> set[str]:
    """Return the pruned company names for a provider (skipped on the next run)."""
    if conn is None:
        conn = get_connection()
    rows = conn.execute(
        "SELECT company FROM company_yield WHERE provider = ? AND pruned = 1",
        (provider,),
    ).fetchall()
    return {row["company"] for row in rows}


# ---------------------------------------------------------------------------
# User feedback -> relevance weights
# ---------------------------------------------------------------------------

VALID_SENTIMENTS = ("like", "dislike")


def record_feedback(
    conn: sqlite3.Connection | None,
    job_url: str,
    sentiment: str,
) -> dict:
    """Store a like/dislike for a job and tag the job row for the gate.

    The job's normalized title tokens become positive (like) or negative
    (dislike) weights consumed by the relevance gate's title check.

    Returns:
        {"url", "sentiment", "title", "company"}.
    """
    sentiment = (sentiment or "").strip().lower()
    if sentiment not in VALID_SENTIMENTS:
        raise ValueError(f"sentiment must be one of {VALID_SENTIMENTS}")

    if conn is None:
        conn = get_connection()
    row = conn.execute(
        "SELECT title, company FROM jobs WHERE url = ?", (job_url,)
    ).fetchone()
    title = row["title"] if row else None
    company = row["company"] if row else None

    conn.execute(
        """INSERT INTO user_feedback (job_url, job_title, company, sentiment)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(job_url, sentiment) DO UPDATE SET
               job_title = excluded.job_title,
               company = excluded.company,
               created_at = datetime('now')""",
        (job_url, title, company, sentiment),
    )
    conn.execute(
        "UPDATE jobs SET user_feedback = ? WHERE url = ?",
        (sentiment, job_url),
    )
    conn.commit()
    return {"url": job_url, "sentiment": sentiment, "title": title, "company": company}


def feedback_title_terms(conn: sqlite3.Connection | None) -> dict[str, int]:
    """Net weight per normalized title token across all feedback.

    A token seen in a liked job counts +1, in a disliked job -1, so the
    relevance gate can down-weight titles carrying strongly disliked terms.
    """
    if conn is None:
        conn = get_connection()
    from joborion.sourcing.normalize import normalize_title

    weights: dict[str, int] = {}
    rows = conn.execute(
        "SELECT job_title, sentiment FROM user_feedback "
        "WHERE job_title IS NOT NULL"
    ).fetchall()
    for row in rows:
        tokens = normalize_title(row["job_title"]).split()
        delta = 1 if row["sentiment"] == "like" else -1
        for token in tokens:
            if len(token) < 3:
                continue
            weights[token] = weights.get(token, 0) + delta
    return weights
