"""Adzuna provider: searches the Adzuna Jobs API as a JobProvider.

Adzuna returns country-scoped endpoints and HTML descriptions, so results are
stripped and normalized here before going through the shared store_raw_jobs
insert path. Credentials are read from environment variables (loaded from
~/.joborion/.env) named by the source config.
"""

from __future__ import annotations

import html
import logging
import os
import re

import httpx

from joborion.config import load_env, load_search_config
from joborion.database import get_connection
from joborion.sources.base import ProviderResult, RawJob, store_raw_jobs

log = logging.getLogger(__name__)

ADZUNA_BASE = "https://api.adzuna.com/v1/api/jobs"


class NetworkError(Exception):
    """Raised when the Adzuna API is unreachable or answers with an error."""


def _strip_html(html_text: str) -> str:
    text = re.sub(r"<[^>]+>", "", html_text)
    return html.unescape(text).strip()


def _fetch(url: str, params: dict) -> dict:
    """GET the Adzuna API and return the parsed JSON body."""
    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            response = client.get(url, params=params)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError as exc:
        raise NetworkError(str(exc)) from exc


def _to_raw_job(result: dict, cfg: dict) -> RawJob:
    redirect_url = result.get("redirect_url", "")
    return RawJob(
        title=result.get("title", ""),
        company=(result.get("company") or {}).get("display_name", ""),
        location=(result.get("location") or {}).get("display_name", ""),
        description=_strip_html(result.get("description") or ""),
        url=redirect_url,
        apply_url=redirect_url,
        salary_min=result.get("salary_min"),
        salary_max=result.get("salary_max"),
        salary_currency=cfg.get("currency") or "USD",
        salary_interval="year",
        job_type=result.get("contract_type", ""),
        source="adzuna",
        site="adzuna",
        posted_at=result.get("created", ""),
    )


class AdzunaProvider:
    """Search the Adzuna jobs API across configured countries and queries."""

    name = "adzuna"

    def __init__(self, cfg: dict):
        self.cfg = cfg or {}

    def search(self, intent: dict) -> ProviderResult:
        try:
            return self._search(intent)
        except Exception as exc:
            log.warning("Adzuna search failed: %s", exc)
            return ProviderResult(provider=self.name, errors=1, error=str(exc))

    def _search(self, intent: dict) -> ProviderResult:
        load_env()
        app_id_env = self.cfg.get("app_id_env", "ADZUNA_APP_ID")
        app_key_env = self.cfg.get("app_key_env", "ADZUNA_APP_KEY")
        app_id = os.environ.get(app_id_env, "")
        app_key = os.environ.get(app_key_env, "")
        if not app_id or not app_key:
            log.warning("Adzuna skipped: %s or %s not set", app_id_env, app_key_env)
            return ProviderResult(provider=self.name, errors=0, found=0)

        queries = (load_search_config() or {}).get("queries", [])
        if not queries:
            return ProviderResult(provider=self.name)
        tier1 = [q["query"] for q in queries if q.get("tier") == 1]
        tier2 = [q["query"] for q in queries if q.get("tier") == 2]
        terms = (tier1 + tier2)[: int(self.cfg.get("max_queries", 3))]
        if not terms:
            return ProviderResult(provider=self.name)

        intent = intent or {}
        locations = intent.get("locations") or ["worldwide"]
        job_types = intent.get("job_types") or []
        min_salary = intent.get("min_salary")

        countries = self.cfg.get("countries") or ["gb"]
        results_per_query = int(self.cfg.get("results_per_query", 50))
        max_results = int(self.cfg.get("max_results", 150))

        jobs: list[RawJob] = []
        seen_urls: set[str] = set()
        location0 = locations[0] if locations[0] != "worldwide" else None

        for country in countries:
            for term in terms:
                if len(jobs) >= max_results:
                    break
                params: dict = {
                    "app_id": app_id,
                    "app_key": app_key,
                    "what": term,
                    "results_per_page": results_per_query,
                    "content-type": "application/json",
                    "max_days_old": 30,
                }
                if location0:
                    params["location0"] = location0
                if "fulltime" in job_types:
                    params["full_time"] = "1"
                if min_salary:
                    params["salary_min"] = min_salary

                url = f"{ADZUNA_BASE}/{country}/search/1"
                data = _fetch(url, params)
                for result in data.get("results") or []:
                    if len(jobs) >= max_results:
                        break
                    job = _to_raw_job(result, self.cfg)
                    if job.url and job.url not in seen_urls:
                        seen_urls.add(job.url)
                        jobs.append(job)

        if not jobs:
            return ProviderResult(provider=self.name)

        new, _existing = store_raw_jobs(get_connection(), jobs, provider=self.name)
        return ProviderResult(provider=self.name, found=len(jobs), stored=new, errors=0)
