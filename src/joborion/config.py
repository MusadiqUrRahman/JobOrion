"""JobOrion configuration: paths, platform detection, user data."""

import os
import platform
import re
import shutil
import sys
from pathlib import Path

# User data directory — all user-specific files live here
APP_DIR = Path(os.environ.get("JOBORION_DIR", Path.home() / ".joborion"))

# Core paths
DB_PATH = APP_DIR / "joborion.db"
PROFILE_PATH = APP_DIR / "profile.json"
RESUME_PATH = APP_DIR / "resume.txt"
RESUME_PDF_PATH = APP_DIR / "resume.pdf"
SEARCH_CONFIG_PATH = APP_DIR / "searches.yaml"
PREFERENCES_PATH = APP_DIR / "preferences.yaml"
ENV_PATH = APP_DIR / ".env"

# Generated output
TAILORED_DIR = APP_DIR / "tailored_resumes"
COVER_LETTER_DIR = APP_DIR / "cover_letters"
LOG_DIR = APP_DIR / "logs"

# Chrome worker isolation
CHROME_WORKER_DIR = APP_DIR / "chrome-workers"
APPLY_WORKER_DIR = APP_DIR / "apply-workers"

# Package-shipped config (YAML registries)
PACKAGE_DIR = Path(__file__).parent
CONFIG_DIR = PACKAGE_DIR / "config"

# ---------------------------------------------------------------------------
# Profiles — isolated workspaces under APP_DIR/profiles/<name>
# ---------------------------------------------------------------------------

_ACTIVE_PROFILE: str | None = None
_PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,63})$")


def get_profile() -> str | None:
    """Return the active profile name, or None for the default workspace."""
    return _ACTIVE_PROFILE


def get_profile_dir() -> Path:
    """Base directory for the active profile; APP_DIR when no profile is set."""
    if _ACTIVE_PROFILE:
        return APP_DIR / "profiles" / _ACTIVE_PROFILE
    return APP_DIR


def list_profiles() -> list[str]:
    """Sorted profile names, always including the implicit default."""
    profiles_dir = APP_DIR / "profiles"
    if not profiles_dir.exists():
        return ["default"]
    names = sorted(p.name for p in profiles_dir.iterdir() if p.is_dir())
    return ["default", *names]


def _rebind_profile_paths() -> None:
    """Point every path constant at the active profile's directory."""
    global DB_PATH, PROFILE_PATH, RESUME_PATH, RESUME_PDF_PATH
    global SEARCH_CONFIG_PATH, PREFERENCES_PATH, ENV_PATH, TAILORED_DIR
    global COVER_LETTER_DIR, LOG_DIR, CHROME_WORKER_DIR, APPLY_WORKER_DIR
    base = get_profile_dir()
    DB_PATH = base / "joborion.db"
    PROFILE_PATH = base / "profile.json"
    RESUME_PATH = base / "resume.txt"
    RESUME_PDF_PATH = base / "resume.pdf"
    SEARCH_CONFIG_PATH = base / "searches.yaml"
    PREFERENCES_PATH = base / "preferences.yaml"
    ENV_PATH = base / ".env"
    TAILORED_DIR = base / "tailored_resumes"
    COVER_LETTER_DIR = base / "cover_letters"
    LOG_DIR = base / "logs"
    CHROME_WORKER_DIR = base / "chrome-workers"
    APPLY_WORKER_DIR = base / "apply-workers"


def set_profile(name: str | None) -> None:
    """Activate an isolated workspace; None resets to the default.

    Raises ValueError for empty or unsafe names. Rebinding only happens when
    the profile actually changes, so pre-applied module-level path patches
    (used by tests) survive a no-op call.
    """
    global _ACTIVE_PROFILE
    if name is None:
        name = None
    if name == _ACTIVE_PROFILE:
        return
    if name is not None and (not name or not _PROFILE_NAME_RE.match(name) or name in (".", "..")):
        raise ValueError(
            "Profile names must be 1-64 chars: letters, digits, '.', '_', '-'."
        )
    _ACTIVE_PROFILE = name
    _rebind_profile_paths()
    _sync_imported_modules()


def reset_profile() -> None:
    """Force-reset to the default workspace, always rebinding paths."""
    global _ACTIVE_PROFILE
    _ACTIVE_PROFILE = None
    _rebind_profile_paths()
    _sync_imported_modules()


# Consumer modules that capture path constants at import time; when they are
# already loaded, keep their module-level names in sync so call-time reads
# reflect the active profile regardless of import order.
_PROFILE_SYNC_MODULES: dict[str, tuple[str, ...]] = {
    "joborion.database": ("DB_PATH",),
    "joborion.scoring.resume_tailor": ("RESUME_PATH", "TAILORED_DIR"),
    "joborion.scoring.fit_scorer": ("RESUME_PATH",),
    "joborion.scoring.document_converter": ("TAILORED_DIR",),
    "joborion.scoring.cover_writer": ("COVER_LETTER_DIR", "RESUME_PATH"),
    "joborion.wizard.init": (
        "ENV_PATH", "PROFILE_PATH", "RESUME_PATH", "RESUME_PDF_PATH",
        "SEARCH_CONFIG_PATH",
    ),
}


def _sync_imported_modules() -> None:
    """Push the rebound path constants into already-imported consumer modules."""
    for module_name, attrs in _PROFILE_SYNC_MODULES.items():
        module = sys.modules.get(module_name)
        if module is None:
            continue
        for attr in attrs:
            try:
                setattr(module, attr, globals()[attr])
            except KeyError:
                continue


def get_chrome_path() -> str:
    """Auto-detect Chrome/Chromium executable path, cross-platform.

    Override with CHROME_PATH environment variable.
    """
    env_path = os.environ.get("CHROME_PATH")
    if env_path and Path(env_path).exists():
        return env_path

    system = platform.system()

    if system == "Windows":
        candidates = [
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
        ]
    elif system == "Darwin":
        candidates = [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        ]
    else:  # Linux
        candidates = []
        for name in ("google-chrome", "google-chrome-stable", "chromium-browser", "chromium"):
            found = shutil.which(name)
            if found:
                candidates.append(Path(found))

    for c in candidates:
        if c and c.exists():
            return str(c)

    # Fall back to PATH search
    for name in ("google-chrome", "google-chrome-stable", "chromium-browser", "chromium", "chrome"):
        found = shutil.which(name)
        if found:
            return found

    raise FileNotFoundError(
        "Chrome/Chromium not found. Install Chrome or set CHROME_PATH environment variable."
    )


def get_chrome_user_data() -> Path:
    """Default Chrome user data directory, cross-platform."""
    system = platform.system()
    if system == "Windows":
        return Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"
    elif system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
    else:
        return Path.home() / ".config" / "google-chrome"


def ensure_dirs():
    """Create all required directories."""
    for d in [APP_DIR, TAILORED_DIR, COVER_LETTER_DIR, LOG_DIR, CHROME_WORKER_DIR, APPLY_WORKER_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def load_profile() -> dict:
    """Load user profile from ~/.joborion/profile.json."""
    import json
    if not PROFILE_PATH.exists():
        raise FileNotFoundError(
            f"Profile not found at {PROFILE_PATH}. Run `joborion init` first."
        )
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def load_search_config() -> dict:
    """Load search configuration from ~/.joborion/searches.yaml."""
    import yaml
    if not SEARCH_CONFIG_PATH.exists():
        # Fall back to package-shipped example
        example = CONFIG_DIR / "searches.example.yaml"
        if example.exists():
            return yaml.safe_load(example.read_text(encoding="utf-8"))
        return {}
    return yaml.safe_load(SEARCH_CONFIG_PATH.read_text(encoding="utf-8"))


def load_sites_config() -> dict:
    """Load sites.yaml configuration (sites list, manual_ats, blocked, etc.)."""
    import yaml
    path = CONFIG_DIR / "sites.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def is_manual_ats(url: str | None) -> bool:
    """Check if a URL routes through an ATS that requires manual application."""
    if not url:
        return False
    sites_cfg = load_sites_config()
    domains = sites_cfg.get("manual_ats", [])
    url_lower = url.lower()
    return any(domain in url_lower for domain in domains)


def load_blocked_sites() -> tuple[set[str], list[str]]:
    """Load blocked sites and URL patterns from sites.yaml.

    Returns:
        (blocked_site_names, blocked_url_patterns)
    """
    cfg = load_sites_config()
    blocked = cfg.get("blocked", {})
    sites = set(blocked.get("sites", []))
    patterns = blocked.get("url_patterns", [])
    return sites, patterns


def load_blocked_sso() -> list[str]:
    """Load blocked SSO domains from sites.yaml."""
    cfg = load_sites_config()
    return cfg.get("blocked_sso", [])


def load_base_urls() -> dict[str, str | None]:
    """Load site base URLs for URL resolution from sites.yaml."""
    cfg = load_sites_config()
    return cfg.get("base_urls", {})


# ---------------------------------------------------------------------------
# Default values — referenced across modules instead of magic numbers
# ---------------------------------------------------------------------------

DEFAULTS = {
    "min_score": 7,
    "max_apply_attempts": 3,
    "max_tailor_attempts": 5,
    "poll_interval": 60,
    "apply_timeout": 300,
    "viewport": "1280x900",
}


def load_env():
    """Load environment variables from ~/.joborion/.env if it exists."""
    from dotenv import load_dotenv
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH)
    # Also try CWD .env as fallback
    load_dotenv()


# ---------------------------------------------------------------------------
# Tier system — feature gating by installed dependencies
# ---------------------------------------------------------------------------

TIER_LABELS = {
    1: "Discovery",
    2: "AI Scoring & Tailoring",
    3: "Full Auto-Apply",
}

TIER_COMMANDS: dict[int, list[str]] = {
    1: ["init", "run search", "run details", "status", "dashboard"],
    2: ["run evaluate", "run tailor", "run letter", "run export", "run"],
    3: ["apply"],
}


def get_tier() -> int:
    """Detect the current tier based on available dependencies.

    Tier 1 (Discovery):            Python + pip
    Tier 2 (AI Scoring & Tailoring): + LLM API key
    Tier 3 (Full Auto-Apply):       + Claude Code CLI + Chrome
    """
    load_env()

    from joborion.llm import _detect_providers
    has_llm = bool(_detect_providers())
    if not has_llm:
        return 1

    has_claude = shutil.which("claude") is not None
    try:
        get_chrome_path()
        has_chrome = True
    except FileNotFoundError:
        has_chrome = False

    if has_claude and has_chrome:
        return 3

    return 2


def check_tier(required: int, feature: str) -> None:
    """Raise SystemExit with a clear message if the current tier is too low.

    Args:
        required: Minimum tier needed (1, 2, or 3).
        feature: Human-readable description of the feature being gated.
    """
    current = get_tier()
    if current >= required:
        return

    from rich.console import Console
    _console = Console(stderr=True)

    missing: list[str] = []
    from joborion.llm import _detect_providers
    if required >= 2 and not _detect_providers():
        missing.append("LLM API key — run [bold]joborion init[/bold] or set GEMINI_API_KEY")
    if required >= 3:
        if not shutil.which("claude"):
            missing.append("Claude Code CLI — install from [bold]https://claude.ai/code[/bold]")
        try:
            get_chrome_path()
        except FileNotFoundError:
            missing.append("Chrome/Chromium — install or set CHROME_PATH")

    _console.print(
        f"\n[red]'{feature}' requires {TIER_LABELS.get(required, f'Tier {required}')} (Tier {required}).[/red]\n"
        f"Current tier: {TIER_LABELS.get(current, f'Tier {current}')} (Tier {current})."
    )
    if missing:
        _console.print("\n[yellow]Missing:[/yellow]")
        for m in missing:
            _console.print(f"  - {m}")
    _console.print()
    raise SystemExit(1)
