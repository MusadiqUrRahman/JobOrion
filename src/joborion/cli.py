"""JobOrion CLI — the main entry point with premium terminal experience."""

from __future__ import annotations

import logging
from typing import Optional

import typer

from joborion.ui import (
    console,
    print_banner,
    print_startup_screen,
    print_screen_header,
    print_goal_panel,
    print_rule,
    print_spacer,
    print_success,
    print_error,
    print_warning,
    make_gradient_panel,
    print_success_banner,
    print_reflection_card,
    make_plan_table,
    make_stats_table,
    make_score_distribution_table,
    make_site_table,
    make_doctor_table,
    print_tier_panel,
    print_spinner,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S",
)

app = typer.Typer(
    name="joborion",
    help="[bold bright_cyan]AI-powered end-to-end job application pipeline[/bold bright_cyan]",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

VALID_STAGES = ("search", "details", "evaluate", "tailor", "letter", "export")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bootstrap() -> None:
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
    """[bold bright_cyan]JobOrion[/bold bright_cyan] — AI-powered job application pipeline."""
    if not version:
        print_startup_screen()


@app.command()
def init() -> None:
    """Run the first-time setup wizard (profile, resume, search config)."""
    from joborion.wizard.init import run_wizard

    print_screen_header("Setup Wizard", "First-time configuration", "🧙")
    run_wizard()


@app.command()
def plan(
    goal: str = typer.Argument(..., help="Your goal in plain language"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show plan without executing."),
    max_cost: float = typer.Option(5.0, "--max-cost", help="Maximum budget in USD."),
) -> None:
    """Plan job search pipeline from a natural language goal."""
    from joborion.agent.orchestrator import Orchestrator

    print_screen_header("Pipeline Planner", "Goal-driven execution plan", "🗺️")

    orch = Orchestrator(goal=goal, max_cost=max_cost)

    if dry_run:
        with print_spinner("Analyzing your goal..."):
            plan_result = orch.plan()

        print_spacer()
        print_goal_panel(goal)
        print_spacer()

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

        print_spacer()

        # Summary in elegant panel
        summary = f"""
  📊 Estimated cost:    [bold bright_yellow]${plan_result.total_cost:.4f}[/bold bright_yellow]
  ⏱️  Estimated time:    [bold bright_cyan]{plan_result.total_duration_ms / 1000:.1f}s[/bold bright_cyan]
  📋 Steps:             [bold bright_white]{len(plan_result.steps)}[/bold bright_white]
"""
        console.print(make_gradient_panel(
            summary,
            border_style="bright_cyan",
            padding=(0, 2),
        ))
        print_spacer()
    else:
        result = orch.execute()
        print_success_banner(
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
    print_screen_header("Reflection", "Learn from past runs", "🪞")

    conn = get_connection()
    reflector = Reflector(conn)

    if run_id:
        with print_spinner(f"Analyzing run {run_id}..."):
            result = reflector.analyze_run(run_id)
            ref_id = store_reflection(result, conn=conn)
        print_spacer()
        print_reflection_card(result, ref_id)
    else:
        runs = get_recent_runs(n=last)
        if not runs:
            console.print(make_gradient_panel(
                "[bright_yellow]No runs found to analyze.[/bright_yellow]\n\n"
                "  [dim]Run a pipeline first: [bold bright_cyan]joborion run --goal \"Find Python jobs\"[/bold bright_cyan][/dim]",
                border_style="bright_yellow",
                padding=(1, 2),
            ))
            return

        with print_spinner(f"Analyzing {len(runs)} run(s)..."):
            for run in runs:
                rid = run.get("run_id", "")
                result = reflector.analyze_run(rid)
                ref_id = store_reflection(result, conn=conn)

        print_spacer()
        for run in runs:
            rid = run.get("run_id", "")
            result = reflector.analyze_run(rid)
            ref_id = store_reflection(result, conn=conn)
            print_reflection_card(result, ref_id)
            print_spacer()


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

    # Goal-driven mode
    if goal:
        from joborion.agent.orchestrator import Orchestrator

        print_screen_header("Pipeline Runner", "Goal-driven execution", "🚀")

        orch = Orchestrator(goal=goal, max_cost=5.0, auto=auto, yes=yes, semi=semi)

        if auto:
            with print_spinner("Running autonomous pipeline..."):
                result = orch.execute_autonomous()
            report = result.get("report", "")
            console.print(make_gradient_panel(
                report,
                title="[bold bright_green]🏁 Autonomous Run Complete[/bold bright_green]",
                border_style="bright_green",
                padding=(1, 2),
            ))
        else:
            if dry_run:
                with print_spinner("Planning execution..."):
                    plan_result = orch.plan()

                print_spacer()
                print_goal_panel(goal)
                print_spacer()

                steps_data = [
                    {"tool": s.tool, "description": s.description, "cost_estimate": s.cost_estimate}
                    for s in plan_result.steps
                ]
                table = make_plan_table(steps_data)
                console.print(table)
                print_spacer()
            else:
                with print_spinner("Running pipeline..."):
                    result = orch.execute()
                print_success_banner(
                    "Pipeline completed!",
                    cost=result["total_cost"],
                    errors=len(result.get("errors", [])),
                )
        return

    # Legacy mode: explicit stages
    from joborion.pipeline import run_pipeline

    stage_list = stages if stages else ["all"]

    for s in stage_list:
        if s != "all" and s not in VALID_STAGES:
            print_error(f"Unknown stage: '{s}'")
            console.print(make_gradient_panel(
                f"[dim]Valid stages: {', '.join(VALID_STAGES)}, all[/dim]",
                border_style="bright_red",
            ))
            raise typer.Exit(code=1)

    llm_stages = {"evaluate", "tailor", "letter"}
    if any(s in stage_list for s in llm_stages) or "all" in stage_list:
        from joborion.config import check_tier
        check_tier(2, "AI scoring/tailoring")

    valid_modes = ("strict", "normal", "lenient")
    if validation not in valid_modes:
        print_error(f"Invalid --validation: '{validation}'")
        console.print(make_gradient_panel(
            f"[dim]Choose from: {', '.join(valid_modes)}[/dim]",
            border_style="bright_red",
        ))
        raise typer.Exit(code=1)

    # Stage pipeline view
    print_screen_header("Pipeline Runner", "Stage execution", "⚡")

    stage_flow = " → ".join(stage_list)
    console.print(make_gradient_panel(
        f"[bold bright_white]{stage_flow}[/bold bright_white]",
        title="[bold bright_cyan]Stages[/bold bright_cyan]",
        border_style="bright_cyan",
        padding=(0, 1),
    ))
    print_spacer()

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

    check_tier(3, "auto-apply")

    if not _profile_path.exists():
        print_error("Profile not found")
        console.print(make_gradient_panel(
            "[dim]Run [bold bright_cyan]joborion init[/bold bright_cyan] to create your profile first.[/dim]",
            border_style="bright_red",
            padding=(1, 2),
        ))
        raise typer.Exit(code=1)

    if not (gen and url):
        conn = get_connection()
        ready = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE tailored_resume_path IS NOT NULL AND applied_at IS NULL"
        ).fetchone()[0]
        if ready == 0:
            print_error("No tailored resumes ready")
            console.print(make_gradient_panel(
                "[dim]Run [bold bright_cyan]joborion run evaluate tailor[/bold bright_cyan] first.[/dim]",
                border_style="bright_red",
                padding=(1, 2),
            ))
            raise typer.Exit(code=1)

    if gen:
        from joborion.apply.runner import gen_prompt
        target = url or ""
        if not target:
            print_error("--gen requires --url")
            raise typer.Exit(code=1)
        prompt_file = gen_prompt(target, min_score=min_score, model=model)
        if not prompt_file:
            print_error("No matching job found")
            raise typer.Exit(code=1)
        mcp_path = _profile_path.parent / ".mcp-apply-0.json"
        print_success(f"Wrote prompt to: {prompt_file}")
        print_spacer()
        console.print(make_gradient_panel(
            f"[bold bright_white]Run manually:[/bold bright_white]\n"
            f"[dim]claude --model {model} -p "
            f"--mcp-config {mcp_path} "
            f"--permission-mode bypassPermissions < {prompt_file}[/dim]",
            border_style="bright_cyan",
            padding=(1, 2),
        ))
        return

    from joborion.apply.runner import main as apply_main

    effective_limit = limit if limit is not None else (0 if continuous else 1)

    print_screen_header("Auto-Apply", "Submit job applications", "🚀")

    # Config display
    config_lines = [
        f"  {'Limit':.<20} {'unlimited' if continuous else effective_limit}",
        f"  {'Workers':.<20} {workers}",
        f"  {'Model':.<20} {model}",
        f"  {'Headless':.<20} {headless}",
        f"  {'Dry run':.<20} {dry_run}",
    ]
    if url:
        config_lines.append(f"  {'Target':.<20} {url}")

    console.print(make_gradient_panel(
        "\n".join(config_lines),
        title="[bold bright_cyan]Configuration[/bold bright_cyan]",
        border_style="bright_cyan",
        padding=(1, 2),
    ))
    print_spacer()

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

    print_screen_header("Dashboard", "Pipeline statistics", "📊")
    print_spacer()

    # Stats table
    stats_table = make_stats_table(stats)
    console.print(stats_table)

    # Score distribution
    if stats["score_distribution"]:
        print_spacer()
        dist_table = make_score_distribution_table(stats["score_distribution"])
        console.print(dist_table)

    # By site
    if stats["by_site"]:
        print_spacer()
        site_table = make_site_table(stats["by_site"])
        console.print(site_table)

    print_spacer()
    print_rule("End of Report", "dim bright_cyan")
    print_spacer()


@app.command()
def dashboard() -> None:
    """Generate and open the HTML dashboard in your browser."""
    _bootstrap()

    from joborion.dashboard import open_dashboard

    print_screen_header("Dashboard", "Interactive web view", "🌐")
    with print_spinner("Generating dashboard..."):
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

    print_screen_header("System Doctor", "Setup diagnostics", "🩺")

    results: list[tuple[str, str, str, str]] = []

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
    table = make_doctor_table(results)
    console.print(table)

    # Tier summary
    from joborion.config import get_tier, TIER_LABELS
    tier = get_tier()

    print_spacer()
    print_tier_panel(tier, TIER_LABELS)
    print_spacer()


if __name__ == "__main__":
    app()
