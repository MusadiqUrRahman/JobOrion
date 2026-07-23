"""JobOrion UI — premium terminal experience.

Gradient-style branding, elegant panels, modern spinners,
smooth progress bars, tasteful transitions. Every screen polished.
"""

from __future__ import annotations

import itertools
from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.rule import Rule
from rich import box

console = Console()

# ─── Color Palette ────────────────────────────────────────────────────────────

# Gradient stops for the banner (top → bottom)
BANNER_GRADIENT = ["bright_cyan", "cyan", "bright_magenta", "magenta"]

# Stage theming
STAGE_COLORS: dict[str, str] = {
    "search": "bright_cyan",
    "details": "bright_blue",
    "evaluate": "bright_yellow",
    "tailor": "bright_green",
    "letter": "bright_magenta",
    "export": "bright_white",
}

STAGE_EMOJI: dict[str, str] = {
    "search": "🔍",
    "details": "📋",
    "evaluate": "⚡",
    "tailor": "✂️",
    "letter": "✉️",
    "export": "📄",
}

BANNER_TEXT = "JOBORION"

# Unicode building blocks for decorative elements
HLINE = "─"
VLINE = "│"
CORNER_TL = "╭"
CORNER_TR = "╮"
CORNER_BL = "╰"
CORNER_BR = "╯"
DOT = "●"
DIAMOND = "◆"
STAR = "✦"
ARROW = "→"
BULLET = "•"


# ─── Banner ──────────────────────────────────────────────────────────────────


def _render_banner_art() -> str:
    try:
        import pyfiglet
        return pyfiglet.figlet_format(BANNER_TEXT, font="doom").rstrip()
    except Exception:
        return f"  {BANNER_TEXT}"


def _gradient_line(text: str, colors: list[str]) -> Text:
    """Apply a gradient across a line by character position."""
    rich_text = Text(text)
    n = len(text)
    if n == 0 or not colors:
        return rich_text
    for i, ch in enumerate(text):
        if ch in (" ", "\n", "\t"):
            continue
        idx = int(i / max(n - 1, 1) * (len(colors) - 1))
        rich_text.stylize(f"bold {colors[idx]}", i, i + 1)
    return rich_text


def print_banner() -> None:
    """Print the main application banner with gradient coloring and tagline."""
    art = _render_banner_art()
    lines = art.split("\n")

    group_parts: list[Any] = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        color_idx = int(i / max(len(lines) - 1, 1) * (len(BANNER_GRADIENT) - 1))
        color = BANNER_GRADIENT[color_idx]
        group_parts.append(Text(f"  {line}", style=f"bold {color}"))

    tagline = Text()
    tagline.append("  AI-Powered Job Application Pipeline", style="dim bright_white")
    group_parts.append(tagline)

    console.print(Group(*group_parts))
    console.print()


# ─── Startup Screen ──────────────────────────────────────────────────────────

def _get_version() -> str:
    try:
        from joborion import __version__
        return __version__
    except Exception:
        return "0.3.0"


def _get_tier_info() -> tuple[int, str]:
    try:
        from joborion.config import get_tier, TIER_LABELS
        tier = get_tier()
        return tier, TIER_LABELS[tier]
    except Exception:
        return 1, "Discovery"


def _get_stats_summary() -> dict[str, int]:
    try:
        from joborion.database import get_stats
        stats = get_stats()
        return {
            "jobs": stats.get("total", 0),
            "scored": stats.get("scored", 0),
            "applied": stats.get("applied", 0),
        }
    except Exception:
        return {"jobs": 0, "scored": 0, "applied": 0}


def print_startup_screen() -> None:
    """Print the premium startup screen with banner, pipeline diagram, and system info."""
    import shutil
    import os

    version = _get_version()
    tier, tier_label = _get_tier_info()
    stats = _get_stats_summary()

    # ── Banner ──
    art = _render_banner_art()
    lines = art.split("\n")
    group_parts: list[Any] = []
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        color_idx = int(i / max(len(lines) - 1, 1) * (len(BANNER_GRADIENT) - 1))
        color = BANNER_GRADIENT[color_idx]
        group_parts.append(Text(f"  {line}", style=f"bold {color}"))
    console.print(Group(*group_parts))

    # ── Tagline + Version ──
    tagline = Text()
    tagline.append("  AI-Powered Job Application Pipeline", style="dim bright_white")
    tagline.append(f"  v{version}", style="dim bright_cyan")
    group_parts.append(tagline)
    console.print(tagline)
    console.print()

    # ── Pipeline Diagram ──
    pipeline = Text()
    pipeline.append("  ╭─────────────────────────────────────────────────────────────────────╮\n", style="dim bright_cyan")
    pipeline.append("  │", style="dim bright_cyan")
    pipeline.append("  ⚡ PIPELINE", style="bold bright_white")
    pipeline.append("                                                                   │\n", style="dim bright_cyan")
    pipeline.append("  │", style="dim bright_cyan")
    pipeline.append("                                                                     │\n", style="dim bright_cyan")
    pipeline.append("  │", style="dim bright_cyan")
    pipeline.append("   🔍 SEARCH", style="bold bright_cyan")
    pipeline.append("  ───→  ", style="dim bright_cyan")
    pipeline.append("📋 DETAILS", style="bold bright_blue")
    pipeline.append("  ───→  ", style="dim bright_cyan")
    pipeline.append("⚡ EVAL", style="bold bright_yellow")
    pipeline.append("                                                              │\n", style="dim bright_cyan")
    pipeline.append("  │", style="dim bright_cyan")
    pipeline.append("                                                                     │\n", style="dim bright_cyan")
    pipeline.append("  │", style="dim bright_cyan")
    pipeline.append("   ✂️  TAILOR", style="bold bright_green")
    pipeline.append("  ───→  ", style="dim bright_cyan")
    pipeline.append("✉️  LETTER", style="bold bright_magenta")
    pipeline.append("  ───→  ", style="dim bright_cyan")
    pipeline.append("📄 EXPORT", style="bold bright_white")
    pipeline.append("                                                           │\n", style="dim bright_cyan")
    pipeline.append("  │", style="dim bright_cyan")
    pipeline.append("                                                                     │\n", style="dim bright_cyan")
    pipeline.append("  ╰─────────────────────────────────────────────────────────────────────╯\n", style="dim bright_cyan")
    console.print(pipeline)

    # ── Info Grid ──
    has_claude = shutil.which("claude") is not None
    has_chrome = False
    try:
        from joborion.config import get_chrome_path
        get_chrome_path()
        has_chrome = True
    except Exception:
        pass

    has_llm = any([
        os.environ.get("GEMINI_API_KEY"),
        os.environ.get("OPENAI_API_KEY"),
        os.environ.get("LLM_URL"),
    ])

    info = Table.grid(padding=(0, 2))
    info.add_column(style="bold bright_white", width=18)
    info.add_column(style="bright_white")

    # Row 1
    tier_color = {1: "bright_yellow", 2: "bright_cyan", 3: "bright_green"}.get(tier, "white")
    info.add_row("  🎯 Tier", Text(f"{tier} — {tier_label}", style=f"bold {tier_color}"))
    info.add_row("  📊 Jobs", Text(f"{stats['jobs']} found  |  {stats['scored']} scored  |  {stats['applied']} applied", style="bright_white"))
    info.add_row("  🤖 LLM", Text("Ready" if has_llm else "Not configured", style="bright_green" if has_llm else "dim bright_red"))
    info.add_row("  🌐 Browser", Text("Ready" if has_chrome else "Not found", style="bright_green" if has_chrome else "dim bright_red"))
    info.add_row("  🤖 Claude CLI", Text("Ready" if has_claude else "Not found", style="bright_green" if has_claude else "dim bright_red"))

    console.print(Panel(
        info,
        title="[bold bright_cyan]System Status[/bold bright_cyan]",
        border_style="bright_cyan",
        box=box.ROUNDED,
        padding=(0, 1),
    ))
    console.print()


def print_splash() -> None:
    """Print a brief animated splash when launching."""
    print_startup_screen()


def print_rule(title: str = "", style: str = "dim bright_cyan") -> None:
    """Print a decorative horizontal rule with optional title."""
    console.print(Rule(title, style=style))


def print_transition(title: str = "") -> None:
    """Print an elegant transition between sections."""
    console.print()
    if title:
        console.print(Rule(f" {title} ", style="bright_cyan"))
    else:
        console.print(Rule(style="dim bright_cyan"))
    console.print()


def print_spacer() -> None:
    """Print a small vertical spacer."""
    console.print()


def print_dot_line(style: str = "dim bright_cyan") -> None:
    """Print a decorative dot line."""
    dots = f"  {DOT} " * 30
    console.print(Text(dots, style=style))


# ─── Screen Headers ──────────────────────────────────────────────────────────


def print_screen_header(title: str, subtitle: str = "", icon: str = "") -> None:
    """Print an elegant screen header with decorative border."""
    header = Text()
    if icon:
        header.append(f"  {icon} ", style="bold bright_cyan")
    header.append(title, style="bold bright_white")
    if subtitle:
        header.append(f"  {subtitle}", style="dim")

    console.print()
    console.print(Panel(
        header,
        border_style="bright_cyan",
        box=box.DOUBLE_EDGE,
        padding=(0, 1),
    ))
    console.print()


# ─── Status Badges ───────────────────────────────────────────────────────────


def make_status_badge(status: str) -> Text:
    """Create a colored status badge."""
    badges = {
        "done": ("✓ Done", "bold bright_green"),
        "running": ("⟳ Running", "bold bright_yellow"),
        "error": ("✗ Error", "bold bright_red"),
        "pending": ("○ Pending", "dim"),
        "skipped": ("⊘ Skipped", "dim bright_white"),
    }
    text, style = badges.get(status, (status, "dim"))
    return Text(text, style=style)


# ─── Panels ──────────────────────────────────────────────────────────────────


def make_gradient_panel(
    content: str | Text,
    title: str = "",
    subtitle: str = "",
    border_style: str = "bright_cyan",
    padding: tuple[int, int] = (1, 2),
) -> Panel:
    """Create an elegant panel with optional title and subtitle."""
    if title:
        title_text = Text(title, style="bold bright_white")
        if subtitle:
            title_text.append(f"  {subtitle}", style="dim")
        return Panel(
            content,
            title=title_text,
            border_style=border_style,
            box=box.ROUNDED,
            padding=padding,
        )
    return Panel(
        content,
        border_style=border_style,
        box=box.ROUNDED,
        padding=padding,
    )


def print_goal_panel(goal: str) -> None:
    """Print an elegant goal display panel."""
    content = Text()
    content.append(f'  "{goal}"', style="bold bright_white")
    console.print(Panel(
        content,
        title="[bold bright_cyan]🎯 Goal[/bold bright_cyan]",
        subtitle="[dim]Natural Language[/dim]",
        border_style="bright_cyan",
        box=box.ROUNDED,
        padding=(1, 2),
    ))


# ─── Progress & Spinners ─────────────────────────────────────────────────────


def print_progress_bar(current: int, total: int, label: str = "", width: int = 30) -> None:
    """Print a beautiful gradient progress bar."""
    pct = int(current / max(total, 1) * 100)
    filled = int(pct / 100 * width)
    empty = width - filled

    # Color based on progress
    if pct >= 80:
        bar_color = "bright_green"
    elif pct >= 50:
        bar_color = "bright_yellow"
    elif pct >= 25:
        bar_color = "bright_cyan"
    else:
        bar_color = "bright_red"

    bar = Text()
    bar.append("  ▏", style="dim")
    bar.append("█" * filled, style=f"bold {bar_color}")
    bar.append("░" * empty, style="dim")
    bar.append(" ▕", style="dim")
    bar.append(f"  {pct:3d}%", style=f"bold {bar_color}")
    if label:
        bar.append(f"  {label}", style="dim")

    console.print(bar)


def make_progress_bar(current: int, total: int, width: int = 30) -> Text:
    """Create a gradient progress bar as Text."""
    pct = int(current / max(total, 1) * 100)
    filled = int(pct / 100 * width)
    empty = width - filled

    if pct >= 80:
        bar_color = "bright_green"
    elif pct >= 50:
        bar_color = "bright_yellow"
    elif pct >= 25:
        bar_color = "bright_cyan"
    else:
        bar_color = "bright_red"

    bar = Text()
    bar.append("▏", style="dim")
    bar.append("█" * filled, style=f"bold {bar_color}")
    bar.append("░" * empty, style="dim")
    bar.append(" ▕ ", style="dim")
    bar.append(f"{pct:3d}%", style=f"bold {bar_color}")
    return bar


class SpinnerContext:
    """Context manager for a Rich spinner."""

    def __init__(self, message: str = "Working...", spinner: str = "dots"):
        self._status = console.status(f"[bold bright_cyan]{message}", spinner=spinner)

    def __enter__(self):
        self._status.start()
        return self

    def __exit__(self, *args):
        self._status.stop()

    def update(self, message: str) -> None:
        self._status.update(f"[bold bright_cyan]{message}")


def print_spinner(message: str = "Working...") -> SpinnerContext:
    """Return a spinner context manager for use in `with` blocks."""
    return SpinnerContext(message)


# ─── Hermes-Grade: Themed Spinners ───────────────────────────────────────────

# Animated faces cycled while waiting (Hermes-style)
WAITING_FACES = ["(⟳)", "(◆)", "(●)", "(★)", "(◇)", "(▲)"]

# Thinking faces during model reasoning
THINKING_FACES = ["(⚡)", "(◆)", "(●)", "(★)"]

# Themed verbs for spinner messages
THINKING_VERBS = [
    "searching",
    "analyzing",
    "scoring",
    "tailoring",
    "generating",
    "processing",
    "evaluating",
    "optimizing",
]

# Decorative wings/brackets around spinner
WINGS = [
    ("⟪ ", " ⟫"),
    ("〈 ", " 〉"),
    ("〖 ", " 〗"),
]

_face_cycle = itertools.cycle(WAITING_FACES)


def print_tool_line(message: str, indent: int = 1) -> None:
    """Print a tool output line with Hermes-style ┊ prefix."""
    prefix = "┊ " * indent
    text = Text()
    text.append(f"  {prefix}", style="dim bright_cyan")
    text.append(message, style="bright_white")
    console.print(text)


def print_stage_progress(
    stage: str,
    message: str,
    progress: int = 0,
    total: int = 100,
) -> None:
    """Print a streaming stage progress line with animated indicator."""
    emoji = STAGE_EMOJI.get(stage, "▶")
    color = STAGE_COLORS.get(stage, "white")
    face = next(_face_cycle)

    pct = int(progress / max(total, 1) * 100)
    filled = int(pct / 100 * 20)
    empty = 20 - filled

    bar_color = "bright_green" if pct >= 80 else "bright_yellow" if pct >= 50 else "bright_cyan"

    line = Text()
    line.append(f"  {face} ", style="bold bright_cyan")
    line.append(f"{emoji} {stage.upper()}", style=f"bold {color}")
    line.append("  ", style="dim")
    line.append("█" * filled, style=f"bold {bar_color}")
    line.append("░" * empty, style="dim")
    line.append(f" {pct:3d}%", style=f"bold {bar_color}")
    line.append(f"  {message}", style="dim")

    console.print(line)


def print_streaming_update(stage: str, message: str) -> None:
    """Print a streaming update with tool prefix."""
    emoji = STAGE_EMOJI.get(stage, "▶")
    color = STAGE_COLORS.get(stage, "white")

    line = Text()
    line.append("  ┊ ", style="dim bright_cyan")
    line.append(f"{emoji} ", style=f"bold {color}")
    line.append(message, style="bright_white")
    console.print(line)


# ─── Hermes-Grade: Compact Mode ──────────────────────────────────────────────

def get_terminal_width() -> int:
    """Get current terminal width."""
    return console.width


def is_compact_mode() -> bool:
    """Check if terminal is in compact mode (< 76 columns)."""
    return console.width < 76


def is_minimal_mode() -> bool:
    """Check if terminal is in minimal mode (< 52 columns)."""
    return console.width < 52


def print_compact_header(title: str, icon: str = "") -> None:
    """Print a compact header for narrow terminals."""
    if is_minimal_mode():
        header = Text()
        if icon:
            header.append(f"{icon} ", style="bold bright_cyan")
        header.append(title, style="bold bright_white")
        console.print(header)
    elif is_compact_mode():
        header = Text()
        if icon:
            header.append(f"{icon} ", style="bold bright_cyan")
        header.append(title, style="bold bright_white")
        console.print(Panel(header, border_style="bright_cyan", padding=(0, 1)))
    else:
        print_screen_header(title, icon=icon)


# ─── Hermes-Grade: Status Bar ────────────────────────────────────────────────

def print_status_bar(
    model: str = "",
    tokens_used: int = 0,
    tokens_max: int = 0,
    cost: float = 0.0,
    duration: str = "",
    stage: str = "",
) -> None:
    """Print a Hermes-style status bar above the input area."""
    bar = Text()
    bar.append("─" * console.width, style="dim bright_cyan")
    console.print(bar)

    status = Text()
    status.append(" ◆ ", style="bold bright_cyan")

    # Model
    if model:
        truncated = model[:26] + "…" if len(model) > 26 else model
        status.append(truncated, style="bold bright_white")
        status.append("  │  ", style="dim")

    # Token count
    if tokens_max > 0:
        pct = int(tokens_used / tokens_max * 100)
        status.append(f"{tokens_used}/{tokens_max}", style="bright_white")
        status.append(" ", style="dim")

        # Context bar with color thresholds
        bar_filled = int(pct / 100 * 10)
        bar_empty = 10 - bar_filled
        if pct >= 95:
            ctx_color = "bright_red"
        elif pct >= 80:
            ctx_color = "bright_yellow"
        elif pct >= 50:
            ctx_color = "bright_cyan"
        else:
            ctx_color = "bright_green"
        status.append("[", style="dim")
        status.append("█" * bar_filled, style=f"bold {ctx_color}")
        status.append("░" * bar_empty, style="dim")
        status.append("]", style="dim")
        status.append("  │  ", style="dim")

    # Cost
    if cost > 0:
        status.append(f"${cost:.4f}", style="bold bright_yellow")
        status.append("  │  ", style="dim")

    # Duration
    if duration:
        status.append(f"⏱ {duration}", style="bright_white")
        status.append("  │  ", style="dim")

    # Current stage
    if stage:
        emoji = STAGE_EMOJI.get(stage, "▶")
        color = STAGE_COLORS.get(stage, "white")
        status.append(f"{emoji} {stage}", style=f"bold {color}")

    console.print(status)
    console.print("─" * console.width, style="dim bright_cyan")


# ─── Messages ─────────────────────────────────────────────────────────────────


def print_success(message: str) -> None:
    """Print a success message with icon."""
    text = Text()
    text.append("  ✓ ", style="bold bright_green")
    text.append(message, style="bright_white")
    console.print(text)


def print_error(message: str) -> None:
    """Print an error message with icon."""
    text = Text()
    text.append("  ✗ ", style="bold bright_red")
    text.append(message, style="bright_red")
    console.print(text)


def print_warning(message: str) -> None:
    """Print a warning message with icon."""
    text = Text()
    text.append("  ⚠ ", style="bold bright_yellow")
    text.append(message, style="bright_yellow")
    console.print(text)


def print_info(message: str) -> None:
    """Print an info message with icon."""
    text = Text()
    text.append("  ℹ ", style="bold bright_cyan")
    text.append(message, style="bright_cyan")
    console.print(text)


def print_success_banner(message: str, cost: float = 0.0, errors: int = 0) -> None:
    """Print a beautiful success completion banner."""
    content = Text()
    content.append(f"  {message}\n\n", style="bold bright_green")

    if cost > 0:
        content.append("  💰 Cost: ", style="bold bright_white")
        content.append(f"${cost:.4f}\n", style="bold bright_yellow")

    if errors:
        content.append("  ⚠ Errors: ", style="bold bright_white")
        content.append(f"{errors}\n", style="bold bright_red")
    else:
        content.append("  ✓ Status: ", style="bold bright_white")
        content.append("All clear\n", style="bold bright_green")

    console.print(Panel(
        content,
        border_style="bright_green",
        box=box.DOUBLE_EDGE,
        padding=(1, 2),
    ))


def print_error_banner(message: str) -> None:
    """Print a beautiful error banner."""
    content = Text()
    content.append(f"  ✗ {message}\n", style="bold bright_red")
    console.print(Panel(
        content,
        border_style="bright_red",
        box=box.DOUBLE_EDGE,
        padding=(1, 2),
    ))


def print_completed(message: str, cost: float = 0.0, errors: int = 0) -> None:
    """Alias for print_success_banner for backward compat."""
    print_success_banner(message, cost, errors)


# ─── Tables ──────────────────────────────────────────────────────────────────


def _make_base_table(
    title: str,
    title_style: str = "bold bright_cyan",
    border_style: str = "bright_cyan",
    header_style: str = "bold bright_cyan",
) -> Table:
    """Create a base table with consistent styling."""
    return Table(
        title=f"[{title_style}]{title}[/{title_style}]",
        box=box.ROUNDED,
        show_header=True,
        header_style=header_style,
        border_style=border_style,
        padding=(0, 1),
        show_lines=False,
    )


def make_pipeline_table(stages: list[dict]) -> Table:
    """Create a beautiful pipeline status table with progress bars."""
    table = _make_base_table("⚡ Pipeline Status", border_style="bright_blue")

    table.add_column("Stage", style="bold", width=14)
    table.add_column("Status", justify="center", width=12)
    table.add_column("Count", justify="right", width=8)
    table.add_column("Progress", width=24)

    for stage in stages:
        name = stage.get("name", "?")
        status = stage.get("status", "pending")
        count = stage.get("count", 0)

        emoji = STAGE_EMOJI.get(name, "▶")
        color = STAGE_COLORS.get(name, "white")

        badge = make_status_badge(status)

        # Dynamic progress bar based on status
        if status == "ok":
            bar = make_progress_bar(100, 100)
        elif status == "running":
            bar = make_progress_bar(60, 100)
        else:
            bar = make_progress_bar(0, 100)

        table.add_row(
            Text(f"{emoji} {name}", style=color),
            badge,
            str(count),
            bar,
        )

    return table


def make_stats_table(stats: dict) -> Table:
    """Create a beautiful statistics table with gradient bars."""
    table = _make_base_table("📊 Job Statistics", border_style="bright_magenta")

    table.add_column("Metric", style="bold", width=25)
    table.add_column("Count", justify="right", width=10)
    table.add_column("Distribution", width=24)

    max_val = max(stats.get("total", 1), stats.get("scored", 1), 1)

    rows = [
        ("📦 Total jobs", stats.get("total", 0)),
        ("📋 With description", stats.get("with_description", 0)),
        ("⚡ Scored", stats.get("scored", 0)),
        ("✂️ Tailored", stats.get("tailored", 0)),
        ("✉️ Cover letters", stats.get("with_cover_letter", 0)),
        ("✅ Applied", stats.get("applied", 0)),
    ]

    for label, count in rows:
        bar = make_progress_bar(count, max_val, width=20)
        table.add_row(label, str(count), bar)

    return table


def make_cost_table(costs: dict) -> Table:
    """Create an elegant cost breakdown table."""
    table = _make_base_table("💰 Cost Breakdown", border_style="bright_yellow")

    table.add_column("Component", style="bold", width=22)
    table.add_column("Cost", justify="right", width=14)

    total = costs.get("total", 0.0)
    by_tool = costs.get("by_tool", {})

    for tool, cost in by_tool.items():
        table.add_row(tool, Text(f"${cost:.4f}", style="bright_yellow"))

    table.add_section()
    total_text = Text(f"${total:.4f}", style="bold bright_green")
    table.add_row(Text("Total", style="bold bright_white"), total_text)

    return table


def make_plan_table(steps: list[dict]) -> Table:
    """Create an execution plan table with gradient numbering."""
    table = _make_base_table("🗺️ Execution Plan", border_style="bright_cyan")

    table.add_column("#", justify="right", width=4, style="dim")
    table.add_column("Stage", style="bold", width=14)
    table.add_column("Description", width=35)
    table.add_column("Est. Cost", justify="right", width=12)

    for i, step in enumerate(steps, 1):
        name = step.get("tool", "?")
        desc = step.get("description", "")
        cost = step.get("cost_estimate", 0.0)

        stage_key = name.split("_")[0]
        color = STAGE_COLORS.get(stage_key, "white")
        emoji = STAGE_EMOJI.get(stage_key, "▶")

        # Number with gradient color
        num_colors = ["bright_cyan", "cyan", "bright_magenta", "magenta", "bright_yellow", "yellow"]
        num_color = num_colors[(i - 1) % len(num_colors)]

        table.add_row(
            Text(str(i), style=f"bold {num_color}"),
            Text(f"{emoji} {name}", style=color),
            desc,
            Text(f"${cost:.4f}", style="bright_yellow"),
        )

    return table


def make_score_distribution_table(distribution: list[tuple[int, int]]) -> Table:
    """Create a beautiful score distribution table with gradient bars."""
    table = _make_base_table("📈 Score Distribution", border_style="bright_yellow")

    table.add_column("Score", justify="center", width=8)
    table.add_column("Count", justify="right", width=8)
    table.add_column("Distribution", width=30)

    max_count = max((count for _, count in distribution), default=1) or 1

    for score, count in distribution:
        if score >= 7:
            color = "bright_green"
            icon = "🌟"
        elif score >= 5:
            color = "bright_yellow"
            icon = "⭐"
        else:
            color = "bright_red"
            icon = "💔"

        bar = make_progress_bar(count, max_count, width=25)
        table.add_row(
            Text(f"{icon} {score}", style=f"bold {color}"),
            str(count),
            bar,
        )

    return table


def make_site_table(sites: list[tuple[str | None, int]]) -> Table:
    """Create a beautiful jobs-by-source table."""
    table = _make_base_table("🌐 Jobs by Source", border_style="bright_magenta")

    table.add_column("Source", width=25)
    table.add_column("Count", justify="right", width=10)

    for site, count in sites:
        table.add_row(f"🌐 {site or 'Unknown'}", str(count))

    return table


# ─── Reflection Card ─────────────────────────────────────────────────────────


def print_reflection_card(result: dict, ref_id: str) -> None:
    """Print a beautiful reflection card with sections."""
    rating = result.get("overall_rating", "ok")
    rating_map = {
        "good": ("🌟 Excellent", "bright_green"),
        "ok": ("⭐ Average", "bright_yellow"),
        "poor": ("💔 Needs Work", "bright_red"),
    }
    label, color = rating_map.get(rating, ("❓ Unknown", "white"))

    content = Text()
    content.append("  Run: ", style="dim")
    content.append(f"{result.get('run_id', '?')}\n", style="bright_white")

    content.append(f"\n  {label}\n\n", style=f"bold {color}")

    if result.get("what_went_well"):
        content.append("  ✅ What went well\n", style="bold bright_green")
        for item in result["what_went_well"][:3]:
            content.append(f"    {BULLET} {item}\n", style="bright_green")

    if result.get("what_failed"):
        content.append("\n  ❌ What failed\n", style="bold bright_red")
        for item in result["what_failed"][:3]:
            content.append(f"    {BULLET} {item}\n", style="bright_red")

    if result.get("recommendations"):
        content.append("\n  💡 Recommendations\n", style="bold bright_cyan")
        for i, rec in enumerate(result["recommendations"][:3], 1):
            content.append(f"    {i}. {rec}\n", style="bright_cyan")

    border = {"good": "bright_green", "ok": "bright_yellow", "poor": "bright_red"}.get(rating, "white")

    console.print(Panel(
        content,
        title=f"[bold]Reflection[/bold]  [dim]{ref_id}[/dim]",
        border_style=border,
        box=box.ROUNDED,
        padding=(1, 2),
    ))


# ─── Doctor / System Health ──────────────────────────────────────────────────


def make_doctor_table(results: list[tuple[str, str, str, str]]) -> Table:
    """Create a beautiful system health table."""
    table = _make_base_table("🩺 System Health", border_style="bright_cyan")

    table.add_column("Component", style="bold", width=22)
    table.add_column("Status", justify="center", width=10)
    table.add_column("Details", width=40)

    for check, status, emoji, note in results:
        if status == "ok":
            style = "bright_green"
        elif status == "warn":
            style = "bright_yellow"
        else:
            style = "bright_red"

        table.add_row(
            Text(check, style="bold bright_white"),
            Text(f" {emoji} ", style=style),
            Text(note, style="dim"),
        )

    return table


def print_tier_panel(tier: int, labels: dict) -> None:
    """Print a beautiful tier display panel."""
    content = Text()
    content.append(f"\n  Tier {tier}: ", style="bold bright_white")
    content.append(f"{labels[tier]}\n", style="bold bright_cyan")

    hints = {
        1: [
            ("→ Tier 2", "scoring, tailoring", "needs LLM API key"),
            ("→ Tier 3", "auto-apply", "needs Claude CLI + Chrome"),
        ],
        2: [
            ("→ Tier 3", "auto-apply", "needs Claude CLI + Chrome"),
        ],
        3: [],
    }

    for target, feature, reason in hints.get(tier, []):
        content.append(f"\n  {target}: ", style="dim bright_white")
        content.append(f"{feature}", style="dim")
        content.append(f"  ({reason})", style="dim")

    if tier == 3:
        content.append("\n\n  ✓ All tiers unlocked!", style="bold bright_green")

    content.append("\n")
    console.print(Panel(
        content,
        border_style="bright_cyan",
        box=box.ROUNDED,
        padding=(0, 1),
    ))


# ─── Utility ─────────────────────────────────────────────────────────────────


def clear_line() -> None:
    """Clear the current terminal line."""
    console.print("\r" + " " * console.width + "\r", end="")
