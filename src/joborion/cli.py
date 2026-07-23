"""JobOrion CLI — the main entry point."""

from __future__ import annotations

import logging
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table
from rich import box

from joborion.ui import (
    console, print_banner, print_success, print_warning, make_stats_table, make_plan_table, print_completed,
    print_reflection_card,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)

app = typer.Typer(
    name="joborion",
    help="[bold bright cyan]AI-powered end-to-end job application pipeline[/bold bright cyan]",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

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
        print_banner()
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
    """[bold bright cyan]JobOrion[/bold bright cyan] — AI-powered job application pipeline."""


@app.command()
def init() -> None:
    """Run the first-time setup wizard (profile, resume, search config)."""
    from joborion.wizard.init import run_wizard

    run_wizard()


@app.command()
def plan(
    goal: str = typer.Argument(..., help="Your goal in plain language"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show plan without executing."),
    max_cost: float = typer.Option(5.0, "--max-cost", help="Maximum budget in USD."),
) -> None:
    """Plan job search pipeline from a natural language goal."""
    from joborion.agent.orchestrator import Orchestrator

    orch = Orchestrator(goal=goal, max_cost=max_cost)

    if dry_run:
        plan_result = orch.plan()
        console.print()
        console.print(Panel(
            f"[bold bright cyan]{goal}[/bold cyan]",
            title="[bold]🎯 Goal[/bold]",
            border_style="cyan",
            padding=(0, 1),
        ))

        steps_data = [
            {
                "tool": s.tool,
                "description": s.description,
                "cost_estimate": s.cost_estimate,
            }
            for s in plan_result.steps
        ]
        table = make_plan_table(steps_data)
        console.print(table)

        console.print()
        console.print(f"  [bold]Estimated cost:[/bold] [yellow]${plan_result.total_cost:.4f}[/yellow]")
        console.print(f"  [bold]Estimated time:[/bold] [cyan]{plan_result.total_duration_ms / 1000:.1f}s[/cyan]")
        console.print()
    else:
        result = orch.execute()
        print_completed(
            "Pipeline completed!",
            cost=result["total_cost"],
            errors=len(result.get("errors", [])),
        )


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
        result = reflector.analyze_run(run_id)
        ref_id = store_reflection(result, conn=conn)
        print_reflection_card(result, ref_id)
    else:
        runs = get_recent_runs(n=last)
        if not runs:
            console.print(Panel(
                "[yellow]No runs found to analyze.[/yellow]",
                border_style="yellow",
            ))
            return

        for run in runs:
            rid = run.get("run_id", "")
            result = reflector.analyze_run(rid)
            ref_id = store_reflection(result, conn=conn)
            print_reflection_card(result, ref_id)
            console.print()


@app.command()
def run(
    stages: Optional[list[str]] = typer.Argument(
        None,
        help=f"Pipeline stages: {', '.join(VALID_STAGES)}, all",
    ),
    goal: Optional[str] = typer.Option(None, "--goal", "-g", help="Natural language goal."),
    auto: bool = typer.Option(False, "--auto", help="Autonomous mode (full loop)."),
    semi: bool = typer.Option(False, "--semi", help="Semi-autonomous: approve before each application."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip all approval gates."),
    min_score: int = typer.Option(7, "--min-score", help="Minimum fit score."),
    workers: int = typer.Option(1, "--workers", "-w", help="Parallel threads."),
    stream: bool = typer.Option(False, "--stream", help="Concurrent streaming mode."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without executing."),
    validation: str = typer.Option("normal", "--validation", help="Validation strictness."),
) -> None:
    """Run pipeline stages: search, details, evaluate, tailor, letter, export."""
    _bootstrap()

    # If --goal is provided, use orchestrator
    if goal:
        from joborion.agent.orchestrator import Orchestrator

        orch = Orchestrator(goal=goal, max_cost=5.0, auto=auto, yes=yes, semi=semi)

        if auto:
            result = orch.execute_autonomous()
            report = result.get("report", "")
            console.print(Panel(report, border_style="green", padding=(1, 2)))
        else:
            if dry_run:
                plan_result = orch.plan()
                console.print()
                console.print(Panel(
                    f"[bold bright cyan]{goal}[/bold cyan]",
                    title="[bold]🎯 Goal[/bold]",
                    border_style="cyan",
                ))

                steps_data = [
                    {"tool": s.tool, "description": s.description, "cost_estimate": s.cost_estimate}
                    for s in plan_result.steps
                ]
                table = make_plan_table(steps_data)
                console.print(table)
                console.print()
            else:
                result = orch.execute()
                print_completed(
                    "Pipeline completed!",
                    cost=result["total_cost"],
                    errors=len(result.get("errors", [])),
                )
        return

    # Legacy mode: explicit stages
    from joborion.pipeline import run_pipeline

    stage_list = stages if stages else ["all"]

    # Validate stage names
    for s in stage_list:
        if s != "all" and s not in VALID_STAGES:
            console.print(Panel(
                f"[red]Unknown stage:[/red] '{s}'\n"
                f"Valid stages: {', '.join(VALID_STAGES)}, all",
                border_style="red",
            ))
            raise typer.Exit(code=1)

    # Gate AI stages behind Tier 2
    llm_stages = {"evaluate", "tailor", "letter"}
    if any(s in stage_list for s in llm_stages) or "all" in stage_list:
        from joborion.config import check_tier
        check_tier(2, "AI scoring/tailoring")

    # Validate --validation flag
    valid_modes = ("strict", "normal", "lenient")
    if validation not in valid_modes:
        console.print(Panel(
            f"[red]Invalid --validation:[/red] '{validation}'\n"
            f"Choose from: {', '.join(valid_modes)}",
            border_style="red",
        ))
        raise typer.Exit(code=1)

    # Show what we're about to do
    console.print()
    console.print(Panel(
        f"[bold]Running:[/bold] {' → '.join(stage_list)}",
        border_style="cyan",
        padding=(0, 1),
    ))

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
    limit: Optional[int] = typer.Option(None, "--limit", "-l", help="Max applications."),
    workers: int = typer.Option(1, "--workers", "-w", help="Parallel workers."),
    min_score: int = typer.Option(7, "--min-score", help="Minimum fit score."),
    model: str = typer.Option("haiku", "--model", "-m", help="Claude model."),
    continuous: bool = typer.Option(False, "--continuous", "-c", help="Run forever."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without submitting."),
    headless: bool = typer.Option(False, "--headless", help="Run browsers headless."),
    url: Optional[str] = typer.Option(None, "--url", help="Apply to specific URL."),
    gen: bool = typer.Option(False, "--gen", help="Generate prompt file instead of running."),
    mark_applied: Optional[str] = typer.Option(None, "--mark-applied", help="Mark job as applied."),
    mark_failed: Optional[str] = typer.Option(None, "--mark-failed", help="Mark job as failed."),
    fail_reason: Optional[str] = typer.Option(None, "--fail-reason", help="Reason for failure."),
    reset_failed: bool = typer.Option(False, "--reset-failed", help="Reset all failed jobs."),
) -> None:
    """Launch auto-apply to submit job applications."""
    _bootstrap()

    from joborion.config import check_tier, PROFILE_PATH as _profile_path
    from joborion.database import get_connection

    # Utility modes
    if mark_applied:
        from joborion.apply.runner import mark_job
        mark_job(mark_applied, "applied")
        print_success(f"Marked as applied: {mark_applied}")
        return

    if mark_failed:
        from joborion.apply.runner import mark_job
        mark_job(mark_failed, "failed", reason=fail_reason)
        print_warning(f"Marked as failed: {mark_failed} ({fail_reason or 'manual'})")
        return

    if reset_failed:
        from joborion.apply.runner import reset_failed as do_reset
        count = do_reset()
        print_success(f"Reset {count} failed job(s) for retry.")
        return

    # Full apply mode
    check_tier(3, "auto-apply")

    if not _profile_path.exists():
        console.print(Panel(
            "[red]Profile not found.[/red]\n"
            "Run [bold]joborion init[/bold] to create your profile first.",
            border_style="red",
        ))
        raise typer.Exit(code=1)

    if not (gen and url):
        conn = get_connection()
        ready = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL AND applied_at IS NULL"
        ).fetchone()[0]
        if ready == 0:
            console.print(Panel(
                "[red]No tailored resumes ready.[/red]\n"
                "Run [bold]joborion run evaluate tailor[/bold] first.",
                border_style="red",
            ))
            raise typer.Exit(code=1)

    if gen:
        from joborion.apply.runner import gen_prompt
        target = url or ""
        if not target:
            console.print(Panel("[red]--gen requires --url[/red]", border_style="red"))
            raise typer.Exit(code=1)
        prompt_file = gen_prompt(target, min_score=min_score, model=model)
        if not prompt_file:
            console.print(Panel("[red]No matching job found.[/red]", border_style="red"))
            raise typer.Exit(code=1)
        mcp_path = _profile_path.parent / ".mcp-apply-0.json"
        print_success(f"Wrote prompt to: {prompt_file}")
        console.print()
        console.print(Panel(
            f"[bold]Run manually:[/bold]\n"
            f"claude --model {model} -p "
            f"--mcp-config {mcp_path} "
            f"--permission-mode bypassPermissions < {prompt_file}",
            border_style="cyan",
        ))
        return

    from joborion.apply.runner import main as apply_main

    effective_limit = limit if limit is not None else (0 if continuous else 1)

    # Show launch banner
    console.print()
    console.print(Panel(
        f"[bold bright cyan]🚀 Launching Auto-Apply[/bold cyan]\n\n"
        f"  [bold]Limit:[/bold]    {'unlimited' if continuous else effective_limit}\n"
        f"  [bold]Workers:[/bold]  {workers}\n"
        f"  [bold]Model:[/bold]    {model}\n"
        f"  [bold]Headless:[/bold] {headless}\n"
        f"  [bold]Dry run:[/bold]  {dry_run}"
        + (f"\n  [bold]Target:[/bold]   {url}" if url else ""),
        border_style="cyan",
        padding=(1, 2),
    ))

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

    console.print()
    print_banner()

    # Stats table
    stats_table = make_stats_table(stats)
    console.print(stats_table)

    # Score distribution
    if stats["score_distribution"]:
        console.print()
        dist_table = Table(
            title="[bold bright yellow]Score Distribution[/bold bright yellow]",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold yellow",
            border_style="bright yellow",
        )
        dist_table.add_column("Score", justify="center", width=6)
        dist_table.add_column("Count", justify="right", width=6)
        dist_table.add_column("Distribution", width=30)

        max_count = max(count for _, count in stats["score_distribution"]) or 1
        for score, count in stats["score_distribution"]:
            bar_len = int(count / max_count * 25)
            if score >= 7:
                color = "green"
                emoji = "🌟"
            elif score >= 5:
                color = "yellow"
                emoji = "⭐"
            else:
                color = "red"
                emoji = "💔"
            bar = f"[{color}]{'█' * bar_len}{'░' * (25 - bar_len)}[/{color}]"
            dist_table.add_row(f"{emoji} {score}", str(count), bar)

        console.print(dist_table)

    # By site
    if stats["by_site"]:
        console.print()
        site_table = Table(
            title="[bold bright magenta]Jobs by Source[/bold bright magenta]",
            box=box.ROUNDED,
            show_header=True,
            header_style="bold magenta",
            border_style="bright magenta",
        )
        site_table.add_column("Source", width=25)
        site_table.add_column("Count", justify="right", width=8)

        for site, count in stats["by_site"]:
            site_table.add_row(f"🌐 {site or 'Unknown'}", str(count))

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
    import os
    from joborion.config import (
        load_env, PROFILE_PATH, RESUME_PATH, RESUME_PDF_PATH,
        SEARCH_CONFIG_PATH, get_chrome_path,
    )

    load_env()

    console.print()
    print_banner()

    results: list[tuple[str, str, str, str]] = []  # (check, status, emoji, note)

    # Tier 1 checks
    if PROFILE_PATH.exists():
        results.append(("profile.json", "ok", "✅", str(PROFILE_PATH)))
    else:
        results.append(("profile.json", "fail", "❌", "Run 'joborion init'"))

    if RESUME_PATH.exists():
        results.append(("resume.txt", "ok", "✅", str(RESUME_PATH)))
    elif RESUME_PDF_PATH.exists():
        results.append(("resume.txt", "warn", "⚠️", "Only PDF found"))
    else:
        results.append(("resume.txt", "fail", "❌", "Run 'joborion init'"))

    if SEARCH_CONFIG_PATH.exists():
        results.append(("searches.yaml", "ok", "✅", str(SEARCH_CONFIG_PATH)))
    else:
        results.append(("searches.yaml", "warn", "⚠️", "Will use example"))

    import importlib.util
    if importlib.util.find_spec("jobspy"):
        results.append(("python-jobspy", "ok", "✅", "Job board scraping"))
    else:
        results.append(("python-jobspy", "warn", "⚠️", "pip install python-jobspy"))

    # Tier 2 checks
    has_gemini = bool(os.environ.get("GEMINI_API_KEY"))
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))
    has_local = bool(os.environ.get("LLM_URL"))
    if has_gemini:
        model = os.environ.get("LLM_MODEL", "gemini-2.0-flash")
        results.append(("LLM API key", "ok", "✅", f"Gemini ({model})"))
    elif has_openai:
        model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
        results.append(("LLM API key", "ok", "✅", f"OpenAI ({model})"))
    elif has_local:
        results.append(("LLM API key", "ok", "✅", f"Local: {os.environ.get('LLM_URL')}"))
    else:
        results.append(("LLM API key", "fail", "❌", "Set GEMINI_API_KEY"))

    # Tier 3 checks
    claude_bin = shutil.which("claude")
    if claude_bin:
        results.append(("Claude Code CLI", "ok", "✅", claude_bin))
    else:
        results.append(("Claude Code CLI", "fail", "❌", "Install from claude.ai/code"))

    try:
        chrome_path = get_chrome_path()
        results.append(("Chrome/Chromium", "ok", "✅", chrome_path))
    except FileNotFoundError:
        results.append(("Chrome/Chromium", "fail", "❌", "Install Chrome"))

    npx_bin = shutil.which("npx")
    if npx_bin:
        results.append(("Node.js (npx)", "ok", "✅", npx_bin))
    else:
        results.append(("Node.js (npx)", "fail", "❌", "Install Node.js 18+"))

    capsolver = os.environ.get("CAPSOLVER_API_KEY")
    if capsolver:
        results.append(("CapSolver API key", "ok", "✅", "CAPTCHA solving enabled"))
    else:
        results.append(("CapSolver API key", "warn", "💡", "Optional: CAPTCHA solving"))

    # Render results
    table = Table(
        title="[bold bright cyan]System Health[/bold bright cyan]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        border_style="bright cyan",
    )
    table.add_column("Component", style="bold", width=20)
    table.add_column("Status", justify="center", width=8)
    table.add_column("Details", width=35)

    for check, status, emoji, note in results:
        status_color = "green" if status == "ok" else "yellow" if status == "warn" else "red"
        table.add_row(check, f"[{status_color}]{emoji}[/{status_color}]", f"[dim]{note}[/dim]")

    console.print(table)

    # Tier summary
    from joborion.config import get_tier, TIER_LABELS
    tier = get_tier()

    console.print()
    console.print(Panel(
        f"[bold]Tier {tier}: {TIER_LABELS[tier]}[/bold]\n\n"
        + (
            "[dim]→ Tier 2: scoring, tailoring (needs LLM API key)[/dim]\n"
            "[dim]→ Tier 3: auto-apply (needs Claude CLI + Chrome)[/dim]"
            if tier == 1
            else "[dim]→ Tier 3: auto-apply (needs Claude CLI + Chrome)[/dim]"
            if tier == 2
            else "[green]All tiers unlocked![/green]"
        ),
        border_style="cyan",
        padding=(1, 2),
    ))

    console.print()


if __name__ == "__main__":
    app()
