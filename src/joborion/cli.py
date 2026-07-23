"""JobOrion CLI — the main entry point."""

from __future__ import annotations

import logging
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from joborion import __version__

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)

app = typer.Typer(
    name="joborion",
    help="AI-powered end-to-end job application pipeline.",
    no_args_is_help=True,
)
console = Console()
log = logging.getLogger(__name__)

# Valid pipeline stages (in execution order)
VALID_STAGES = ("search", "details", "evaluate", "tailor", "letter", "export")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bootstrap() -> None:
    """Common setup: load env, create dirs, init DB."""
    from joborion.config import load_env, ensure_dirs
    from joborion.database import init_db

    load_env()
    ensure_dirs()
    init_db()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"[bold]joborion[/bold] {__version__}")
        raise typer.Exit()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", "-V",
        help="Show version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """JobOrion — AI-powered end-to-end job application pipeline."""


@app.command()
def init() -> None:
    """Run the first-time setup wizard (profile, resume, search config)."""
    from joborion.wizard.init import run_wizard

    run_wizard()


@app.command()
def plan(
    goal: str = typer.Argument(..., help="Your goal in plain language (e.g., 'Find 10 remote Python jobs')"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show plan without executing."),
    max_cost: float = typer.Option(5.0, "--max-cost", help="Maximum budget in USD."),
) -> None:
    """Plan job search pipeline from a natural language goal."""
    from joborion.agent.orchestrator import Orchestrator

    orch = Orchestrator(goal=goal, max_cost=max_cost)

    if dry_run:
        plan_result = orch.plan()
        console.print("\n[bold]Execution Plan[/bold]\n")
        console.print(f"Goal: {goal}\n")
        console.print(f"Estimated cost: ${plan_result.total_cost:.4f}")
        console.print(f"Estimated duration: {plan_result.total_duration_ms / 1000:.1f}s\n")
        for i, step in enumerate(plan_result.steps, 1):
            console.print(f"  {i}. {step.tool}: {step.description}")
        console.print()
    else:
        result = orch.execute()
        console.print("\n[bold]Pipeline completed![/bold]")
        console.print(f"Status: {result['status']}")
        console.print(f"Cost: ${result['total_cost']:.4f}")
        if result["errors"]:
            console.print(f"[red]Errors: {len(result['errors'])}[/red]")
        console.print()


@app.command()
def reflect(
    run_id: Optional[str] = typer.Option(None, "--run-id", help="Analyze a specific run."),
    last: int = typer.Option(1, "--last", help="Analyze the last N runs."),
) -> None:
    """Analyze pipeline runs and generate insights."""
    from joborion.agent.reflector import Reflector
    from joborion.database import (
        store_reflection, get_recent_runs, get_connection,
    )

    _bootstrap()
    conn = get_connection()
    reflector = Reflector(conn)

    if run_id:
        # Analyze specific run
        result = reflector.analyze_run(run_id)
        ref_id = store_reflection(result)
        _print_reflection(result, ref_id)
    else:
        # Analyze last N runs
        runs = get_recent_runs(n=last)
        if not runs:
            console.print("[yellow]No runs found to analyze.[/yellow]")
            return

        for run in runs:
            rid = run.get("run_id", "")
            result = reflector.analyze_run(rid)
            ref_id = store_reflection(result)
            _print_reflection(result, ref_id)
            console.print()


def _print_reflection(result: dict, ref_id: str) -> None:
    """Print a reflection record in a formatted table."""
    from rich.panel import Panel

    rating = result["overall_rating"]
    color = {"good": "green", "ok": "yellow", "poor": "red"}.get(rating, "white")

    console.print()
    console.print(Panel.fit(
        f"[bold]Reflection[/bold] ({ref_id})\n"
        f"Run: {result.get('run_id', '?')}",
        border_style=color,
    ))

    # Rating
    console.print(f"  Rating: [{color}]{rating.upper()}[/{color}]")

    # What went well
    if result.get("what_went_well"):
        console.print("\n  [bold green]What went well:[/bold green]")
        for item in result["what_went_well"]:
            console.print(f"    + {item}")

    # What failed
    if result.get("what_failed"):
        console.print("\n  [bold red]What failed:[/bold red]")
        for item in result["what_failed"]:
            console.print(f"    - {item}")

    # Recommendations
    if result.get("recommendations"):
        console.print("\n  [bold cyan]Recommendations:[/bold cyan]")
        for i, rec in enumerate(result["recommendations"], 1):
            console.print(f"    {i}. {rec}")

    # Score calibration
    cal = result.get("scoring_calibration", {})
    if cal.get("avg_score"):
        console.print("\n  [bold]Score calibration:[/bold]")
        console.print(f"    Avg: {cal['avg_score']}, Range: {cal.get('score_range', '?')}")
        console.print(f"    {cal.get('assessment', '')}")

    # Cost
    cost = result.get("cost_analysis", {})
    if cost.get("total", 0) > 0:
        console.print(f"\n  [bold]Cost:[/bold] ${cost['total']:.4f}")


@app.command()
def run(
    stages: Optional[list[str]] = typer.Argument(
        None,
        help=(
            "Pipeline stages to run. "
            f"Valid: {', '.join(VALID_STAGES)}, all. "
            "Defaults to 'all' if omitted."
        ),
    ),
    goal: Optional[str] = typer.Option(None, "--goal", "-g", help="Natural language goal (overrides stages)."),
    min_score: int = typer.Option(7, "--min-score", help="Minimum fit score for tailor/letter stages."),
    workers: int = typer.Option(1, "--workers", "-w", help="Parallel threads for search/details stages."),
    stream: bool = typer.Option(False, "--stream", help="Run stages concurrently (streaming mode)."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview stages without executing."),
    validation: str = typer.Option(
        "normal",
        "--validation",
        help=(
            "Validation strictness for tailor/letter stages. "
            "strict: banned words = errors, judge must pass. "
            "normal: banned words = warnings only (default, recommended for Gemini free tier). "
            "lenient: banned words ignored, LLM judge skipped (fastest, fewest API calls)."
        ),
    ),
) -> None:
    """Run pipeline stages: search, details, evaluate, tailor, letter, export."""
    _bootstrap()

    # If --goal is provided, use orchestrator
    if goal:
        from joborion.agent.orchestrator import Orchestrator

        orch = Orchestrator(goal=goal, max_cost=5.0)
        result = orch.execute(dry_run=dry_run)

        if dry_run:
            console.print("\n[bold]Execution Plan[/bold]\n")
            console.print(f"Goal: {goal}\n")
            for i, desc in enumerate(result["plan"], 1):
                console.print(f"  {i}. {desc}")
            console.print()
        else:
            console.print("\n[bold]Pipeline completed![/bold]")
            console.print(f"Status: {result['status']}")
            console.print(f"Cost: ${result['total_cost']:.4f}")
            if result["errors"]:
                console.print(f"[red]Errors: {len(result['errors'])}[/red]")
            console.print()
    else:
        # Legacy mode: explicit stages
        from joborion.pipeline import run_pipeline

        stage_list = stages if stages else ["all"]

        # Validate stage names
        for s in stage_list:
            if s != "all" and s not in VALID_STAGES:
                console.print(
                    f"[red]Unknown stage:[/red] '{s}'. "
                    f"Valid stages: {', '.join(VALID_STAGES)}, all"
                )
                raise typer.Exit(code=1)

        # Gate AI stages behind Tier 2
        llm_stages = {"evaluate", "tailor", "letter"}
        if any(s in stage_list for s in llm_stages) or "all" in stage_list:
            from joborion.config import check_tier
            check_tier(2, "AI scoring/tailoring")

        # Validate the --validation flag value
        valid_modes = ("strict", "normal", "lenient")
        if validation not in valid_modes:
            console.print(
                f"[red]Invalid --validation value:[/red] '{validation}'. "
                f"Choose from: {', '.join(valid_modes)}"
            )
            raise typer.Exit(code=1)

        result = run_pipeline(
            stages=stage_list,
            min_score=min_score,
            dry_run=dry_run,
            stream=stream,
            workers=workers,
            validation_mode=validation,
        )

        if result.get("errors"):
            raise typer.Exit(code=1)


@app.command()
def apply(
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Max applications to submit."),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of parallel browser workers."),
    min_score: int = typer.Option(7, "--min-score", help="Minimum fit score for job selection."),
    model: str = typer.Option("haiku", "--model", "-m", help="Claude model name."),
    continuous: bool = typer.Option(False, "--continuous", "-c", help="Run forever, polling for new jobs."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview actions without submitting."),
    headless: bool = typer.Option(False, "--headless", help="Run browsers in headless mode."),
    url: Optional[str] = typer.Option(None, "--url", help="Apply to a specific job URL."),
    gen: bool = typer.Option(False, "--gen", help="Generate prompt file for manual debugging instead of running."),
    mark_applied: Optional[str] = typer.Option(None, "--mark-applied", help="Manually mark a job URL as applied."),
    mark_failed: Optional[str] = typer.Option(None, "--mark-failed", help="Manually mark a job URL as failed (provide URL)."),
    fail_reason: Optional[str] = typer.Option(None, "--fail-reason", help="Reason for --mark-failed."),
    reset_failed: bool = typer.Option(False, "--reset-failed", help="Reset all failed jobs for retry."),
) -> None:
    """Launch auto-apply to submit job applications."""
    _bootstrap()

    from joborion.config import check_tier, PROFILE_PATH as _profile_path
    from joborion.database import get_connection

    # --- Utility modes (no Chrome/Claude needed) ---

    if mark_applied:
        from joborion.apply.runner import mark_job
        mark_job(mark_applied, "applied")
        console.print(f"[green]Marked as applied:[/green] {mark_applied}")
        return

    if mark_failed:
        from joborion.apply.runner import mark_job
        mark_job(mark_failed, "failed", reason=fail_reason)
        console.print(f"[yellow]Marked as failed:[/yellow] {mark_failed} ({fail_reason or 'manual'})")
        return

    if reset_failed:
        from joborion.apply.runner import reset_failed as do_reset
        count = do_reset()
        console.print(f"[green]Reset {count} failed job(s) for retry.[/green]")
        return

    # --- Full apply mode ---

    # Check 1: Tier 3 required (Claude Code CLI + Chrome)
    check_tier(3, "auto-apply")

    # Check 2: Profile exists
    if not _profile_path.exists():
        console.print(
            "[red]Profile not found.[/red]\n"
            "Run [bold]joborion init[/bold] to create your profile first."
        )
        raise typer.Exit(code=1)

    # Check 3: Tailored resumes exist (skip for --gen with --url)
    if not (gen and url):
        conn = get_connection()
        ready = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL AND applied_at IS NULL"
        ).fetchone()[0]
        if ready == 0:
            console.print(
                "[red]No tailored resumes ready.[/red]\n"
                "Run [bold]joborion run evaluate tailor[/bold] first to prepare applications."
            )
            raise typer.Exit(code=1)

    if gen:
        from joborion.apply.runner import gen_prompt
        target = url or ""
        if not target:
            console.print("[red]--gen requires --url to specify which job.[/red]")
            raise typer.Exit(code=1)
        prompt_file = gen_prompt(target, min_score=min_score, model=model)
        if not prompt_file:
            console.print("[red]No matching job found for that URL.[/red]")
            raise typer.Exit(code=1)
        mcp_path = _profile_path.parent / ".mcp-apply-0.json"
        console.print(f"[green]Wrote prompt to:[/green] {prompt_file}")
        console.print("\n[bold]Run manually:[/bold]")
        console.print(
            f"  claude --model {model} -p "
            f"--mcp-config {mcp_path} "
            f"--permission-mode bypassPermissions < {prompt_file}"
        )
        return

    from joborion.apply.runner import main as apply_main

    effective_limit = limit if limit is not None else (0 if continuous else 1)

    console.print("\n[bold blue]Launching Auto-Apply[/bold blue]")
    console.print(f"  Limit:    {'unlimited' if continuous else effective_limit}")
    console.print(f"  Workers:  {workers}")
    console.print(f"  Model:    {model}")
    console.print(f"  Headless: {headless}")
    console.print(f"  Dry run:  {dry_run}")
    if url:
        console.print(f"  Target:   {url}")
    console.print()

    apply_main(
        limit=effective_limit,
        target_url=url,
        min_score=min_score,
        headless=headless,
        model=model,
        dry_run=dry_run,
        continuous=continuous,
        workers=workers,
    )


@app.command()
def status() -> None:
    """Show pipeline statistics from the database."""
    _bootstrap()

    from joborion.database import get_stats

    stats = get_stats()

    console.print("\n[bold]JobOrion Pipeline Status[/bold]\n")

    # Summary table
    summary = Table(title="Pipeline Overview", show_header=True, header_style="bold cyan")
    summary.add_column("Metric", style="bold")
    summary.add_column("Count", justify="right")

    summary.add_row("Total jobs discovered", str(stats["total"]))
    summary.add_row("With full description", str(stats["with_description"]))
    summary.add_row("Pending enrichment", str(stats["pending_detail"]))
    summary.add_row("Enrichment errors", str(stats["detail_errors"]))
    summary.add_row("Scored by LLM", str(stats["scored"]))
    summary.add_row("Pending scoring", str(stats["unscored"]))
    summary.add_row("Tailored resumes", str(stats["tailored"]))
    summary.add_row("Pending tailoring (7+)", str(stats["untailored_eligible"]))
    summary.add_row("Cover letters", str(stats["with_cover_letter"]))
    summary.add_row("Ready to apply", str(stats["ready_to_apply"]))
    summary.add_row("Applied", str(stats["applied"]))
    summary.add_row("Apply errors", str(stats["apply_errors"]))

    console.print(summary)

    # Score distribution
    if stats["score_distribution"]:
        dist_table = Table(title="\nScore Distribution", show_header=True, header_style="bold yellow")
        dist_table.add_column("Score", justify="center")
        dist_table.add_column("Count", justify="right")
        dist_table.add_column("Bar")

        max_count = max(count for _, count in stats["score_distribution"]) or 1
        for score, count in stats["score_distribution"]:
            bar_len = int(count / max_count * 30)
            if score >= 7:
                color = "green"
            elif score >= 5:
                color = "yellow"
            else:
                color = "red"
            bar = f"[{color}]{'=' * bar_len}[/{color}]"
            dist_table.add_row(str(score), str(count), bar)

        console.print(dist_table)

    # By site
    if stats["by_site"]:
        site_table = Table(title="\nJobs by Source", show_header=True, header_style="bold magenta")
        site_table.add_column("Site")
        site_table.add_column("Count", justify="right")

        for site, count in stats["by_site"]:
            site_table.add_row(site or "Unknown", str(count))

        console.print(site_table)

    console.print()


@app.command()
def dashboard() -> None:
    """Generate and open the HTML dashboard in your browser."""
    _bootstrap()

    from joborion.dashboard import open_dashboard

    open_dashboard()


@app.command()
def doctor() -> None:
    """Check your setup and diagnose missing requirements."""
    import shutil
    from joborion.config import (
        load_env, PROFILE_PATH, RESUME_PATH, RESUME_PDF_PATH,
        SEARCH_CONFIG_PATH, get_chrome_path,
    )

    load_env()

    ok_mark = "[green]OK[/green]"
    fail_mark = "[red]MISSING[/red]"
    warn_mark = "[yellow]WARN[/yellow]"

    results: list[tuple[str, str, str]] = []  # (check, status, note)

    # --- Tier 1 checks ---
    # Profile
    if PROFILE_PATH.exists():
        results.append(("profile.json", ok_mark, str(PROFILE_PATH)))
    else:
        results.append(("profile.json", fail_mark, "Run 'joborion init' to create"))

    # Resume
    if RESUME_PATH.exists():
        results.append(("resume.txt", ok_mark, str(RESUME_PATH)))
    elif RESUME_PDF_PATH.exists():
        results.append(("resume.txt", warn_mark, "Only PDF found — plain-text needed for AI stages"))
    else:
        results.append(("resume.txt", fail_mark, "Run 'joborion init' to add your resume"))

    # Search config
    if SEARCH_CONFIG_PATH.exists():
        results.append(("searches.yaml", ok_mark, str(SEARCH_CONFIG_PATH)))
    else:
        results.append(("searches.yaml", warn_mark, "Will use example config — run 'joborion init'"))

    # jobspy (discovery dep installed separately)
    try:
        import jobspy  # noqa: F401
        results.append(("python-jobspy", ok_mark, "Job board scraping available"))
    except ImportError:
        results.append(("python-jobspy", warn_mark,
                        "pip install --no-deps python-jobspy && pip install pydantic tls-client requests markdownify regex"))

    # --- Tier 2 checks ---
    import os
    has_gemini = bool(os.environ.get("GEMINI_API_KEY"))
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))
    has_local = bool(os.environ.get("LLM_URL"))
    if has_gemini:
        model = os.environ.get("LLM_MODEL", "gemini-2.0-flash")
        results.append(("LLM API key", ok_mark, f"Gemini ({model})"))
    elif has_openai:
        model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
        results.append(("LLM API key", ok_mark, f"OpenAI ({model})"))
    elif has_local:
        results.append(("LLM API key", ok_mark, f"Local: {os.environ.get('LLM_URL')}"))
    else:
        results.append(("LLM API key", fail_mark,
                        "Set GEMINI_API_KEY in ~/.joborion/.env (run 'joborion init')"))

    # --- Tier 3 checks ---
    # Claude Code CLI
    claude_bin = shutil.which("claude")
    if claude_bin:
        results.append(("Claude Code CLI", ok_mark, claude_bin))
    else:
        results.append(("Claude Code CLI", fail_mark,
                        "Install from https://claude.ai/code (needed for auto-apply)"))

    # Chrome
    try:
        chrome_path = get_chrome_path()
        results.append(("Chrome/Chromium", ok_mark, chrome_path))
    except FileNotFoundError:
        results.append(("Chrome/Chromium", fail_mark,
                        "Install Chrome or set CHROME_PATH env var (needed for auto-apply)"))

    # Node.js / npx (for Playwright MCP)
    npx_bin = shutil.which("npx")
    if npx_bin:
        results.append(("Node.js (npx)", ok_mark, npx_bin))
    else:
        results.append(("Node.js (npx)", fail_mark,
                        "Install Node.js 18+ from nodejs.org (needed for auto-apply)"))

    # CapSolver (optional)
    capsolver = os.environ.get("CAPSOLVER_API_KEY")
    if capsolver:
        results.append(("CapSolver API key", ok_mark, "CAPTCHA solving enabled"))
    else:
        results.append(("CapSolver API key", "[dim]optional[/dim]",
                        "Set CAPSOLVER_API_KEY in .env for CAPTCHA solving"))

    # --- Render results ---
    console.print()
    console.print("[bold]JobOrion Doctor[/bold]\n")

    col_w = max(len(r[0]) for r in results) + 2
    for check, status, note in results:
        pad = " " * (col_w - len(check))
        console.print(f"  {check}{pad}{status}  [dim]{note}[/dim]")

    console.print()

    # Tier summary
    from joborion.config import get_tier, TIER_LABELS
    tier = get_tier()
    console.print(f"[bold]Current tier: Tier {tier} — {TIER_LABELS[tier]}[/bold]")

    if tier == 1:
        console.print("[dim]  → Tier 2 unlocks: scoring, tailoring, cover letters (needs LLM API key)[/dim]")
        console.print("[dim]  → Tier 3 unlocks: auto-apply (needs Claude Code CLI + Chrome + Node.js)[/dim]")
    elif tier == 2:
        console.print("[dim]  → Tier 3 unlocks: auto-apply (needs Claude Code CLI + Chrome + Node.js)[/dim]")

    console.print()


if __name__ == "__main__":
    app()
