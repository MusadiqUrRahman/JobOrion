"""JobOrion UI — beautiful terminal interface components.

Provides colorful, modern terminal output with panels, tables,
progress indicators, and styled text.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

console = Console()

# Color palette
COLORS = {
    "primary": "cyan",
    "secondary": "magenta",
    "success": "green",
    "warning": "yellow",
    "error": "red",
    "info": "blue",
    "dim": "dim white",
    "bright": "bright_white",
    "accent": "bright_cyan",
}

# Stage colors
STAGE_COLORS = {
    "search": "bright_cyan",
    "details": "bright_blue",
    "evaluate": "bright_yellow",
    "tailor": "bright_green",
    "letter": "bright_magenta",
    "export": "bright_white",
}

# Stage emojis
STAGE_EMOJI = {
    "search": "🔍",
    "details": "📋",
    "evaluate": "⚡",
    "tailor": "✂️",
    "letter": "✉️",
    "export": "📄",
}


def print_banner() -> None:
    """Print the main application banner."""
    banner = """
[bold bright_cyan]
     ██╗ ██████╗ ██████╗ ██╗   ██╗███████╗███████╗████████╗
     ██║██╔═══██╗██╔══██╗╚██╗ ██╔╝██╔════╝██╔════╝╚══██╔══╝
     ██║██║   ██║██████╔╝ ╚████╔╝ █████╗  ███████╗   ██║
██   ██║██║   ██║██╔══██╗  ╚██╔╝  ██╔══╝  ╚════██║   ██║
╚█████╔╝╚██████╔╝██║  ██║   ██║   ███████╗███████║   ██║
 ╚════╝  ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝╚══════╝   ╚═╝
[/bold bright_cyan]
[dim]AI-Powered Job Application Pipeline[/dim]"""
    console.print(banner)


def print_stage_header(stage: str, description: str) -> None:
    """Print a styled stage header."""
    emoji = STAGE_EMOJI.get(stage, "▶")
    color = STAGE_COLORS.get(stage, "white")
    console.print()
    console.print(Panel(
        f"[bold {color}]{emoji} {stage.upper()}[/{color}] — {description}",
        border_style=color,
        padding=(0, 1),
    ))


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"  [green]✓[/green] {message}")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"  [red]✗[/red] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"  [yellow]⚠[/yellow] {message}")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"  [cyan]ℹ[/cyan] {message}")


def print_progress(current: int, total: int, label: str = "") -> None:
    """Print a progress bar."""
    if total == 0:
        pct = 0
    else:
        pct = int(current / total * 100)
    filled = int(pct / 5)
    bar = "█" * filled + "░" * (20 - filled)

    if pct >= 80:
        color = "green"
    elif pct >= 50:
        color = "yellow"
    else:
        color = "red"

    console.print(f"  [{color}]{bar}[/{color}] {pct}% {label}")


def make_pipeline_table(stages: list[dict]) -> Table:
    """Create a beautiful pipeline status table.

    Args:
        stages: List of dicts with keys: name, status, count.
    """
    table = Table(
        title="[bold bright_cyan]Pipeline Status[/bold bright_cyan]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        border_style="bright_blue",
        padding=(0, 1),
    )

    table.add_column("Stage", style="bold", width=12)
    table.add_column("Status", justify="center", width=10)
    table.add_column("Count", justify="right", width=8)
    table.add_column("Progress", width=22)

    for stage in stages:
        name = stage.get("name", "?")
        status = stage.get("status", "pending")
        count = stage.get("count", 0)

        emoji = STAGE_EMOJI.get(name, "▶")
        color = STAGE_COLORS.get(name, "white")

        # Status badge
        if status == "ok":
            status_badge = "[green]✓ Done[/green]"
        elif status == "running":
            status_badge = "[yellow]⏳ Running[/yellow]"
        elif status == "error":
            status_badge = "[red]✗ Error[/red]"
        else:
            status_badge = "[dim]○ Pending[/dim]"

        # Progress bar
        if status == "ok":
            progress = "[green]████████████████████[/green]"
        elif status == "running":
            progress = "[yellow]████████████░░░░░░░░[/yellow]"
        else:
            progress = "[dim]░░░░░░░░░░░░░░░░░░░░[/dim]"

        table.add_row(
            f"[{color}]{emoji} {name}[/{color}]",
            status_badge,
            str(count),
            progress,
        )

    return table


def make_stats_table(stats: dict) -> Table:
    """Create a beautiful statistics table."""
    table = Table(
        title="[bold bright_cyan]Job Statistics[/bold bright_cyan]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold magenta",
        border_style="bright_magenta",
        padding=(0, 1),
    )

    table.add_column("Metric", style="bold", width=25)
    table.add_column("Count", justify="right", width=10)
    table.add_column("Bar", width=20)

    max_val = max(
        stats.get("total", 1),
        stats.get("scored", 1),
        stats.get("tailored", 1),
        1,
    )

    rows = [
        ("📦 Total jobs", stats.get("total", 0)),
        ("📋 With description", stats.get("with_description", 0)),
        ("⚡ Scored", stats.get("scored", 0)),
        ("✂️ Tailored", stats.get("tailored", 0)),
        ("✉️ Cover letters", stats.get("with_cover_letter", 0)),
        ("✅ Applied", stats.get("applied", 0)),
    ]

    for label, count in rows:
        bar_len = int(count / max_val * 18) if max_val > 0 else 0
        if count > 0:
            bar = f"[green]{'█' * bar_len}{'░' * (18 - bar_len)}[/green]"
        else:
            bar = f"[dim]{'░' * 18}[/dim]"
        table.add_row(label, str(count), bar)

    return table


def make_cost_table(costs: dict) -> Table:
    """Create a cost breakdown table."""
    table = Table(
        title="[bold bright_cyan]Cost Breakdown[/bold bright_cyan]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold yellow",
        border_style="bright_yellow",
        padding=(0, 1),
    )

    table.add_column("Component", style="bold", width=20)
    table.add_column("Cost", justify="right", width=12)

    total = costs.get("total", 0.0)
    by_tool = costs.get("by_tool", {})

    for tool, cost in by_tool.items():
        table.add_row(tool, f"[yellow]${cost:.4f}[/yellow]")

    table.add_section()
    table.add_row("[bold]Total[/bold]", f"[bold green]${total:.4f}[/bold green]")

    return table


def make_plan_table(steps: list[dict]) -> Table:
    """Create an execution plan table."""
    table = Table(
        title="[bold bright_cyan]Execution Plan[/bold bright_cyan]",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        border_style="bright_cyan",
        padding=(0, 1),
    )

    table.add_column("#", justify="right", width=3, style="dim")
    table.add_column("Stage", style="bold", width=12)
    table.add_column("Description", width=35)
    table.add_column("Est. Cost", justify="right", width=10)

    for i, step in enumerate(steps, 1):
        name = step.get("tool", "?")
        desc = step.get("description", "")
        cost = step.get("cost_estimate", 0.0)
        color = STAGE_COLORS.get(name.split("_")[0], "white")
        emoji = STAGE_EMOJI.get(name.split("_")[0], "▶")

        table.add_row(
            str(i),
            f"[{color}]{emoji} {name}[/{color}]",
            desc,
            f"${cost:.4f}",
        )

    return table


def print_completed(message: str, cost: float = 0.0, errors: int = 0) -> None:
    """Print a completion banner."""
    console.print()
    console.print(Panel(
        f"[bold green]✓ {message}[/bold green]\n\n"
        f"Cost: [bold yellow]${cost:.4f}[/bold yellow]\n"
        f"Errors: [bold {'red' if errors else 'green'}]{errors}[/bold {'red' if errors else 'green'}]",
        border_style="green",
        padding=(1, 2),
    ))


def print_reflection_card(result: dict, ref_id: str) -> None:
    """Print a beautiful reflection card."""
    rating = result.get("overall_rating", "ok")
    rating_colors = {"good": "green", "ok": "yellow", "poor": "red"}
    rating_emoji = {"good": "🌟", "ok": "⭐", "poor": "💔"}
    color = rating_colors.get(rating, "white")
    emoji = rating_emoji.get(rating, "❓")

    # Build content
    content = Text()
    content.append(f"Run: {result.get('run_id', '?')}\n", style="dim")
    content.append(f"\n{emoji} Rating: ", style="bold")
    content.append(rating.upper(), style=f"bold {color}")

    if result.get("what_went_well"):
        content.append("\n\n✅ What went well:\n", style="bold green")
        for item in result["what_went_well"][:3]:
            content.append(f"   • {item}\n", style="green")

    if result.get("what_failed"):
        content.append("\n❌ What failed:\n", style="bold red")
        for item in result["what_failed"][:3]:
            content.append(f"   • {item}\n", style="red")

    if result.get("recommendations"):
        content.append("\n💡 Recommendations:\n", style="bold cyan")
        for i, rec in enumerate(result["recommendations"][:3], 1):
            content.append(f"   {i}. {rec}\n", style="cyan")

    console.print(Panel(
        content,
        title=f"[bold]Reflection[/bold] [dim]({ref_id})[/dim]",
        border_style=color,
        padding=(1, 2),
    ))
