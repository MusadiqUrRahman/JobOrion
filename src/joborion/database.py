"""JobOrion database layer: schema, migrations, stats, and connection helpers.

Single source of truth for the jobs table schema. All columns from every
pipeline stage are created up front so any stage can run independently
without migration ordering issues.
"""

import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from joborion.config import DB_PATH

# Thread-local connection storage — each thread gets its own connection
# (required for SQLite thread safety with parallel workers)
_local = threading.local()


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Get a thread-local cached SQLite connection with WAL mode enabled.

    Each thread gets its own connection (required for SQLite thread safety).
    Connections are cached and reused within the same thread.

    Args:
        db_path: Override the default DB_PATH. Useful for testing.

    Returns:
        sqlite3.Connection configured with WAL mode and row factory.
    """
    path = str(db_path or DB_PATH)

    if not hasattr(_local, 'connections'):
        _local.connections = {}

    conn = _local.connections.get(path)
    if conn is not None:
        try:
            conn.execute("SELECT 1")
            return conn
        except sqlite3.ProgrammingError:
            pass

    conn = sqlite3.connect(path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.row_factory = sqlite3.Row
    _local.connections[path] = conn
    return conn


def close_connection(db_path: Path | str | None = None) -> None:
    """Close the cached connection for the current thread."""
    path = str(db_path or DB_PATH)
    if hasattr(_local, 'connections'):
        conn = _local.connections.pop(path, None)
        if conn is not None:
            conn.close()


def init_db(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Create the full jobs table with all columns from every pipeline stage.

    This is idempotent -- safe to call on every startup. Uses CREATE TABLE IF NOT EXISTS
    so it won't destroy existing data.

    Schema columns by stage:
      - Discovery:  url, title, salary, description, location, site, strategy, discovered_at
      - Enrichment: full_description, application_url, detail_scraped_at, detail_error
      - Scoring:    fit_score, score_reasoning, scored_at
      - Tailoring:  tailored_resume_path, tailored_at, tailor_attempts
      - Cover:      cover_letter_path, cover_letter_at, cover_attempts
      - Apply:      applied_at, apply_status, apply_error, apply_attempts,
                   agent_id, last_attempted_at, apply_duration_ms, apply_task_id,
                   verification_confidence

    Also creates tables for source reliability tracking and validation error memory.

    Args:
        db_path: Override the default DB_PATH.

    Returns:
        sqlite3.Connection with the schema initialized.
    """
    path = db_path or DB_PATH

    # Ensure parent directory exists
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    conn = get_connection(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            -- Discovery stage (smart_extract / job_search)
            url                   TEXT PRIMARY KEY,
            title                 TEXT,
            salary                TEXT,
            description           TEXT,
            location              TEXT,
            site                  TEXT,
            strategy              TEXT,
            discovered_at         TEXT,

            -- Enrichment stage (detail_scraper)
            full_description      TEXT,
            application_url       TEXT,
            detail_scraped_at     TEXT,
            detail_error          TEXT,

            -- Scoring stage (job_scorer)
            fit_score             INTEGER,
            score_reasoning       TEXT,
            scored_at             TEXT,

            -- Tailoring stage (resume tailor)
            tailored_resume_path  TEXT,
            tailored_at           TEXT,
            tailor_attempts       INTEGER DEFAULT 0,

            -- Cover letter stage
            cover_letter_path     TEXT,
            cover_letter_at       TEXT,
            cover_attempts        INTEGER DEFAULT 0,

            -- Application stage
            applied_at            TEXT,
            apply_status          TEXT,
            apply_error           TEXT,
            apply_attempts        INTEGER DEFAULT 0,
            agent_id              TEXT,
            last_attempted_at     TEXT,
            apply_duration_ms     INTEGER,
            apply_task_id         TEXT,
            verification_confidence TEXT
        )
    """)

    # Source reliability tracking
    conn.execute("""
        CREATE TABLE IF NOT EXISTS source_stats (
            source_name     TEXT PRIMARY KEY,
            total_runs      INTEGER DEFAULT 0,
            success_runs    INTEGER DEFAULT 0,
            failed_runs     INTEGER DEFAULT 0,
            total_jobs      INTEGER DEFAULT 0,
            last_success_at TEXT,
            last_failure_at TEXT,
            last_error      TEXT,
            avg_jobs_per_run REAL DEFAULT 0.0
        )
    """)

    # Validation error memory
    conn.execute("""
        CREATE TABLE IF NOT EXISTS validation_errors (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            stage           TEXT NOT NULL,
            job_url         TEXT,
            error_type      TEXT NOT NULL,
            error_message   TEXT,
            attempt_number  INTEGER,
            created_at      TEXT DEFAULT (datetime('now'))
        )
    """)

    # Run history
    conn.execute("""
        CREATE TABLE IF NOT EXISTS run_history (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            run_started_at  TEXT,
            run_completed_at TEXT,
            stages_run      TEXT,
            total_jobs      INTEGER DEFAULT 0,
            jobs_enriched   INTEGER DEFAULT 0,
            jobs_scored     INTEGER DEFAULT 0,
            jobs_tailored   INTEGER DEFAULT 0,
            jobs_covered    INTEGER DEFAULT 0,
            llm_calls       INTEGER DEFAULT 0,
            errors          TEXT,
            elapsed_seconds REAL DEFAULT 0.0
        )
    """)

    # Site memory — tracks per-site extraction success/failure for smart routing
    conn.execute("""
        CREATE TABLE IF NOT EXISTS site_memory (
            site_name               TEXT PRIMARY KEY,
            total_attempts          INTEGER DEFAULT 0,
            successful_extractions  INTEGER DEFAULT 0,
            successful_applications INTEGER DEFAULT 0,
            avg_extraction_time_ms  INTEGER DEFAULT 0,
            preferred_strategy      TEXT,
            blocked_reason          TEXT,
            last_attempted_at       TEXT,
            notes                   TEXT
        )
    """)

    # Run log — structured record of each pipeline execution
    conn.execute("""
        CREATE TABLE IF NOT EXISTS run_log (
            run_id                TEXT PRIMARY KEY,
            started_at            TEXT,
            completed_at          TEXT,
            goal                  TEXT,
            plan                  TEXT,
            stages_run            TEXT,
            jobs_discovered       INTEGER DEFAULT 0,
            jobs_enriched         INTEGER DEFAULT 0,
            jobs_scored           INTEGER DEFAULT 0,
            jobs_tailored         INTEGER DEFAULT 0,
            jobs_covered          INTEGER DEFAULT 0,
            jobs_applied          INTEGER DEFAULT 0,
            total_cost            REAL DEFAULT 0.0,
            total_duration_ms     INTEGER DEFAULT 0,
            status                TEXT,
            errors                TEXT,
            reflection_id         TEXT
        )
    """)

    # Cost ledger — per-action cost tracking
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cost_ledger (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id                TEXT,
            action                TEXT,
            tool                  TEXT,
            tokens_in             INTEGER DEFAULT 0,
            tokens_out            INTEGER DEFAULT 0,
            cost_usd              REAL DEFAULT 0.0,
            recorded_at           TEXT
        )
    """)

    conn.commit()

    # Run migrations for any columns added after initial schema
    ensure_columns(conn)

    return conn


# Complete column registry: column_name -> SQL type with optional default.
# This is the single source of truth. Adding a column here is all that's needed
# for it to appear in both new databases and migrated ones.
_ALL_COLUMNS: dict[str, str] = {
    # Discovery
    "url": "TEXT PRIMARY KEY",
    "title": "TEXT",
    "salary": "TEXT",
    "description": "TEXT",
    "location": "TEXT",
    "site": "TEXT",
    "strategy": "TEXT",
    "discovered_at": "TEXT",
    # Enrichment
    "full_description": "TEXT",
    "application_url": "TEXT",
    "detail_scraped_at": "TEXT",
    "detail_error": "TEXT",
    # Scoring
    "fit_score": "INTEGER",
    "score_reasoning": "TEXT",
    "scored_at": "TEXT",
    # Tailoring
    "tailored_resume_path": "TEXT",
    "tailored_at": "TEXT",
    "tailor_attempts": "INTEGER DEFAULT 0",
    # Cover letter
    "cover_letter_path": "TEXT",
    "cover_letter_at": "TEXT",
    "cover_attempts": "INTEGER DEFAULT 0",
    # Application
    "applied_at": "TEXT",
    "apply_status": "TEXT",
    "apply_error": "TEXT",
    "apply_attempts": "INTEGER DEFAULT 0",
    "agent_id": "TEXT",
    "last_attempted_at": "TEXT",
    "apply_duration_ms": "INTEGER",
    "apply_task_id": "TEXT",
    "verification_confidence": "TEXT",
}


def ensure_columns(conn: sqlite3.Connection | None = None) -> list[str]:
    """Add any missing columns to the jobs table (forward migration).

    Reads the current table schema via PRAGMA table_info and compares against
    the full column registry. Any missing columns are added with ALTER TABLE.

    This makes it safe to upgrade the database from any previous version --
    columns are only added, never removed or renamed.

    Args:
        conn: Database connection. Uses get_connection() if None.

    Returns:
        List of column names that were added (empty if schema was already current).
    """
    if conn is None:
        conn = get_connection()

    existing = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    added = []

    for col, dtype in _ALL_COLUMNS.items():
        if col not in existing:
            # PRIMARY KEY columns can't be added via ALTER TABLE, but url
            # is always created with the table itself so this is safe
            if "PRIMARY KEY" in dtype:
                continue
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {dtype}")
            added.append(col)

    if added:
        conn.commit()

    return added


def get_stats(conn: sqlite3.Connection | None = None) -> dict:
    """Return job counts by pipeline stage.

    Provides a snapshot of how many jobs are at each stage, useful for
    dashboard display and pipeline progress tracking.

    Args:
        conn: Database connection. Uses get_connection() if None.

    Returns:
        Dictionary with keys:
            total, by_site, pending_detail, with_description,
            scored, unscored, tailored, untailored_eligible,
            with_cover_letter, applied, score_distribution
    """
    if conn is None:
        conn = get_connection()

    stats: dict = {}

    # Total jobs
    stats["total"] = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

    # By site breakdown
    rows = conn.execute(
        "SELECT site, COUNT(*) as cnt FROM jobs GROUP BY site ORDER BY cnt DESC"
    ).fetchall()
    stats["by_site"] = [(row[0], row[1]) for row in rows]

    # Enrichment stage
    stats["pending_detail"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE detail_scraped_at IS NULL"
    ).fetchone()[0]

    stats["with_description"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE full_description IS NOT NULL"
    ).fetchone()[0]

    stats["detail_errors"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE detail_error IS NOT NULL"
    ).fetchone()[0]

    # Scoring stage
    stats["scored"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE fit_score IS NOT NULL"
    ).fetchone()[0]

    stats["unscored"] = conn.execute(
        "SELECT COUNT(*) FROM jobs "
        "WHERE full_description IS NOT NULL AND fit_score IS NULL"
    ).fetchone()[0]

    # Score distribution
    dist_rows = conn.execute(
        "SELECT fit_score, COUNT(*) as cnt FROM jobs "
        "WHERE fit_score IS NOT NULL "
        "GROUP BY fit_score ORDER BY fit_score DESC"
    ).fetchall()
    stats["score_distribution"] = [(row[0], row[1]) for row in dist_rows]

    # Tailoring stage
    stats["tailored"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL"
    ).fetchone()[0]

    stats["untailored_eligible"] = conn.execute(
        "SELECT COUNT(*) FROM jobs "
        "WHERE fit_score >= 7 AND full_description IS NOT NULL "
        "AND tailored_resume_path IS NULL"
    ).fetchone()[0]

    stats["tailor_exhausted"] = conn.execute(
        "SELECT COUNT(*) FROM jobs "
        "WHERE COALESCE(tailor_attempts, 0) >= 5 "
        "AND tailored_resume_path IS NULL"
    ).fetchone()[0]

    # Cover letter stage
    stats["with_cover_letter"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE cover_letter_path IS NOT NULL"
    ).fetchone()[0]

    stats["cover_exhausted"] = conn.execute(
        "SELECT COUNT(*) FROM jobs "
        "WHERE COALESCE(cover_attempts, 0) >= 5 "
        "AND (cover_letter_path IS NULL OR cover_letter_path = '')"
    ).fetchone()[0]

    # Application stage
    stats["applied"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE applied_at IS NOT NULL"
    ).fetchone()[0]

    stats["apply_errors"] = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE apply_error IS NOT NULL"
    ).fetchone()[0]

    stats["ready_to_apply"] = conn.execute(
        "SELECT COUNT(*) FROM jobs "
        "WHERE tailored_resume_path IS NOT NULL "
        "AND applied_at IS NULL "
        "AND application_url IS NOT NULL"
    ).fetchone()[0]

    return stats


def store_jobs(conn: sqlite3.Connection, jobs: list[dict],
               site: str, strategy: str) -> tuple[int, int]:
    """Store discovered jobs, skipping duplicates by URL.

    Args:
        conn: Database connection.
        jobs: List of job dicts with keys: url, title, salary, description, location.
        site: Source site name (e.g. "RemoteOK", "Dice").
        strategy: Extraction strategy used (e.g. "json_ld", "api_response", "css_selectors").

    Returns:
        Tuple of (new_count, duplicate_count).
    """
    now = datetime.now(timezone.utc).isoformat()
    new = 0
    existing = 0

    for job in jobs:
        url = job.get("url")
        if not url:
            continue
        try:
            conn.execute(
                "INSERT INTO jobs (url, title, salary, description, location, site, strategy, discovered_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (url, job.get("title"), job.get("salary"), job.get("description"),
                 job.get("location"), site, strategy, now),
            )
            new += 1
        except sqlite3.IntegrityError:
            existing += 1

    conn.commit()
    return new, existing


def get_jobs_by_stage(conn: sqlite3.Connection | None = None,
                      stage: str = "discovered",
                      min_score: int | None = None,
                      limit: int = 100) -> list[dict]:
    """Fetch jobs filtered by pipeline stage.

    Args:
        conn: Database connection. Uses get_connection() if None.
        stage: One of "discovered", "enriched", "scored", "tailored", "applied".
        min_score: Minimum fit_score filter (only relevant for scored+ stages).
        limit: Maximum number of rows to return.

    Returns:
        List of job dicts.
    """
    if conn is None:
        conn = get_connection()

    conditions = {
        "discovered": "1=1",
        "pending_detail": "detail_scraped_at IS NULL",
        "enriched": "full_description IS NOT NULL",
        "pending_score": "full_description IS NOT NULL AND fit_score IS NULL",
        "scored": "fit_score IS NOT NULL",
        "pending_tailor": (
            "fit_score >= ? AND full_description IS NOT NULL "
            "AND tailored_resume_path IS NULL AND COALESCE(tailor_attempts, 0) < 5"
        ),
        "tailored": "tailored_resume_path IS NOT NULL",
        "pending_apply": (
            "tailored_resume_path IS NOT NULL AND applied_at IS NULL "
            "AND application_url IS NOT NULL"
        ),
        "applied": "applied_at IS NOT NULL",
    }

    where = conditions.get(stage, "1=1")
    params: list = []

    if "?" in where and min_score is not None:
        params.append(min_score)
    elif "?" in where:
        params.append(7)  # default min_score

    if min_score is not None and "fit_score" not in where and stage in ("scored", "tailored", "applied"):
        where += " AND fit_score >= ?"
        params.append(min_score)

    query = f"SELECT * FROM jobs WHERE {where} ORDER BY fit_score DESC NULLS LAST, discovered_at DESC"
    if limit > 0:
        query += " LIMIT ?"
        params.append(limit)

    rows = conn.execute(query, params).fetchall()

    # Convert sqlite3.Row objects to dicts
    if rows:
        columns = rows[0].keys()
        return [dict(zip(columns, row)) for row in rows]
    return []


# ---------------------------------------------------------------------------
# Source reliability tracking
# ---------------------------------------------------------------------------

def record_source_run(
    source_name: str,
    success: bool,
    jobs_found: int = 0,
    error: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Record the result of a discovery source run for reliability tracking.

    Args:
        source_name: Name of the source (e.g., "jobspy", "workday", "smartextract").
        success: Whether the source run succeeded.
        jobs_found: Number of jobs found in this run.
        error: Error message if the run failed.
        conn: Database connection. Uses get_connection() if None.
    """
    if conn is None:
        conn = get_connection()

    now = datetime.now(timezone.utc).isoformat()

    # Check if source exists
    existing = conn.execute(
        "SELECT * FROM source_stats WHERE source_name = ?", (source_name,)
    ).fetchone()

    if existing:
        # Update existing record
        total_runs = existing["total_runs"] + 1
        success_runs = existing["success_runs"] + (1 if success else 0)
        failed_runs = existing["failed_runs"] + (0 if success else 1)
        total_jobs = existing["total_jobs"] + jobs_found
        avg_jobs = total_jobs / total_runs if total_runs > 0 else 0.0

        conn.execute(
            """UPDATE source_stats SET
                total_runs = ?,
                success_runs = ?,
                failed_runs = ?,
                total_jobs = ?,
                avg_jobs_per_run = ?,
                last_success_at = CASE WHEN ? THEN ? ELSE last_success_at END,
                last_failure_at = CASE WHEN NOT ? THEN ? ELSE last_failure_at END,
                last_error = CASE WHEN NOT ? THEN ? ELSE last_error END
            WHERE source_name = ?""",
            (
                total_runs, success_runs, failed_runs, total_jobs, avg_jobs,
                success, now, success, now, success, error, source_name,
            ),
        )
    else:
        # Insert new record
        conn.execute(
            """INSERT INTO source_stats
                (source_name, total_runs, success_runs, failed_runs, total_jobs,
                 last_success_at, last_failure_at, last_error, avg_jobs_per_run)
            VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?)""",
            (
                source_name,
                1 if success else 0,
                0 if success else 1,
                jobs_found,
                now if success else None,
                now if not success else None,
                error,
                float(jobs_found),
            ),
        )

    conn.commit()


def get_source_reliability(
    min_runs: int = 3,
    conn: sqlite3.Connection | None = None,
) -> list[dict]:
    """Get source reliability stats, sorted by success rate.

    Args:
        min_runs: Minimum runs required to include a source.
        conn: Database connection. Uses get_connection() if None.

    Returns:
        List of dicts with source stats, sorted by success rate descending.
    """
    if conn is None:
        conn = get_connection()

    rows = conn.execute(
        """SELECT *,
            CASE WHEN total_runs > 0
                THEN (success_runs * 1.0 / total_runs)
                ELSE 0.0
            END as success_rate
        FROM source_stats
        WHERE total_runs >= ?
        ORDER BY success_rate DESC, avg_jobs_per_run DESC""",
        (min_runs,),
    ).fetchall()

    if rows:
        columns = rows[0].keys()
        return [dict(zip(columns, row)) for row in rows]
    return []


# ---------------------------------------------------------------------------
# Validation error memory
# ---------------------------------------------------------------------------

def record_validation_error(
    stage: str,
    job_url: str | None,
    error_type: str,
    error_message: str,
    attempt_number: int | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Record a validation error for learning from past mistakes.

    Args:
        stage: Pipeline stage where error occurred (e.g., "tailor", "cover").
        job_url: URL of the job that caused the error.
        error_type: Type of error (e.g., "banned_word", "fabrication", "json_parse").
        error_message: Detailed error message.
        attempt_number: Which attempt this was.
        conn: Database connection. Uses get_connection() if None.
    """
    if conn is None:
        conn = get_connection()

    conn.execute(
        """INSERT INTO validation_errors
            (stage, job_url, error_type, error_message, attempt_number)
        VALUES (?, ?, ?, ?, ?)""",
        (stage, job_url, error_type, error_message, attempt_number),
    )
    conn.commit()


def get_recent_validation_errors(
    stage: str | None = None,
    limit: int = 50,
    conn: sqlite3.Connection | None = None,
) -> list[dict]:
    """Get recent validation errors to learn from past mistakes.

    Args:
        stage: Filter by pipeline stage (None for all stages).
        limit: Maximum errors to return.
        conn: Database connection. Uses get_connection() if None.

    Returns:
        List of error dicts, most recent first.
    """
    if conn is None:
        conn = get_connection()

    if stage:
        rows = conn.execute(
            """SELECT * FROM validation_errors
            WHERE stage = ?
            ORDER BY created_at DESC LIMIT ?""",
            (stage, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT * FROM validation_errors
            ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()

    if rows:
        columns = rows[0].keys()
        return [dict(zip(columns, row)) for row in rows]
    return []


def get_validation_error_summary(
    stage: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> dict[str, int]:
    """Get a summary of validation errors by type.

    Args:
        stage: Filter by pipeline stage (None for all stages).
        conn: Database connection. Uses get_connection() if None.

    Returns:
        Dict mapping error_type to count.
    """
    if conn is None:
        conn = get_connection()

    if stage:
        rows = conn.execute(
            """SELECT error_type, COUNT(*) as cnt
            FROM validation_errors
            WHERE stage = ?
            GROUP BY error_type
            ORDER BY cnt DESC""",
            (stage,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT error_type, COUNT(*) as cnt
            FROM validation_errors
            GROUP BY error_type
            ORDER BY cnt DESC""",
        ).fetchall()

    return {row[0]: row[1] for row in rows}


# ---------------------------------------------------------------------------
# Site memory — per-site extraction success/failure for smart routing
# ---------------------------------------------------------------------------

def record_site_attempt(
    site_name: str,
    success: bool,
    duration_ms: int = 0,
    strategy: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Record a site extraction attempt for memory-aware routing.

    Updates counters: total_attempts, successful_extractions, avg_extraction_time_ms.
    Sets blocked_reason when consecutive failures exceed threshold.

    Args:
        site_name: Name of the site (e.g., "RemoteOK", "Dice").
        success: Whether the extraction succeeded.
        duration_ms: How long the extraction took in milliseconds.
        strategy: Strategy used for extraction (e.g., "json_ld", "api").
        conn: Database connection. Uses get_connection() if None.
    """
    if conn is None:
        conn = get_connection()

    now = datetime.now(timezone.utc).isoformat()

    existing = conn.execute(
        "SELECT * FROM site_memory WHERE site_name = ?", (site_name,)
    ).fetchone()

    if existing:
        total = existing["total_attempts"] + 1
        successful = existing["successful_extractions"] + (1 if success else 0)
        avg_ms = (
            ((existing["avg_extraction_time_ms"] * existing["total_attempts"]) + duration_ms) // total
            if total > 0 else duration_ms
        )
        # Block if 3+ consecutive failures
        blocked = None
        if not success:
            # Count recent consecutive failures
            failures = conn.execute(
                """SELECT COUNT(*) FROM (
                    SELECT 1 FROM validation_errors
                    WHERE stage = 'site_memory' AND job_url = ?
                    ORDER BY created_at DESC LIMIT 3
                )""",
                (site_name,),
            ).fetchone()[0]
            if failures >= 2:  # This is failure #3
                blocked = f"3+ consecutive failures as of {now}"

        conn.execute(
            """UPDATE site_memory SET
                total_attempts = ?,
                successful_extractions = ?,
                avg_extraction_time_ms = ?,
                preferred_strategy = COALESCE(?, preferred_strategy),
                blocked_reason = COALESCE(?, blocked_reason),
                last_attempted_at = ?
            WHERE site_name = ?""",
            (total, successful, avg_ms, strategy, blocked, now, site_name),
        )
    else:
        conn.execute(
            """INSERT INTO site_memory
                (site_name, total_attempts, successful_extractions,
                 avg_extraction_time_ms, preferred_strategy, last_attempted_at)
            VALUES (?, 1, ?, ?, ?, ?)""",
            (site_name, 1 if success else 0, duration_ms, strategy, now),
        )

    conn.commit()


def get_site_memory(site_name: str, conn: sqlite3.Connection | None = None) -> dict | None:
    """Get a site's memory record.

    Args:
        site_name: Name of the site.
        conn: Database connection. Uses get_connection() if None.

    Returns:
        Dict with site memory fields, or None if not found.
    """
    if conn is None:
        conn = get_connection()

    row = conn.execute(
        "SELECT * FROM site_memory WHERE site_name = ?", (site_name,)
    ).fetchone()
    if row:
        return dict(zip(row.keys(), row))
    return None


def get_reliable_sites(conn: sqlite3.Connection | None = None) -> list[str]:
    """Get sites with >50% success rate (at least 2 attempts).

    Args:
        conn: Database connection. Uses get_connection() if None.

    Returns:
        List of site names sorted by success rate descending.
    """
    if conn is None:
        conn = get_connection()

    rows = conn.execute(
        """SELECT site_name FROM site_memory
        WHERE total_attempts >= 2
        AND (successful_extractions * 1.0 / total_attempts) > 0.5
        ORDER BY (successful_extractions * 1.0 / total_attempts) DESC"""
    ).fetchall()
    return [row[0] for row in rows]


def get_blocked_sites_from_memory(conn: sqlite3.Connection | None = None) -> list[str]:
    """Get sites with blocked_reason set (3+ consecutive failures).

    Args:
        conn: Database connection. Uses get_connection() if None.

    Returns:
        List of blocked site names.
    """
    if conn is None:
        conn = get_connection()

    rows = conn.execute(
        "SELECT site_name FROM site_memory WHERE blocked_reason IS NOT NULL"
    ).fetchall()
    return [row[0] for row in rows]


def unblock_site(site_name: str, conn: sqlite3.Connection | None = None) -> bool:
    """Remove blocked_reason for a site, allowing retries.

    Args:
        site_name: Name of the site to unblock.
        conn: Database connection. Uses get_connection() if None.

    Returns:
        True if the site was unblocked, False if not found or not blocked.
    """
    if conn is None:
        conn = get_connection()

    existing = conn.execute(
        "SELECT blocked_reason FROM site_memory WHERE site_name = ?", (site_name,)
    ).fetchone()
    if existing and existing["blocked_reason"]:
        conn.execute(
            "UPDATE site_memory SET blocked_reason = NULL WHERE site_name = ?",
            (site_name,),
        )
        conn.commit()
        return True
    return False


# ---------------------------------------------------------------------------
# Run log — structured record of each pipeline execution
# ---------------------------------------------------------------------------

def start_run(goal: str = "", conn: sqlite3.Connection | None = None) -> str:
    """Create a new run log entry and return the run_id.

    Args:
        goal: The user's goal for this run (e.g., "find remote Python jobs").
        conn: Database connection. Uses get_connection() if None.

    Returns:
        Unique run_id string.
    """
    if conn is None:
        conn = get_connection()

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """INSERT INTO run_log (run_id, started_at, goal, status)
        VALUES (?, ?, ?, 'running')""",
        (run_id, now, goal),
    )
    conn.commit()
    return run_id


def finish_run(
    run_id: str,
    stats: dict | None = None,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Update a run log entry with completion data.

    Args:
        run_id: The run to update.
        stats: Dict with optional keys: stages_run, jobs_discovered, jobs_enriched,
               jobs_scored, jobs_tailored, jobs_covered, jobs_applied,
               total_cost, total_duration_ms, status, errors.
        conn: Database connection. Uses get_connection() if None.
    """
    if conn is None:
        conn = get_connection()
    if stats is None:
        stats = {}

    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """UPDATE run_log SET
            completed_at = ?,
            stages_run = ?,
            jobs_discovered = ?,
            jobs_enriched = ?,
            jobs_scored = ?,
            jobs_tailored = ?,
            jobs_covered = ?,
            jobs_applied = ?,
            total_cost = ?,
            total_duration_ms = ?,
            status = ?,
            errors = ?
        WHERE run_id = ?""",
        (
            now,
            stats.get("stages_run"),
            stats.get("jobs_discovered", 0),
            stats.get("jobs_enriched", 0),
            stats.get("jobs_scored", 0),
            stats.get("jobs_tailored", 0),
            stats.get("jobs_covered", 0),
            stats.get("jobs_applied", 0),
            stats.get("total_cost", 0.0),
            stats.get("total_duration_ms", 0),
            stats.get("status", "completed"),
            stats.get("errors"),
            run_id,
        ),
    )
    conn.commit()


def get_recent_runs(n: int = 10, conn: sqlite3.Connection | None = None) -> list[dict]:
    """Get the most recent N run log entries.

    Args:
        n: Number of runs to return.
        conn: Database connection. Uses get_connection() if None.

    Returns:
        List of run dicts, most recent first.
    """
    if conn is None:
        conn = get_connection()

    rows = conn.execute(
        "SELECT * FROM run_log ORDER BY started_at DESC LIMIT ?", (n,)
    ).fetchall()
    if rows:
        return [dict(zip(row.keys(), row)) for row in rows]
    return []


# ---------------------------------------------------------------------------
# Cost ledger — per-action cost tracking
# ---------------------------------------------------------------------------

def record_cost(
    run_id: str,
    action: str,
    tool: str,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_usd: float = 0.0,
    conn: sqlite3.Connection | None = None,
) -> None:
    """Record an LLM call cost in the ledger.

    Args:
        run_id: The run this cost belongs to.
        action: What action was performed (e.g., "score", "tailor", "plan").
        tool: Which tool/model was used (e.g., "gemini-2.0-flash").
        tokens_in: Input tokens consumed.
        tokens_out: Output tokens produced.
        cost_usd: Cost in US dollars.
        conn: Database connection. Uses get_connection() if None.
    """
    if conn is None:
        conn = get_connection()

    now = datetime.now(timezone.utc).isoformat()

    conn.execute(
        """INSERT INTO cost_ledger
            (run_id, action, tool, tokens_in, tokens_out, cost_usd, recorded_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (run_id, action, tool, tokens_in, tokens_out, cost_usd, now),
    )
    conn.commit()


def get_run_cost(run_id: str, conn: sqlite3.Connection | None = None) -> float:
    """Get total cost for a specific run.

    Args:
        run_id: The run to check.
        conn: Database connection. Uses get_connection() if None.

    Returns:
        Total cost in USD.
    """
    if conn is None:
        conn = get_connection()

    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0.0) FROM cost_ledger WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    return float(row[0]) if row else 0.0


def get_total_cost(conn: sqlite3.Connection | None = None) -> float:
    """Get all-time total cost across all runs.

    Args:
        conn: Database connection. Uses get_connection() if None.

    Returns:
        Total cost in USD.
    """
    if conn is None:
        conn = get_connection()

    row = conn.execute("SELECT COALESCE(SUM(cost_usd), 0.0) FROM cost_ledger").fetchone()
    return float(row[0]) if row else 0.0
