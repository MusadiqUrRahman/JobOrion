"""JobOrion first-time setup wizard.

Interactive flow that creates ~/.joborion/ with:
  - resume.txt (and optionally resume.pdf)
  - profile.json
  - searches.yaml
  - .env (LLM API key)
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from joborion.config import (
    APP_DIR,
    ENV_PATH,
    PROFILE_PATH,
    RESUME_PATH,
    RESUME_PDF_PATH,
    SEARCH_CONFIG_PATH,
    ensure_dirs,
)

console = Console()


def _prompt_target_role(profile: dict, current_title: str = "") -> str:
    """Ask for the target role, never allowing a blank answer.

    Search (and profile-derived queries) require a target role, so the wizard
    reprompts until a non-blank value is provided.
    """
    while True:
        target_role = Prompt.ask(
            "Target role (what you're applying for, e.g. 'Senior Backend Engineer')",
            default=current_title,
        ).strip()
        if target_role:
            return target_role
        console.print("[red]Target role is required — JobOrion searches use it.[/red]")


# ---------------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------------

def _setup_resume() -> None:
    """Prompt for resume file and copy into APP_DIR."""
    console.print(Panel("[bold]Step 1: Resume[/bold]\nPoint to your master resume file (.txt or .pdf)."))

    while True:
        path_str = Prompt.ask("Resume file path")
        src = Path(path_str.strip().strip('"').strip("'")).expanduser().resolve()

        if not src.exists():
            console.print(f"[red]File not found:[/red] {src}")
            continue

        suffix = src.suffix.lower()
        if suffix not in (".txt", ".pdf"):
            console.print("[red]Unsupported format.[/red] Provide a .txt or .pdf file.")
            continue

        if suffix == ".txt":
            shutil.copy2(src, RESUME_PATH)
            console.print(f"[green]Copied to {RESUME_PATH}[/green]")
        elif suffix == ".pdf":
            shutil.copy2(src, RESUME_PDF_PATH)
            console.print(f"[green]Copied to {RESUME_PDF_PATH}[/green]")

            # Also ask for a plain-text version for LLM consumption
            txt_path_str = Prompt.ask(
                "Plain-text version of your resume (.txt)",
                default="",
            )
            if txt_path_str.strip():
                txt_src = Path(txt_path_str.strip().strip('"').strip("'")).expanduser().resolve()
                if txt_src.exists():
                    shutil.copy2(txt_src, RESUME_PATH)
                    console.print(f"[green]Copied to {RESUME_PATH}[/green]")
                else:
                    console.print("[yellow]File not found, skipping plain-text copy.[/yellow]")
        break


# ---------------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------------

def _setup_profile() -> dict:
    """Walk through profile questions and return a nested profile dict."""
    console.print(Panel("[bold]Step 2: Profile[/bold]\nTell JobOrion about yourself. This powers scoring, tailoring, and auto-fill."))

    profile: dict = {}

    # -- Personal --
    console.print("\n[bold cyan]Personal Information[/bold cyan]")
    full_name = Prompt.ask("Full name")
    profile["personal"] = {
        "full_name": full_name,
        "preferred_name": Prompt.ask("Preferred/nickname (leave blank to use first name)", default=""),
        "email": Prompt.ask("Email address"),
        "phone": Prompt.ask("Phone number", default=""),
        "city": Prompt.ask("City"),
        "province_state": Prompt.ask("Province/State (e.g. Ontario, California)", default=""),
        "country": Prompt.ask("Country"),
        "postal_code": Prompt.ask("Postal/ZIP code", default=""),
        "address": Prompt.ask("Street address (optional, used for form auto-fill)", default=""),
        "linkedin_url": Prompt.ask("LinkedIn URL", default=""),
        "github_url": Prompt.ask("GitHub URL (optional)", default=""),
        "portfolio_url": Prompt.ask("Portfolio URL (optional)", default=""),
        "website_url": Prompt.ask("Personal website URL (optional)", default=""),
        "password": Prompt.ask("Job site password (used for login walls during auto-apply)", password=True, default=""),
    }

    # -- Work Authorization --
    console.print("\n[bold cyan]Work Authorization[/bold cyan]")
    profile["work_authorization"] = {
        "legally_authorized_to_work": Confirm.ask("Are you legally authorized to work in your target country?"),
        "require_sponsorship": Confirm.ask("Will you now or in the future need sponsorship?"),
        "work_permit_type": Prompt.ask("Work permit type (e.g. Citizen, PR, Open Work Permit — leave blank if N/A)", default=""),
        "authorized_countries": [
            s.strip() for s in Prompt.ask(
                "Countries you're authorized to work in (comma-separated; blank = your country only)",
                default="",
            ).split(",") if s.strip()
        ],
        "relocation_willing": Confirm.ask(
            "Willing to relocate to another country for a role?",
            default=False,
        ),
    }

    # -- Compensation --
    console.print("\n[bold cyan]Compensation[/bold cyan]")
    salary = Prompt.ask("Expected annual salary (number)", default="")
    salary_currency = Prompt.ask("Currency", default="USD")
    salary_range = Prompt.ask("Acceptable range (e.g. 80000-120000)", default="")
    range_parts = salary_range.split("-") if "-" in salary_range else [salary, salary]
    profile["compensation"] = {
        "salary_expectation": salary,
        "salary_currency": salary_currency,
        "salary_range_min": range_parts[0].strip(),
        "salary_range_max": range_parts[1].strip() if len(range_parts) > 1 else range_parts[0].strip(),
    }

    # -- Experience --
    console.print("\n[bold cyan]Experience[/bold cyan]")
    current_title = Prompt.ask("Current/most recent job title", default="")
    target_role = _prompt_target_role(profile, current_title)
    profile["experience"] = {
        "years_of_experience_total": Prompt.ask("Years of professional experience", default=""),
        "education_level": Prompt.ask("Highest education (e.g. Bachelor's, Master's, PhD, Self-taught)", default=""),
        "current_title": current_title,
        "target_role": target_role,
    }

    # -- Skills Boundary --
    console.print("\n[bold cyan]Skills[/bold cyan] (comma-separated)")
    langs = Prompt.ask("Programming languages", default="")
    frameworks = Prompt.ask("Frameworks & libraries", default="")
    tools = Prompt.ask("Tools & platforms (e.g. Docker, AWS, Git)", default="")
    profile["skills_boundary"] = {
        "programming_languages": [s.strip() for s in langs.split(",") if s.strip()],
        "frameworks": [s.strip() for s in frameworks.split(",") if s.strip()],
        "tools": [s.strip() for s in tools.split(",") if s.strip()],
    }

    # -- Resume Facts (preserved truths for tailoring) --
    console.print("\n[bold cyan]Resume Facts[/bold cyan]")
    console.print("[dim]These are preserved exactly during resume tailoring — the AI will never change them.[/dim]")
    companies = Prompt.ask("Companies to always keep (comma-separated)", default="")
    projects = Prompt.ask("Projects to always keep (comma-separated)", default="")
    school = Prompt.ask("School name(s) to preserve", default="")
    metrics = Prompt.ask("Real metrics to preserve (e.g. '99.9% uptime, 50k users')", default="")
    profile["resume_facts"] = {
        "preserved_companies": [s.strip() for s in companies.split(",") if s.strip()],
        "preserved_projects": [s.strip() for s in projects.split(",") if s.strip()],
        "preserved_school": school.strip(),
        "real_metrics": [s.strip() for s in metrics.split(",") if s.strip()],
    }

    # -- EEO Voluntary (defaults) --
    profile["eeo_voluntary"] = {
        "gender": "Decline to self-identify",
        "race_ethnicity": "Decline to self-identify",
        "veteran_status": "Decline to self-identify",
        "disability_status": "Decline to self-identify",
    }

    # -- Availability --
    profile["availability"] = {
        "earliest_start_date": Prompt.ask("Earliest start date", default="Immediately"),
    }

    # Save
    PROFILE_PATH.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"\n[green]Profile saved to {PROFILE_PATH}[/green]")
    return profile


# ---------------------------------------------------------------------------
# Search config
# ---------------------------------------------------------------------------

def _setup_searches() -> None:
    """Generate a searches.yaml from user input."""
    console.print(Panel("[bold]Step 3: Job Search Config[/bold]\nDefine what you're looking for."))

    remote_only = Confirm.ask(
        "Only look for remote / work-from-home jobs?",
        default=False,
    )
    search_mode = Prompt.ask(
        "Search mode",
        choices=["remote", "local", "sponsorship", "all"],
        default="remote" if remote_only else "all",
    )
    location = Prompt.ask(
        "Target location (e.g. 'Remote', 'Canada', 'New York, NY', 'Lahore, Pakistan')",
        default="Remote" if remote_only else "",
    )
    distance_str = Prompt.ask("Search radius in miles (0 for no radius)", default="0")
    try:
        distance = int(distance_str)
    except ValueError:
        distance = 0

    roles_raw = Prompt.ask(
        "Target job titles (comma-separated, e.g. 'Backend Engineer, Full Stack Developer')"
    )
    roles = [r.strip() for r in roles_raw.split(",") if r.strip()]

    if not roles:
        # Fall back to the profile's target role so searches follow the
        # user's field (works for any profession, not just tech).
        try:
            profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            profile = {}
        target_role = ((profile.get("experience") or {}).get("target_role") or "").strip()
        if target_role:
            roles = [target_role]
            console.print(f"[dim]Using your target role: [bold]{target_role}[/bold][/dim]")
        else:
            console.print("[yellow]No roles provided and no target role set.[/yellow]")

    # Build YAML content
    lines = [
        "# JobOrion search configuration",
        "# Edit this file to refine your job search queries.",
        "",
        "defaults:",
        f'  location: "{location}"',
        f"  distance: {distance}",
        "  hours_old: 72",
        "  results_per_site: 50",
        f"  remote_only: {str(remote_only).lower()}",
        f"  search_mode: {search_mode}",
        "",
        "locations:",
        f'  - location: "{location}"',
        f"    remote: {str(remote_only).lower()}",
        "",
        "queries:",
    ]
    for i, role in enumerate(roles):
        lines.append(f'  - query: "{role}"')
        lines.append(f"    tier: {min(i + 1, 3)}")

    SEARCH_CONFIG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    console.print(f"[green]Search config saved to {SEARCH_CONFIG_PATH}[/green]")


# ---------------------------------------------------------------------------
# AI Features
# ---------------------------------------------------------------------------

def _setup_ai_features() -> None:
    """Configure LLM providers for AI scoring, tailoring, and cover letters.

    Generates a comprehensive .env with all supported providers pre-configured.
    The user only needs to paste API key(s) — base URLs and models are preset.
    Multiple keys mean automatic failover on rate limits.
    """
    console.print(Panel(
        "[bold]Step 4: AI Features (optional)[/bold]\n"
        "An LLM powers job scoring, resume tailoring, and cover letters.\n"
        "Configure one or more providers below. Multiple providers enable\n"
        "automatic failover if one hits rate limits.\n\n"
        "Supported: [bold]Gemini[/bold] (free), [bold]Anthropic[/bold] (Claude),\n"
        "[bold]OpenAI[/bold], [bold]OpenRouter[/bold], [bold]DeepSeek[/bold],\n"
        "other OpenAI-compatible APIs, and local [bold]Ollama[/bold]."
    ))

    if not Confirm.ask("Enable AI scoring and resume tailoring?", default=True):
        console.print("[dim]Discovery-only mode. You can configure AI later with [bold]joborion init[/bold].[/dim]")
        return

    env_lines = [
        "# =============================================================================",
        "# JobOrion LLM Configuration",
        "# =============================================================================",
        "# Paste API key(s) for your preferred provider(s).",
        "# All providers are pre-configured — you only need to paste your key(s).",
        "#",
        "# Multiple keys = automatic failover on rate limits.",
        "# Priority: Gemini (free) -> Anthropic -> OpenAI -> Custom -> Local",
        "# =============================================================================",
        "",
    ]

    # -- Gemini --
    console.print("\n[bold cyan]Option 1: Google Gemini[/bold cyan] [green](recommended, free tier)[/green]")
    console.print("  Get API key: https://aistudio.google.com/apikey")
    gemini_key = Prompt.ask("  Gemini API key (leave blank to skip)", default="")
    if gemini_key.strip():
        gemini_model = Prompt.ask("  Model", default="gemini-2.0-flash")
        env_lines.append(f"GEMINI_API_KEY={gemini_key.strip()}")
        env_lines.append(f"GEMINI_MODEL={gemini_model.strip()}")
    else:
        env_lines.append("# GEMINI_API_KEY=")
        env_lines.append("# GEMINI_MODEL=gemini-2.0-flash")
    env_lines.append("")

    # -- Anthropic --
    console.print("\n[bold cyan]Option 2: Anthropic (Claude)[/bold cyan]")
    console.print("  Get API key: https://console.anthropic.com/settings/keys")
    anthropic_key = Prompt.ask("  Anthropic API key (leave blank to skip)", default="")
    if anthropic_key.strip():
        anthropic_model = Prompt.ask("  Model", default="claude-sonnet-4-20250514")
        env_lines.append(f"ANTHROPIC_API_KEY={anthropic_key.strip()}")
        env_lines.append(f"ANTHROPIC_MODEL={anthropic_model.strip()}")
    else:
        env_lines.append("# ANTHROPIC_API_KEY=")
        env_lines.append("# ANTHROPIC_MODEL=claude-sonnet-4-20250514")
    env_lines.append("")

    # -- OpenAI --
    console.print("\n[bold cyan]Option 3: OpenAI[/bold cyan]")
    console.print("  Get API key: https://platform.openai.com/api-keys")
    openai_key = Prompt.ask("  OpenAI API key (leave blank to skip)", default="")
    if openai_key.strip():
        openai_model = Prompt.ask("  Model", default="gpt-4o-mini")
        env_lines.append(f"OPENAI_API_KEY={openai_key.strip()}")
        env_lines.append(f"OPENAI_MODEL={openai_model.strip()}")
        env_lines.append("# OPENAI_BASE_URL=    (set only for OpenRouter or custom endpoints)")
    else:
        env_lines.append("# OPENAI_API_KEY=")
        env_lines.append("# OPENAI_MODEL=gpt-4o-mini")
        env_lines.append("# OPENAI_BASE_URL=")
    env_lines.append("")

    # -- OpenRouter (uses OPENAI_API_KEY + OPENAI_BASE_URL) --
    console.print("\n[bold cyan]Option 4: OpenRouter[/bold cyan] [dim](200+ models)[/dim]")
    console.print("  Get API key: https://openrouter.ai/keys")
    console.print("  [dim]Uses OPENAI_API_KEY with a custom base URL.[/dim]")
    or_key = Prompt.ask("  OpenRouter API key (leave blank to skip)", default="")
    if or_key.strip():
        or_model = Prompt.ask("  Model", default="gpt-4o-mini")
        env_lines.append(f"OPENAI_API_KEY={or_key.strip()}")
        env_lines.append("OPENAI_BASE_URL=https://openrouter.ai/api/v1")
        env_lines.append(f"OPENAI_MODEL={or_model.strip()}")
    env_lines.append("")

    # -- Custom OpenAI-compatible (DeepSeek, Together, Groq, etc.) --
    console.print("\n[bold cyan]Option 5: Custom OpenAI-compatible[/bold cyan] [dim](DeepSeek, Together, Groq, etc.)[/dim]")
    custom_key = Prompt.ask("  API key (leave blank to skip)", default="")
    if custom_key.strip():
        custom_base = Prompt.ask("  Base URL", default="https://api.deepseek.com/v1")
        custom_model = Prompt.ask("  Model", default="deepseek-chat")
        env_lines.append(f"CUSTOM_API_KEY={custom_key.strip()}")
        env_lines.append(f"CUSTOM_BASE_URL={custom_base.strip()}")
        env_lines.append(f"CUSTOM_MODEL={custom_model.strip()}")
    else:
        env_lines.append("# CUSTOM_API_KEY=")
        env_lines.append("# CUSTOM_BASE_URL=")
        env_lines.append("# CUSTOM_MODEL=deepseek-chat")
    env_lines.append("")

    # -- Local --
    console.print("\n[bold cyan]Option 6: Local (Ollama / llama.cpp)[/bold cyan]")
    local_url = Prompt.ask("  Local endpoint URL (leave blank to skip)", default="")
    if local_url.strip():
        local_model = Prompt.ask("  Model name", default="llama3.2:3b")
        env_lines.append(f"LLM_URL={local_url.strip()}")
        env_lines.append(f"LLM_MODEL={local_model.strip()}")
        local_key = Prompt.ask("  API key (if required)", default="")
        if local_key.strip():
            env_lines.append(f"LLM_API_KEY={local_key.strip()}")
    else:
        env_lines.append("# LLM_URL=")
        env_lines.append("# LLM_MODEL=llama3.2:3b")
        env_lines.append("# LLM_API_KEY=")
    env_lines.append("")

    # -- Global settings --
    env_lines.append("# -- Global settings --")
    env_lines.append("LLM_MAX_CALLS=500")
    env_lines.append("LLM_MAX_COST=5.0")
    env_lines.append("")

    ENV_PATH.write_text("\n".join(env_lines), encoding="utf-8")
    console.print(f"\n[green]AI configuration saved to {ENV_PATH}[/green]")
    console.print("[dim]You can re-run this anytime or edit the file directly.[/dim]")


# ---------------------------------------------------------------------------
# Auto-Apply
# ---------------------------------------------------------------------------

def _setup_auto_apply() -> None:
    """Configure autonomous job application (requires Claude Code CLI)."""
    console.print(Panel(
        "[bold]Step 5: Auto-Apply (optional)[/bold]\n"
        "JobOrion can autonomously fill and submit job applications\n"
        "using Claude Code as the browser agent."
    ))

    if not Confirm.ask("Enable autonomous job applications?", default=True):
        console.print("[dim]You can apply manually using the tailored resumes JobOrion generates.[/dim]")
        return

    # Check for Claude Code CLI
    if shutil.which("claude"):
        console.print("[green]Claude Code CLI detected.[/green]")
    else:
        console.print(
            "[yellow]Claude Code CLI not found on PATH.[/yellow]\n"
            "Install it from: [bold]https://claude.ai/code[/bold]\n"
            "Auto-apply won't work until Claude Code is installed."
        )

    # Optional: CapSolver for CAPTCHAs
    console.print("\n[dim]Some job sites use CAPTCHAs. CapSolver can handle them automatically.[/dim]")
    if Confirm.ask("Configure CapSolver API key? (optional)", default=False):
        capsolver_key = Prompt.ask("CapSolver API key")
        # Append to existing .env or create
        if ENV_PATH.exists():
            existing = ENV_PATH.read_text(encoding="utf-8")
            if "CAPSOLVER_API_KEY" not in existing:
                ENV_PATH.write_text(
                    existing.rstrip() + f"\nCAPSOLVER_API_KEY={capsolver_key}\n",
                    encoding="utf-8",
                )
        else:
            ENV_PATH.write_text(f"# JobOrion configuration\nCAPSOLVER_API_KEY={capsolver_key}\n", encoding="utf-8")
        console.print("[green]CapSolver key saved.[/green]")
    else:
        console.print("[dim]Skipped. Add CAPSOLVER_API_KEY to .env later if needed.[/dim]")


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def run_wizard() -> None:
    """Run the full interactive setup wizard."""
    console.print()
    console.print(
        Panel.fit(
            "[bold green]JobOrion Setup Wizard[/bold green]\n\n"
            "This will create your configuration at:\n"
            f"  [cyan]{APP_DIR}[/cyan]\n\n"
            "You can re-run this anytime with [bold]joborion init[/bold].",
            border_style="green",
        )
    )

    ensure_dirs()
    console.print(f"[dim]Created {APP_DIR}[/dim]\n")

    # Step 1: Resume
    _setup_resume()
    console.print()

    # Step 2: Profile
    _setup_profile()
    console.print()

    # Step 3: Search config
    _setup_searches()
    console.print()

    # Step 4: AI features (optional LLM)
    _setup_ai_features()
    console.print()

    # Step 5: Auto-apply (Claude Code detection)
    _setup_auto_apply()
    console.print()

    # Done — show tier status
    from joborion.config import get_tier, TIER_LABELS, TIER_COMMANDS

    tier = get_tier()

    tier_lines: list[str] = []
    for t in range(1, 4):
        label = TIER_LABELS[t]
        cmds = ", ".join(f"[bold]{c}[/bold]" for c in TIER_COMMANDS[t])
        if t <= tier:
            tier_lines.append(f"  [green]✓ Tier {t} — {label}[/green]  ({cmds})")
        elif t == tier + 1:
            tier_lines.append(f"  [yellow]→ Tier {t} — {label}[/yellow]  ({cmds})")
        else:
            tier_lines.append(f"  [dim]✗ Tier {t} — {label}  ({cmds})[/dim]")

    unlock_hint = ""
    if tier == 1:
        unlock_hint = "\n[dim]To unlock Tier 2: configure an LLM API key (re-run [bold]joborion init[/bold]).[/dim]"
    elif tier == 2:
        unlock_hint = "\n[dim]To unlock Tier 3: install Claude Code CLI + Chrome.[/dim]"

    console.print(
        Panel.fit(
            "[bold green]Setup complete![/bold green]\n\n"
            f"[bold]Your tier: Tier {tier} — {TIER_LABELS[tier]}[/bold]\n\n"
            + "\n".join(tier_lines)
            + unlock_hint,
            border_style="green",
        )
    )
