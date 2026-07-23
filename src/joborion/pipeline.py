"""JobOrion Pipeline Orchestrator.

Runs pipeline stages in sequence or concurrently (streaming mode).

Usage (via CLI):
    joborion run                        # all stages, sequential
    joborion run --stream               # all stages, concurrent
    joborion run search details         # specific stages
    joborion run evaluate tailor letter # LLM-only stages
    joborion run --dry-run              # preview without executing
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from joborion.config import load_env, ensure_dirs
from joborion.database import (
    init_db, get_connection, get_stats, record_source_run,
    get_reliable_sites, get_blocked_sites_from_memory, record_site_attempt,
    start_run, finish_run,
)
from joborion.llm import get_client

log = logging.getLogger(__name__)
console = Console()


# ---------------------------------------------------------------------------
# Stage definitions
# ---------------------------------------------------------------------------

STAGE_ORDER = ("search", "details", "evaluate", "tailor", "letter", "export")

STAGE_META: dict[str, dict] = {
    "search":   {"desc": "Job search (JobSpy + Workday + smart extract)"},
    "details":  {"desc": "Detail enrichment (full descriptions + apply URLs)"},
    "evaluate": {"desc": "LLM scoring (fit 1-10)"},
    "tailor":   {"desc": "Resume tailoring (LLM + validation)"},
    "letter":   {"desc": "Cover letter generation"},
    "export":   {"desc": "PDF conversion (tailored resumes + cover letters)"},
}

# Upstream dependency: a stage only finishes when its upstream is done AND
# it has no remaining pending work.
UPSTREAM_DEPS: dict[str, str | None] = {
    "search":   None,
    "details":  "search",
    "evaluate": "details",
    "tailor":   "evaluate",
    "letter":   "tailor",
    "export":   "letter",
}


# ---------------------------------------------------------------------------
# Individual stage runners
# ---------------------------------------------------------------------------

def _run_discovery_stage(workers: int = 1) -> dict:
    """Stage: Job discovery — JobSpy, Workday, and smart-extract scrapers.

    Uses smart source routing: checks site_memory to skip blocked sources,
    prioritize reliable sources, and record attempt results.
    """
    stats: dict = {"jobspy": None, "workday": None, "smartextract": None}

    # Get blocked sites from memory — skip these entirely
    blocked = get_blocked_sites_from_memory()
    if blocked:
        console.print(f"  [yellow]Skipping blocked sites: {', '.join(blocked)}[/yellow]")

    # Get reliable sites for prioritization
    reliable = get_reliable_sites()
    default_order = ["jobspy", "workday", "smartextract"]

    if reliable:
        # Put reliable sources first, then the rest
        source_order = reliable + [s for s in default_order if s not in reliable]
    else:
        source_order = list(default_order)

    # Filter out blocked sources
    source_order = [s for s in source_order if s not in blocked]

    # Run sources in order
    for source in source_order:
        if source == "jobspy":
            console.print("  [cyan]JobSpy full crawl...[/cyan]")
            try:
                from joborion.discovery.jobspy import scrape_jobspy
                import time
                t0 = time.time()
                scrape_jobspy()
                elapsed_ms = int((time.time() - t0) * 1000)
                stats["jobspy"] = "ok"
                record_source_run("jobspy", success=True, jobs_found=0)
                record_site_attempt("jobspy", success=True, duration_ms=elapsed_ms)
            except Exception as e:
                log.error("JobSpy crawl failed: %s", e)
                console.print(f"  [red]JobSpy error:[/red] {e}")
                stats["jobspy"] = f"error: {e}"
                record_source_run("jobspy", success=False, error=str(e))
                record_site_attempt("jobspy", success=False)

        elif source == "workday":
            console.print("  [cyan]Workday corporate scraper...[/cyan]")
            try:
                from joborion.discovery.workday import scrape_workday
                import time
                t0 = time.time()
                scrape_workday(workers=workers)
                elapsed_ms = int((time.time() - t0) * 1000)
                stats["workday"] = "ok"
                record_source_run("workday", success=True, jobs_found=0)
                record_site_attempt("workday", success=True, duration_ms=elapsed_ms)
            except Exception as e:
                log.error("Workday scraper failed: %s", e)
                console.print(f"  [red]Workday error:[/red] {e}")
                stats["workday"] = f"error: {e}"
                record_source_run("workday", success=False, error=str(e))
                record_site_attempt("workday", success=False)

        elif source == "smartextract":
            console.print("  [cyan]Smart extract (AI-powered scraping)...[/cyan]")
            try:
                from joborion.discovery.ai_scraper import scrape_ai_sites
                import time
                t0 = time.time()
                scrape_ai_sites(workers=workers)
                elapsed_ms = int((time.time() - t0) * 1000)
                stats["smartextract"] = "ok"
                record_source_run("smartextract", success=True, jobs_found=0)
                record_site_attempt("smartextract", success=True, duration_ms=elapsed_ms)
            except Exception as e:
                log.error("Smart extract failed: %s", e)
                console.print(f"  [red]Smart extract error:[/red] {e}")
                stats["smartextract"] = f"error: {e}"
                record_source_run("smartextract", success=False, error=str(e))
                record_site_attempt("smartextract", success=False)

    return stats


def _run_enrichment_stage(workers: int = 1) -> dict:
    """Stage: Detail enrichment — scrape full descriptions and apply URLs."""
    try:
        from joborion.enrichment.page_scraper import enrich_jobs
        enrich_jobs(workers=workers)
        return {"status": "ok"}
    except Exception as e:
        log.error("Enrichment failed: %s", e)
        return {"status": f"error: {e}"}


def _run_scoring_stage() -> dict:
    """Stage: LLM scoring — assign fit scores 1-10."""
    try:
        from joborion.scoring.fit_scorer import score_jobs
        score_jobs()
        return {"status": "ok"}
    except Exception as e:
        log.error("Scoring failed: %s", e)
        return {"status": f"error: {e}"}


def _run_tailoring_stage(min_score: int = 7, validation_mode: str = "normal") -> dict:
    """Stage: Resume tailoring — generate tailored resumes for high-fit jobs."""
    try:
        from joborion.scoring.resume_tailor import tailor_resumes
        tailor_resumes(min_score=min_score, validation_mode=validation_mode)
        return {"status": "ok"}
    except Exception as e:
        log.error("Tailoring failed: %s", e)
        return {"status": f"error: {e}"}


def _run_cover_letter_stage(min_score: int = 7, validation_mode: str = "normal") -> dict:
    """Stage: Cover letter generation."""
    try:
        from joborion.scoring.cover_writer import write_cover_letters
        write_cover_letters(min_score=min_score, validation_mode=validation_mode)
        return {"status": "ok"}
    except Exception as e:
        log.error("Cover letter generation failed: %s", e)
        return {"status": f"error: {e}"}


def _run_pdf_conversion_stage() -> dict:
    """Stage: PDF conversion — convert tailored resumes and cover letters to PDF."""
    try:
        from joborion.scoring.document_converter import convert_all_to_pdf
        convert_all_to_pdf()
        return {"status": "ok"}
    except Exception as e:
        log.error("PDF conversion failed: %s", e)
        return {"status": f"error: {e}"}


# Map stage names to their runner functions
STAGE_RUNNERS: dict[str, callable] = {
    "search":   _run_discovery_stage,
    "details":  _run_enrichment_stage,
    "evaluate": _run_scoring_stage,
    "tailor":   _run_tailoring_stage,
    "letter":   _run_cover_letter_stage,
    "export":   _run_pdf_conversion_stage,
}


# ---------------------------------------------------------------------------
# Stage resolution
# ---------------------------------------------------------------------------

def _resolve_stages(stage_names: list[str]) -> list[str]:
    """Resolve 'all' and validate/order stage names."""
    if "all" in stage_names:
        return list(STAGE_ORDER)

    resolved = []
    for name in stage_names:
        if name not in STAGE_META:
            console.print(
                f"[red]Unknown stage:[/red] '{name}'. "
                f"Available: {', '.join(STAGE_ORDER)}, all"
            )
            raise SystemExit(1)
        if name not in resolved:
            resolved.append(name)

    # Maintain canonical order
    return [s for s in STAGE_ORDER if s in resolved]


# ---------------------------------------------------------------------------
# Streaming pipeline helpers
# ---------------------------------------------------------------------------

class _ConcurrentStageTracker:
    """Thread-safe tracker for which stages have finished producing work."""

    def __init__(self):
        self._events: dict[str, threading.Event] = {
            stage: threading.Event() for stage in STAGE_ORDER
        }
        self._results: dict[str, dict] = {}
        self._lock = threading.Lock()

    def mark_done(self, stage: str, result: dict | None = None) -> None:
        with self._lock:
            self._results[stage] = result or {"status": "ok"}
        self._events[stage].set()

    def is_done(self, stage: str) -> bool:
        return self._events[stage].is_set()

    def wait(self, stage: str, timeout: float | None = None) -> bool:
        return self._events[stage].wait(timeout=timeout)

    def get_results(self) -> dict[str, dict]:
        with self._lock:
            return dict(self._results)


# SQL to count pending work for each stage
_PENDING_SQL: dict[str, str] = {
    "details": "SELECT COUNT(*) FROM jobs WHERE detail_scraped_at IS NULL",
    "evaluate": "SELECT COUNT(*) FROM jobs WHERE full_description IS NOT NULL AND fit_score IS NULL",
    "tailor": (
        "SELECT COUNT(*) FROM jobs WHERE fit_score >= ? "
        "AND full_description IS NOT NULL "
        "AND tailored_resume_path IS NULL "
        "AND COALESCE(tailor_attempts, 0) < 5"
    ),
    "letter": (
        "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL "
        "AND (cover_letter_path IS NULL OR cover_letter_path = '') "
        "AND COALESCE(cover_attempts, 0) < 5"
    ),
    "export": (
        "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL "
        "AND tailored_resume_path LIKE '%.txt'"
    ),
}

# How long to sleep between polling loops in streaming mode (seconds)
_STREAM_POLL_INTERVAL = 10


def _count_pending(stage: str, min_score: int = 7) -> int:
    """Count pending work items for a stage."""
    sql = _PENDING_SQL.get(stage)
    if sql is None:
        return 0
    conn = get_connection()
    if "?" in sql:
        return conn.execute(sql, (min_score,)).fetchone()[0]
    return conn.execute(sql).fetchone()[0]


def _run_stage_streaming(
    stage: str,
    tracker: _ConcurrentStageTracker,
    stop_event: threading.Event,
    min_score: int = 7,
    workers: int = 1,
    validation_mode: str = "normal",
) -> None:
    """Run a single stage in streaming mode: loop until upstream done + no work.

    For search: runs once, then marks done.
    For all others: polls DB for pending work, runs the batch processor,
    and repeats until upstream is done and no pending work remains.
    """
    runner = STAGE_RUNNERS[stage]
    kwargs: dict = {}
    if stage in ("tailor", "letter"):
        kwargs["min_score"] = min_score
        kwargs["validation_mode"] = validation_mode
    if stage in ("search", "details"):
        kwargs["workers"] = workers

    upstream = UPSTREAM_DEPS[stage]

    if stage == "search":
        # Discover runs once (its sub-scrapers already do their full crawl)
        try:
            result = runner(**kwargs)
            tracker.mark_done(stage, result)
        except Exception as e:
            log.exception("Stage '%s' crashed", stage)
            tracker.mark_done(stage, {"status": f"error: {e}"})
        return

    # For downstream stages: loop until upstream done + no pending work
    passes = 0
    while not stop_event.is_set():
        # Wait for upstream to start producing work (first pass only)
        if passes == 0 and upstream and not tracker.is_done(upstream):
            # Wait a bit for upstream to produce some work before first run
            tracker.wait(upstream, timeout=_STREAM_POLL_INTERVAL)

        pending = _count_pending(stage, min_score)

        if pending > 0:
            try:
                runner(**kwargs)
                passes += 1
            except Exception as e:
                log.error("Stage '%s' error (pass %d): %s", stage, passes, e)
                passes += 1
        else:
            # No work right now
            upstream_done = upstream is None or tracker.is_done(upstream)
            if upstream_done:
                # No work and upstream is done — this stage is finished
                break
            # Upstream still running, wait and retry
            if stop_event.wait(timeout=_STREAM_POLL_INTERVAL):
                break  # Stop requested

    tracker.mark_done(stage, {"status": "ok", "passes": passes})


# ---------------------------------------------------------------------------
# Pipeline orchestrators
# ---------------------------------------------------------------------------

def _run_sequential(ordered: list[str], min_score: int, workers: int = 1,
                    validation_mode: str = "normal") -> dict:
    """Execute stages one at a time (original behavior)."""
    results: list[dict] = []
    errors: dict[str, str] = {}
    pipeline_start = time.time()

    for name in ordered:
        meta = STAGE_META[name]
        console.print(f"\n{'=' * 70}")
        console.print(f"  [bold]STAGE: {name}[/bold] — {meta['desc']}")
        console.print(f"  Started: {datetime.now().strftime('%H:%M:%S')}")
        console.print(f"{'=' * 70}")

        t0 = time.time()
        runner = STAGE_RUNNERS[name]

        try:
            kwargs: dict = {}
            if name in ("tailor", "letter"):
                kwargs["min_score"] = min_score
                kwargs["validation_mode"] = validation_mode
            if name in ("search", "details"):
                kwargs["workers"] = workers
            result = runner(**kwargs)
            elapsed = time.time() - t0

            status = "ok"
            if isinstance(result, dict):
                status = result.get("status", "ok")
                if name == "search":
                    sub_errors = [
                        f"{k}: {v}" for k, v in result.items()
                        if isinstance(v, str) and v.startswith("error")
                    ]
                    if sub_errors:
                        status = "partial"

        except Exception as e:
            elapsed = time.time() - t0
            status = f"error: {e}"
            log.exception("Stage '%s' crashed", name)
            console.print(f"\n  [red]STAGE FAILED:[/red] {e}")

        results.append({"stage": name, "status": status, "elapsed": elapsed})
        if status not in ("ok", "partial"):
            errors[name] = status

        console.print(f"\n  Stage '{name}' completed in {elapsed:.1f}s — {status}")

    total_elapsed = time.time() - pipeline_start
    return {"stages": results, "errors": errors, "elapsed": total_elapsed}


def _run_streaming(ordered: list[str], min_score: int, workers: int = 1,
                   validation_mode: str = "normal") -> dict:
    """Execute stages concurrently with DB as conveyor belt."""
    tracker = _ConcurrentStageTracker()
    stop_event = threading.Event()
    pipeline_start = time.time()

    console.print("\n  [bold cyan]STREAMING MODE[/bold cyan] — stages run concurrently")
    console.print(f"  Poll interval: {_STREAM_POLL_INTERVAL}s\n")

    # Mark stages NOT in `ordered` as done so downstream doesn't wait for them
    for stage in STAGE_ORDER:
        if stage not in ordered:
            tracker.mark_done(stage, {"status": "skipped"})

    # Launch each stage in its own thread
    threads: dict[str, threading.Thread] = {}
    start_times: dict[str, float] = {}

    for name in ordered:
        start_times[name] = time.time()
        t = threading.Thread(
            target=_run_stage_streaming,
            args=(name, tracker, stop_event, min_score, workers, validation_mode),
            name=f"stage-{name}",
            daemon=True,
        )
        threads[name] = t
        t.start()
        console.print(f"  [dim]Started thread:[/dim] {name}")

    # Wait for all threads to finish
    try:
        for name in ordered:
            threads[name].join()
            elapsed = time.time() - start_times[name]
            console.print(
                f"  [green]Completed:[/green] {name} ({elapsed:.1f}s)"
            )
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted — stopping stages...[/yellow]")
        stop_event.set()
        for t in threads.values():
            t.join(timeout=10)

    total_elapsed = time.time() - pipeline_start

    # Build results from tracker
    all_results = tracker.get_results()
    results: list[dict] = []
    errors: dict[str, str] = {}

    for name in ordered:
        r = all_results.get(name, {"status": "unknown"})
        elapsed = time.time() - start_times.get(name, pipeline_start)
        status = r.get("status", "ok")

        results.append({"stage": name, "status": status, "elapsed": elapsed})
        if status not in ("ok", "partial", "skipped"):
            errors[name] = status

    return {"stages": results, "errors": errors, "elapsed": total_elapsed}


def run_pipeline(
    stages: list[str] | None = None,
    min_score: int = 7,
    dry_run: bool = False,
    stream: bool = False,
    workers: int = 1,
    validation_mode: str = "normal",
) -> dict:
    """Run pipeline stages.

    Args:
        stages: List of stage names, or None / ["all"] for full pipeline.
        min_score: Minimum fit score for tailor/cover stages.
        dry_run: If True, preview stages without executing.
        stream: If True, run stages concurrently (streaming mode).
        workers: Number of parallel threads for discovery/enrichment stages.

    Returns:
        Dict with keys: stages (list of result dicts), errors (dict), elapsed (float).
    """
    # Bootstrap
    load_env()
    ensure_dirs()
    init_db()

    # Resolve stages
    if stages is None:
        stages = ["all"]
    ordered = _resolve_stages(stages)

    # Banner
    mode = "streaming" if stream else "sequential"
    console.print()
    console.print(Panel.fit(
        f"[bold]JobOrion Pipeline[/bold] ({mode})",
        border_style="blue",
    ))
    console.print(f"  Min score:  {min_score}")
    console.print(f"  Workers:    {workers}")
    console.print(f"  Validation: {validation_mode}")
    console.print(f"  Stages:     {' -> '.join(ordered)}")

    # Pre-run stats
    pre_stats = get_stats()
    console.print(f"  DB:        {pre_stats['total']} jobs, {pre_stats['pending_detail']} pending enrichment")

    if dry_run:
        console.print(f"\n  [yellow]DRY RUN[/yellow] — would execute ({mode}):")
        for name in ordered:
            meta = STAGE_META[name]
            console.print(f"    {name:<12s}  {meta['desc']}")
        console.print("\n  No changes made.")
        return {"stages": [], "errors": {}, "elapsed": 0.0}

    # Start run log
    run_id = start_run(goal=f"pipeline:{','.join(ordered)}")

    # Execute
    if stream:
        result = _run_streaming(ordered, min_score, workers=workers,
                                validation_mode=validation_mode)
    else:
        result = _run_sequential(ordered, min_score, workers=workers,
                                 validation_mode=validation_mode)

    # Finish run log
    final_stats = get_stats()
    finish_run(run_id, stats={
        "stages_run": ",".join(ordered),
        "jobs_discovered": final_stats.get("total", 0),
        "jobs_enriched": final_stats.get("with_description", 0),
        "jobs_scored": final_stats.get("scored", 0),
        "jobs_tailored": final_stats.get("tailored", 0),
        "jobs_covered": final_stats.get("with_cover_letter", 0),
        "jobs_applied": final_stats.get("applied", 0),
        "total_cost": get_client().cost_usd,
        "total_duration_ms": int(result.get("elapsed", 0) * 1000),
        "status": "completed" if not result.get("errors") else "partial",
        "errors": str(result.get("errors")) if result.get("errors") else None,
    })

    # Summary table
    console.print(f"\n{'=' * 70}")
    summary = Table(title="Pipeline Summary", show_header=True, header_style="bold")
    summary.add_column("Stage", style="bold")
    summary.add_column("Status")
    summary.add_column("Time", justify="right")

    for r in result["stages"]:
        elapsed_str = f"{r['elapsed']:.1f}s"
        status_display = r["status"][:30]
        if r["status"] == "ok":
            style = "green"
        elif r["status"] in ("partial", "skipped"):
            style = "yellow"
        else:
            style = "red"
        summary.add_row(r["stage"], f"[{style}]{status_display}[/{style}]", elapsed_str)

    summary.add_row("", "", "")
    summary.add_row("[bold]Total[/bold]", "", f"[bold]{result['elapsed']:.1f}s[/bold]")
    console.print(summary)

    # Final DB stats
    final = get_stats()
    console.print("\n  [bold]DB Final State:[/bold]")
    console.print(f"    Total jobs:     {final['total']}")
    console.print(f"    With desc:      {final['with_description']}")
    console.print(f"    Scored:         {final['scored']}")
    console.print(f"    Tailored:       {final['tailored']}")
    console.print(f"    Cover letters:  {final['with_cover_letter']}")
    console.print(f"    Ready to apply: {final['ready_to_apply']}")
    console.print(f"    Applied:        {final['applied']}")
    console.print(f"{'=' * 70}\n")

    # Record run history for future reference
    _record_run_history(ordered, pre_stats, final, result)

    return result


def _record_run_history(
    stages_run: list[str],
    pre_stats: dict,
    post_stats: dict,
    result: dict,
) -> None:
    """Record run history for future reference and learning.

    Args:
        stages_run: List of stages that were executed.
        pre_stats: Database stats before pipeline run.
        post_stats: Database stats after pipeline run.
        result: Pipeline execution result.
    """
    try:
        conn = get_connection()
        client = get_client()

        # Calculate delta stats
        jobs_enriched = post_stats.get("with_description", 0) - pre_stats.get("with_description", 0)
        jobs_scored = post_stats.get("scored", 0) - pre_stats.get("scored", 0)
        jobs_tailored = post_stats.get("tailored", 0) - pre_stats.get("tailored", 0)
        jobs_covered = post_stats.get("with_cover_letter", 0) - pre_stats.get("with_cover_letter", 0)

        # Get error summary
        errors = result.get("errors", {})
        errors_json = str(errors) if errors else None

        conn.execute(
            """INSERT INTO run_history
                (run_started_at, run_completed_at, stages_run, total_jobs,
                 jobs_enriched, jobs_scored, jobs_tailored, jobs_covered,
                 llm_calls, errors, elapsed_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().isoformat(),
                datetime.now().isoformat(),
                ",".join(stages_run),
                post_stats.get("total", 0),
                max(0, jobs_enriched),
                max(0, jobs_scored),
                max(0, jobs_tailored),
                max(0, jobs_covered),
                client._call_count,
                errors_json,
                result.get("elapsed", 0.0),
            ),
        )
        conn.commit()

        # Reset LLM budget for next run
        client.reset_budget()

    except Exception as e:
        log.warning("Failed to record run history: %s", e)
