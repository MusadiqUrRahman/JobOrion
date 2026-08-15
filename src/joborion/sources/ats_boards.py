"""ATS boards provider: Greenhouse, Lever, Ashby, SmartRecruiters public feeds.

Each ATS exposes a public JSON job feed. Company -> platform mappings live in
config/companies.yaml; fetch and parse are separated so parsing is testable
with realistic payloads and the network layer can be patched out.
"""

from __future__ import annotations

import logging
import re

import httpx
import yaml

from joborion import config
from joborion.database import get_connection
from joborion.sources.base import ProviderResult, RawJob, proxy_http_url, resolve_proxy, store_raw_jobs
from joborion.sourcing.learning import note_company_run, pruned_companies
from joborion.wizard.preferences import load_preferences

log = logging.getLogger(__name__)

_HTML_TAG = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    return _HTML_TAG.sub("", text or "")


def load_companies() -> dict:
    """Load the companies.yaml registry. Returns {} if missing or unreadable."""
    path = config.CONFIG_DIR / "companies.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    companies = data.get("companies", {})
    return companies if isinstance(companies, dict) else {}


def parse_greenhouse(slug: str, company_name: str, payload: dict) -> list[RawJob]:
    jobs: list[RawJob] = []
    for posting in payload.get("jobs", []):
        location = posting.get("location") or {}
        if isinstance(location, dict):
            location = location.get("name", "")
        url = posting.get("absolute_url", "")
        jobs.append(
            RawJob(
                title=posting.get("title", ""),
                company=posting.get("company_name") or company_name or slug,
                location=location,
                url=url,
                apply_url=url,
                posted_at=posting.get("updated_at", ""),
                source="ats_boards",
                site=f"greenhouse-{slug}",
            )
        )
    return jobs


def parse_lever(slug: str, payload: list) -> list[RawJob]:
    jobs: list[RawJob] = []
    for posting in payload:
        categories = posting.get("categories") or {}
        all_locations = categories.get("allLocations") or []
        location = ", ".join(str(x) for x in all_locations) or categories.get("location", "")
        description = posting.get("descriptionPlain")
        if not description:
            description = _strip_html(posting.get("description", ""))
        url = posting.get("hostedUrl", "")
        jobs.append(
            RawJob(
                title=posting.get("text", ""),
                company=slug,
                location=location,
                description=description,
                url=url,
                apply_url=posting.get("applyUrl") or url,
                job_type=categories.get("commitment", ""),
                posted_at=posting.get("createdAt", ""),
                source="ats_boards",
                site=f"lever-{slug}",
            )
        )
    return jobs


def parse_ashby(org: str, payload: dict) -> list[RawJob]:
    jobs: list[RawJob] = []
    for posting in payload.get("jobs", []):
        location = posting.get("location", "")
        secondary = posting.get("secondaryLocations") or []
        locations = ", ".join(str(x) for x in [location, *secondary] if x)
        url = posting.get("jobUrl", "")
        jobs.append(
            RawJob(
                title=posting.get("title", ""),
                company=org,
                location=locations,
                description=posting.get("descriptionPlain", ""),
                url=url,
                apply_url=posting.get("applyUrl") or url,
                job_type=posting.get("employmentType", ""),
                seniority=posting.get("seniority", ""),
                is_remote=posting.get("isRemote"),
                posted_at=posting.get("publishedAt", ""),
                source="ats_boards",
                site=f"ashby-{org}",
            )
        )
    return jobs


def parse_smartrecruiters(payload: dict) -> list[RawJob]:
    jobs: list[RawJob] = []
    for posting in payload.get("content", []):
        company = posting.get("companyName") or (posting.get("company") or {}).get("name", "")
        location_data = posting.get("location") or {}
        location = location_data.get("fullLocation", "")
        if not location:
            location = ", ".join(x for x in [location_data.get("city", ""), location_data.get("country", "")] if x)
        url = posting.get("jobUrl", "")
        if not url:
            identifier = (posting.get("company") or {}).get("identifier", "")
            ref = posting.get("ref", "")
            if identifier and ref:
                url = f"https://jobs.smartrecruiters.com/{identifier}/{ref}"
        experience = posting.get("experienceLevel") or {}
        jobs.append(
            RawJob(
                title=posting.get("name", ""),
                company=company,
                location=location,
                url=url,
                apply_url=url,
                job_type=posting.get("jobType") or (posting.get("typeOfEmployment") or {}).get("label", ""),
                seniority=experience.get("label", ""),
                posted_at=posting.get("releasedDate", ""),
                source="ats_boards",
                site="smartrecruiters",
            )
        )
    return jobs


def _fetch_greenhouse(slug: str, params: dict | None = None, proxy: str | None = None) -> dict:
    resp = httpx.get(
        f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
        params=params or {},
        timeout=15,
        follow_redirects=True,
        proxy=proxy,
    )
    resp.raise_for_status()
    return resp.json()


def _fetch_lever(slug: str, params: dict | None = None, proxy: str | None = None) -> list:
    resp = httpx.get(
        f"https://api.lever.co/v0/postings/{slug}",
        params=params or {"mode": "json"},
        timeout=15,
        follow_redirects=True,
        proxy=proxy,
    )
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


def _fetch_ashby(org: str, params: dict | None = None, proxy: str | None = None) -> dict:
    resp = httpx.get(
        f"https://api.ashbyhq.com/posting-api/job-board/{org}",
        params=params or {},
        timeout=15,
        follow_redirects=True,
        proxy=proxy,
    )
    resp.raise_for_status()
    return resp.json()


def _fetch_smartrecruiters(slug: str, params: dict | None = None, proxy: str | None = None) -> dict:
    resp = httpx.get(
        f"https://api.smartrecruiters.com/v1/companies/{slug}/postings",
        params=params or {"limit": 100},
        timeout=15,
        follow_redirects=True,
        proxy=proxy,
    )
    resp.raise_for_status()
    return resp.json()


_PLATFORMS = ("greenhouse", "lever", "ashby", "smartrecruiters")


def _fetch(platform: str, slug: str, params: dict | None, proxy: str | None = None) -> object:
    # Call-time dispatch so tests can monkeypatch individual _fetch_* functions.
    if platform == "greenhouse":
        return _fetch_greenhouse(slug, params, proxy)
    if platform == "lever":
        return _fetch_lever(slug, params, proxy)
    if platform == "ashby":
        return _fetch_ashby(slug, params, proxy)
    if platform == "smartrecruiters":
        return _fetch_smartrecruiters(slug, params, proxy)
    raise ValueError(f"unknown platform: {platform}")


def _parse(platform: str, company: dict, payload: object) -> list[RawJob]:
    if platform == "greenhouse":
        return parse_greenhouse(company["slug"], company.get("name", ""), payload)
    if platform == "lever":
        return parse_lever(company["slug"], payload)
    if platform == "ashby":
        return parse_ashby(company["slug"], payload)
    if platform == "smartrecruiters":
        return parse_smartrecruiters(payload)
    raise ValueError(f"unknown platform: {platform}")


def _int_cfg(cfg: dict, key: str, default: int) -> int:
    try:
        return int(cfg.get(key, default))
    except (TypeError, ValueError):
        return default


class AtsBoardsProvider:
    """Search curated ATS boards for jobs matching a search intent."""

    name = "ats_boards"

    def __init__(self, cfg: dict):
        self.cfg = cfg or {}

    def _select_companies(self, intent: dict, pruned: set[str] | None = None) -> list[dict]:
        companies = load_companies()
        prefs = load_preferences()
        industries = [ind.lower() for ind in (prefs.get("industries") or [])]
        sponsorship_ok = prefs.get("sponsorship_ok", True)
        locations = [loc.lower() for loc in (intent.get("locations") or [])]
        filter_locations = bool(locations and "worldwide" not in locations)
        max_companies = _int_cfg(self.cfg, "max_companies", 15)
        pruned = pruned or set()

        def keep(company: dict) -> bool:
            if (company.get("name") or company.get("slug")) in pruned:
                return False
            if industries:
                company_industries = {str(i).lower() for i in company.get("industries", [])}
                if not company_industries.intersection(industries):
                    return False
            tags = {str(t).lower() for t in company.get("tags", [])}
            if not sponsorship_ok and "sponsorship" in tags:
                return False
            if filter_locations:
                region = (company.get("region") or "").lower()
                if region != "global" and region not in locations:
                    return False
            return True

        wanted = set(industries)
        candidates = [c for c in companies.values() if isinstance(c, dict) and keep(c)]
        if wanted:
            # Rank companies that match more of the user's industries first so
            # max_companies is not filled by peripheral matches (stable sort
            # preserves registry order among equal overlap counts).
            candidates.sort(
                key=lambda c: len(wanted & {str(i).lower() for i in c.get("industries", [])}),
                reverse=True,
            )
        return candidates[:max_companies]

    def search(self, intent: dict) -> ProviderResult:
        max_per_company = _int_cfg(self.cfg, "max_per_company", 50)
        max_results = _int_cfg(self.cfg, "max_results", 300)

        try:
            conn = get_connection()
            companies = self._select_companies(intent, pruned=pruned_companies(conn, self.name))
        except Exception as exc:
            log.error("ats_boards: company selection failed: %s", exc)
            return ProviderResult(provider=self.name, errors=1, error=str(exc))

        jobs: list[RawJob] = []
        attempted: list[str] = []
        errors = 0
        limiter = (intent or {}).get("rate_limiter")
        for company in companies:
            platform = company.get("platform")
            slug = company.get("slug")
            company_key = company.get("name") or slug
            attempted.append(company_key)
            if platform not in _PLATFORMS or not slug:
                errors += 1
                note_company_run(conn, self.name, company_key)
                continue
            try:
                if limiter is not None:
                    limiter.wait()
                payload = _fetch(platform, slug, None, proxy_http_url(resolve_proxy(self.cfg)))
                parsed = _parse(platform, company, payload)
            except Exception as exc:
                errors += 1
                log.warning("ats_boards: %s board %r failed: %s", platform, slug, exc)
                note_company_run(conn, self.name, company_key)
                continue
            note_company_run(conn, self.name, company_key, found=len(parsed))
            jobs.extend(parsed[:max_per_company])
            if len(jobs) >= max_results:
                jobs = jobs[:max_results]
                break

        try:
            new, _existing = store_raw_jobs(conn, jobs, provider=self.name)
        except Exception as exc:
            log.error("ats_boards: storing jobs failed: %s", exc)
            return ProviderResult(provider=self.name, found=len(jobs), stored=0, errors=errors + 1, error=str(exc))

        return ProviderResult(
            provider=self.name, found=len(jobs), stored=new, errors=errors,
            companies=attempted,
        )
