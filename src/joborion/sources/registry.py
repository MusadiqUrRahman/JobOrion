"""Source registry: load config/sources.yaml, build enabled providers in order.

Providers are pure wrappers -- they never reach into the registry and the
registry never hardcodes provider logic. New providers register themselves in
_PROVIDER_CLASSES and get picked up automatically.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

import yaml

from joborion import config
from joborion.llm import estimate_call_cost
from joborion.sources.base import JobProvider, ProviderResult

log = logging.getLogger(__name__)

# Per-job LLM cost model used only for pre-flight estimates: an LLM-heavy
# source (ai_sites) is assumed to spend a small prompt+completion per job.
LLM_JOB_TOKENS_IN = 3000
LLM_JOB_TOKENS_OUT = 300
DEFAULT_EST_JOBS = 10

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


def compute_result_caps(
    providers: list[JobProvider],
    intent: dict | None = None,
) -> dict[str, int]:
    """Per-provider result caps (0 = unlimited).

    A provider's own ``max_results`` config wins; otherwise the run-wide
    ``intent["max_results"]`` applies. Cap enforcement lives in run_providers.
    """
    intent = intent or {}
    global_cap = int(intent.get("max_results") or 0)
    caps: dict[str, int] = {}
    for provider in providers:
        name = getattr(provider, "name", "unknown")
        own = int(getattr(provider, "cfg", {}).get("max_results") or 0)
        caps[name] = own or global_cap
    return caps


def preflight_estimate(
    providers: list[JobProvider],
    intent: dict | None = None,
    caps: dict[str, int] | None = None,
) -> dict:
    """Estimate total jobs and USD cost before running providers.

    Free providers (HTML/JSON scraping) cost nothing. Providers flagged
    ``uses_llm`` are priced with estimate_call_cost per expected job so the
    run's budget can be checked pre-flight. Returns per-provider detail plus
    run totals.
    """
    caps = caps if caps is not None else compute_result_caps(providers, intent)
    per_job_cost = estimate_call_cost(LLM_JOB_TOKENS_IN, LLM_JOB_TOKENS_OUT)
    per_provider: dict = {}
    total_jobs = 0
    total_cost = 0.0

    for provider in providers:
        name = getattr(provider, "name", "unknown")
        cfg = getattr(provider, "cfg", {}) or {}
        cap = caps.get(name, 0)
        est_jobs = cap or int(cfg.get("est_jobs_per_run") or DEFAULT_EST_JOBS)
        uses_llm = bool(getattr(provider, "uses_llm", False))
        est_cost = round(est_jobs * per_job_cost, 4) if uses_llm else 0.0
        per_provider[name] = {
            "cap": cap,
            "estimated_jobs": est_jobs,
            "estimated_cost_usd": est_cost,
        }
        total_jobs += est_jobs
        total_cost += est_cost

    return {
        "per_provider": per_provider,
        "estimated_total_jobs": total_jobs,
        "estimated_cost_usd": round(total_cost, 4),
    }


def _trim_provider_to_cap(
    conn,
    name: str,
    cap: int,
    run_start: str,
) -> int:
    """Delete this run's excess jobs for a provider, keeping the newest ``cap``."""
    if cap <= 0:
        return 0
    rows = conn.execute(
        "SELECT url FROM jobs WHERE source_provider = ? AND discovered_at >= ? "
        "ORDER BY discovered_at DESC",
        (name, run_start),
    ).fetchall()
    if len(rows) <= cap:
        return 0
    excess = [row["url"] for row in rows[cap:]]
    conn.executemany("DELETE FROM jobs WHERE url = ?", [(u,) for u in excess])
    conn.commit()
    return len(excess)


def run_providers(
    intent: dict,
    providers: list[JobProvider] | None = None,
    conn=None,
    caps: dict[str, int] | None = None,
) -> list[ProviderResult]:
    """Run each provider once against the intent, collecting results.

    Never raises: provider exceptions become ProviderResult entries with
    errors > 0. Results are returned in the order providers ran.

    When ``conn`` is given, per-provider result caps (see
    compute_result_caps) are enforced by trimming excess stored jobs after
    each run; the trimmed count is reported on the result.
    """
    if providers is None:
        providers = build_providers()
    if conn is not None and caps is None:
        caps = compute_result_caps(providers, intent)
    run_start = datetime.now(timezone.utc).isoformat()

    results: list[ProviderResult] = []
    for provider in providers:
        name = getattr(provider, "name", "unknown")
        start = perf_counter()
        provider_intent = intent
        cap = (caps or {}).get(name, 0)
        if cap:
            limits = dict(intent.get("provider_limits") or {})
            limits[name] = cap
            provider_intent = {**intent, "provider_limits": limits}
        try:
            result = provider.search(provider_intent)
            if not isinstance(result, ProviderResult):
                result = ProviderResult(provider=name)
        except Exception as e:
            log.error("Provider %r raised during search: %s", name, e)
            result = ProviderResult(provider=name, errors=1, error=str(e))
        if conn is not None and cap and result.ok():
            result.trimmed = _trim_provider_to_cap(conn, name, cap, run_start)
        result.latency_ms = int((perf_counter() - start) * 1000)
        results.append(result)
    return results
