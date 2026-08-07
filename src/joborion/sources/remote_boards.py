"""Remote-board provider: Remotive, RemoteOK, WeWorkRemotely, Jobicy, Arbeitnow, Working Nomads, Hacker News.

Each board is exposed as a pure parse_* function (JSON payload -> list[RawJob])
paired with a _fetch_* function (httpx -> raw JSON items) so parsing logic can
be tested without network access.
"""

from __future__ import annotations

import html
import logging
import re
from html.parser import HTMLParser

import httpx

from joborion.config import load_search_config
from joborion.database import get_connection
from joborion.sources.base import ProviderResult, RawJob, proxy_http_url, resolve_proxy, store_raw_jobs

log = logging.getLogger(__name__)

_REMOTIVE_URL = "https://remotive.com/api/remote-jobs"
_REMOTE_OK_URL = "https://remoteok.com/api"
_WWR_URL = "https://weworkremotely.com/categories/remote-full-time-jobs.json"
_JOBICY_URL = "https://jobicy.com/api/v2/remote-jobs"
_ARBEITNOW_URL = "https://www.arbeitnow.com/api/job-board-api"
_WORKING_NOMADS_URL = "https://www.workingnomads.com/api/exposed_jobs"
_ALGOLIA_BASE = "https://hn.algolia.com/api/v1"

_REMOTIVE_LIMIT = 50
_JOBICY_COUNT = 50
_HTTP_TIMEOUT = 30
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

_SALARY_RANGE_RE = re.compile(
    r"(?:[$€£]\s*)?(?P<min>[\d.,]+)\s*(?P<mink>k)?\s*[-–—]\s*(?:[$€£]\s*)?(?P<max>[\d.,]+)\s*(?P<maxk>k)?",
    re.IGNORECASE,
)

_DEFAULT_SOURCES = ("remotive", "remoteok", "wwr", "jobicy", "arbeitnow", "workingnomads", "hn")
_SOURCE_NAMES = frozenset(_DEFAULT_SOURCES)
_SEARCHABLE_SOURCES = frozenset({"remotive"})


def _get_json(client: httpx.Client, url: str, params: dict | None = None):
    resp = client.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


def _salary_value(digits: str, k_suffix: str | None) -> float:
    value = float(digits.replace(",", ""))
    return value * 1000 if k_suffix else value


def _parse_salary_range(text: str | None) -> tuple[float | None, float | None]:
    if not text:
        return None, None
    m = _SALARY_RANGE_RE.search(text)
    if m is None:
        return None, None
    return (
        _salary_value(m.group("min"), m.group("mink")),
        _salary_value(m.group("max"), m.group("maxk")),
    )


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class _HTMLStripper(HTMLParser):
    """HTML to text, newline-separating block elements so line-based parsing works."""

    _BLOCK_TAGS = frozenset({
        "br", "p", "div", "li", "tr", "ul", "ol", "section",
        "h1", "h2", "h3", "h4", "h5", "h6",
    })

    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in ("script", "style"):
            self._skip = True
        elif tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._skip = False
        elif tag in self._BLOCK_TAGS:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._parts.append(data)

    def get_text(self) -> str:
        text = html.unescape("".join(self._parts))
        text = re.sub(r"[^\S\n]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def strip_html(html_text: str) -> str:
    if not html_text:
        return ""
    stripper = _HTMLStripper()
    stripper.feed(html_text)
    return stripper.get_text()


def parse_remotive(jobs: list) -> list[RawJob]:
    result: list[RawJob] = []
    for item in jobs or []:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        salary_min, salary_max = _parse_salary_range(item.get("salary"))
        result.append(RawJob(
            title=item.get("title"),
            company=item.get("company_name"),
            location=item.get("candidate_required_location"),
            description=item.get("description"),
            url=item.get("url"),
            salary_min=salary_min,
            salary_max=salary_max,
            job_type=item.get("job_type"),
            posted_at=item.get("date"),
            is_remote=True,
            source="remotive",
            site="Remotive",
        ))
    return result


def parse_remoteok(jobs: list) -> list[RawJob]:
    result: list[RawJob] = []
    for item in jobs or []:
        if not isinstance(item, dict) or not item.get("position"):
            continue
        slug = item.get("slug")
        url = item.get("url") or (f"https://remoteok.com/remote-jobs/{slug}" if slug else "")
        result.append(RawJob(
            title=item.get("position"),
            company=item.get("company"),
            location=item.get("location"),
            description=item.get("description"),
            url=url,
            apply_url=item.get("apply_url") or "",
            salary_min=_num(item.get("salary_min")),
            salary_max=_num(item.get("salary_max")),
            salary_currency=item.get("salary_currency"),
            is_remote=True,
            source="remoteok",
            site="RemoteOK",
        ))
    return result


def parse_wwr(jobs: list) -> list[RawJob]:
    result: list[RawJob] = []
    for item in jobs or []:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        result.append(RawJob(
            title=item.get("title"),
            company=item.get("company_name"),
            location=item.get("location"),
            description=strip_html(item.get("description_html")),
            url=item.get("url"),
            apply_url=item.get("apply_url") or "",
            posted_at=item.get("published_at"),
            is_remote=True,
            source="wwr",
            site="WeWorkRemotely",
        ))
    return result


def parse_jobicy(jobs: list) -> list[RawJob]:
    result: list[RawJob] = []
    for item in jobs or []:
        if not isinstance(item, dict) or not item.get("jobTitle"):
            continue
        result.append(RawJob(
            title=item.get("jobTitle"),
            company=item.get("companyName"),
            location=item.get("jobGeo"),
            description=item.get("jobDescription"),
            url=item.get("url"),
            salary_min=_num(item.get("annualSalaryMin")),
            salary_max=_num(item.get("annualSalaryMax")),
            salary_currency=item.get("salaryCurrency"),
            salary_interval="year",
            job_type=item.get("jobType"),
            seniority=item.get("jobLevel"),
            posted_at=item.get("pubDate"),
            is_remote=True,
            source="jobicy",
            site="Jobicy",
        ))
    return result


def parse_arbeitnow(jobs: list) -> list[RawJob]:
    result: list[RawJob] = []
    for item in jobs or []:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        salary_min, salary_max = _parse_salary_range(item.get("salary"))
        result.append(RawJob(
            title=item.get("title"),
            company=item.get("company_name"),
            location=item.get("location"),
            description=item.get("description"),
            url=item.get("url"),
            salary_min=salary_min,
            salary_max=salary_max,
            job_type=item.get("job_type"),
            seniority=item.get("experience_level"),
            posted_at=item.get("published_at"),
            is_remote=True,
            source="arbeitnow",
            site="Arbeitnow",
        ))
    return result


def parse_workingnomads(jobs: list) -> list[RawJob]:
    result: list[RawJob] = []
    for item in jobs or []:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        result.append(RawJob(
            title=item.get("title"),
            company=item.get("company_name"),
            location=item.get("location"),
            description=strip_html(item.get("description")),
            url=item.get("url"),
            job_type=item.get("category_name"),
            posted_at=item.get("pub_date"),
            is_remote=True,
            source="workingnomads",
            site="Working Nomads",
        ))
    return result


def _hn_company(title_line: str) -> str:
    parts = re.split(r"\s*[|–—]\s*|\s+-\s+", title_line, maxsplit=1)
    return parts[0].strip()


def parse_hn(children: list) -> list[RawJob]:
    result: list[RawJob] = []
    for child in children or []:
        if not isinstance(child, dict):
            continue
        text = child.get("text")
        if not text:
            continue
        stripped = strip_html(text)
        if not stripped:
            continue
        title_line = next((ln.strip() for ln in stripped.splitlines() if ln.strip()), "")
        result.append(RawJob(
            title=title_line,
            company=_hn_company(title_line),
            description=stripped,
            url=f"https://news.ycombinator.com/item?id={child.get('id')}",
            is_remote=True,
            source="hn",
            site="HN Who is Hiring",
        ))
    return result


def _fetch_remotive(client: httpx.Client, term: str | None = None) -> list:
    params = {"limit": _REMOTIVE_LIMIT}
    if term:
        params["search"] = term
    payload = _get_json(client, _REMOTIVE_URL, params=params)
    return payload.get("jobs", []) if isinstance(payload, dict) else []


def _fetch_remoteok(client: httpx.Client, term: str | None = None) -> list:
    payload = _get_json(client, _REMOTE_OK_URL)
    return payload if isinstance(payload, list) else []


def _fetch_wwr(client: httpx.Client, term: str | None = None) -> list:
    payload = _get_json(client, _WWR_URL)
    return payload if isinstance(payload, list) else []


def _fetch_jobicy(client: httpx.Client, term: str | None = None) -> list:
    payload = _get_json(client, _JOBICY_URL, params={"count": _JOBICY_COUNT})
    return payload.get("jobs", []) if isinstance(payload, dict) else []


def _fetch_arbeitnow(client: httpx.Client, term: str | None = None) -> list:
    payload = _get_json(client, _ARBEITNOW_URL)
    return payload.get("data", []) if isinstance(payload, dict) else []


def _fetch_workingnomads(client: httpx.Client, term: str | None = None) -> list:
    payload = _get_json(client, _WORKING_NOMADS_URL)
    return payload if isinstance(payload, list) else []


def _fetch_hn(client: httpx.Client, term: str | None = None) -> list:
    search = _get_json(
        client,
        f"{_ALGOLIA_BASE}/search_by_date",
        params={"query": "who is hiring", "tags": "story", "hitsPerPage": 1},
    )
    if not isinstance(search, dict):
        return []
    hits = search.get("hits") or []
    if not hits:
        return []
    item = _get_json(client, f"{_ALGOLIA_BASE}/items/{hits[0]['objectID']}")
    return item.get("children", []) if isinstance(item, dict) else []


def _run_source(source: str, client: httpx.Client, term: str | None) -> list[RawJob]:
    term_arg = term if source in _SEARCHABLE_SOURCES else None
    if source == "remotive":
        return parse_remotive(_fetch_remotive(client, term_arg))
    if source == "remoteok":
        return parse_remoteok(_fetch_remoteok(client, term_arg))
    if source == "wwr":
        return parse_wwr(_fetch_wwr(client, term_arg))
    if source == "jobicy":
        return parse_jobicy(_fetch_jobicy(client, term_arg))
    if source == "arbeitnow":
        return parse_arbeitnow(_fetch_arbeitnow(client, term_arg))
    if source == "workingnomads":
        return parse_workingnomads(_fetch_workingnomads(client, term_arg))
    if source == "hn":
        return parse_hn(_fetch_hn(client, term_arg))
    return []


class RemoteBoardsProvider:
    """Remote-only job boards, fetched over public JSON feeds."""

    name = "remote_boards"

    def __init__(self, cfg: dict):
        self.cfg = cfg or {}

    def _search_queries(self, intent: dict) -> list[dict]:
        evolved = (intent or {}).get("queries")
        if evolved:
            return [q for q in evolved if q.get("query")]
        cfg = load_search_config()
        return [
            q for q in (cfg.get("queries") or [])
            if isinstance(q, dict) and q.get("query") and q.get("tier") in (1, 2)
        ]

    def search(self, intent: dict) -> ProviderResult:
        queries = self._search_queries(intent)
        if not queries:
            return ProviderResult(provider=self.name)
        term = queries[0]["query"]
        sources = self.cfg.get("sources") or list(_DEFAULT_SOURCES)
        max_results = int(self.cfg.get("max_results") or 250)
        hn_limit = int(self.cfg.get("hn_limit") or 150)

        jobs: list[RawJob] = []
        errors = 0
        limiter = (intent or {}).get("rate_limiter")
        with httpx.Client(timeout=_HTTP_TIMEOUT, headers=_HEADERS, follow_redirects=True,
                          proxy=proxy_http_url(resolve_proxy(self.cfg))) as client:
            for source in sources:
                if source not in _SOURCE_NAMES:
                    continue
                if len(jobs) >= max_results:
                    break
                try:
                    if limiter is not None:
                        limiter.wait()
                    parsed = _run_source(source, client, term)
                    if source == "hn":
                        parsed = parsed[:hn_limit]
                    jobs.extend(parsed)
                except Exception as e:
                    errors += 1
                    log.warning("remote_boards source %r failed: %s", source, e)
        jobs = jobs[:max_results]

        new = 0
        try:
            new, _ = store_raw_jobs(get_connection(), jobs, provider=self.name)
        except Exception as e:
            errors += 1
            log.warning("remote_boards store failed: %s", e)
        return ProviderResult(provider=self.name, found=len(jobs), stored=new, errors=errors)
