"""Source registry: load config/sources.yaml, build enabled providers in order.

Providers are pure wrappers -- they never reach into the registry and the
registry never hardcodes provider logic. New providers register themselves in
_PROVIDER_CLASSES and get picked up automatically.
"""

from __future__ import annotations

import logging
from pathlib import Path
from time import perf_counter

import yaml

from joborion import config
from joborion.sources.base import JobProvider, ProviderResult

log = logging.getLogger(__name__)

# Provider name -> (module path, class name). Kept as strings so imports are
# lazy: a missing provider module is skipped, not fatal.
_PROVIDER_CLASSES: dict[str, tuple[str, str]] = {
    "jobspy": ("joborion.sources.jobspy_provider", "JobSpyProvider"),
    "workday": ("joborion.sources.workday_provider", "WorkdayProvider"),
    "adzuna": ("joborion.sources.adzuna_provider", "AdzunaProvider"),
    "remote_boards": ("joborion.sources.remote_boards", "RemoteBoardsProvider"),
    "ats_boards": ("joborion.sources.ats_boards", "AtsBoardsProvider"),
    "ai_sites": ("joborion.sources.ai_site_provider", "AiSiteProvider"),
}


def load_sources_config(path: Path | str | None = None) -> dict:
    """Load the source registry YAML. Returns {} if missing or invalid."""
    cfg_path = Path(path) if path else config.CONFIG_DIR / "sources.yaml"
    try:
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except OSError:
        log.warning("sources.yaml not found at %s", cfg_path)
        return {}
    providers = data.get("providers", {})
    if not isinstance(providers, dict):
        log.warning("sources.yaml has no valid 'providers' mapping")
        return {"providers": {}}
    return data


def enabled_providers(cfg: dict | None = None) -> list[dict]:
    """Return enabled provider specs, ordered by ascending priority.

    Each item is {"name", "cfg", "priority"} where cfg is that provider's own
    options dict from sources.yaml.
    """
    data = cfg if cfg is not None else load_sources_config()
    specs = []
    for name, options in (data.get("providers") or {}).items():
        if not isinstance(options, dict):
            continue
        if not options.get("enabled", False):
            continue
        specs.append({"name": name, "cfg": options, "priority": options.get("priority", 100)})
    return sorted(specs, key=lambda s: s["priority"])


def _import_provider_class(name: str) -> type[JobProvider] | None:
    """Import and return the provider class for a name, or None if unknown."""
    entry = _PROVIDER_CLASSES.get(name)
    if entry is None:
        log.warning("No provider class registered for %r", name)
        return None
    module_path, class_name = entry
    try:
        module = __import__(module_path, fromlist=[class_name])
        return getattr(module, class_name)
    except (ImportError, AttributeError) as e:
        log.warning("Could not load provider %r (%s): %s", name, module_path, e)
        return None


def build_providers(cfg: dict | None = None) -> list[JobProvider]:
    """Instantiate one provider per enabled entry, in priority order."""
    providers: list[JobProvider] = []
    for spec in enabled_providers(cfg):
        cls = _import_provider_class(spec["name"])
        if cls is None:
            continue
        try:
            providers.append(cls(spec["cfg"]))
        except Exception as e:  # provider ctor failures should not kill the run
            log.error("Provider %r failed to initialize: %s", spec["name"], e)
    return providers


def run_providers(
    intent: dict,
    providers: list[JobProvider] | None = None,
) -> list[ProviderResult]:
    """Run each provider once against the intent, collecting results.

    Never raises: provider exceptions become ProviderResult entries with
    errors > 0. Results are returned in the order providers ran.
    """
    if providers is None:
        providers = build_providers()

    results: list[ProviderResult] = []
    for provider in providers:
        name = getattr(provider, "name", "unknown")
        start = perf_counter()
        try:
            result = provider.search(intent)
            if not isinstance(result, ProviderResult):
                result = ProviderResult(provider=name)
        except Exception as e:
            log.error("Provider %r raised during search: %s", name, e)
            result = ProviderResult(provider=name, errors=1, error=str(e))
        result.latency_ms = int((perf_counter() - start) * 1000)
        results.append(result)
    return results
