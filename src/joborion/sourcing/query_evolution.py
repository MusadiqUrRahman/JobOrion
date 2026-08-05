"""LLM query evolution: expanded search queries from top-fit titles + profile.

Phase D4 scope: after evaluation, an LLM generates tiered search queries from
the highest-fit job titles and profile keywords. Queries are stored in the
`query_history` table and rotated so each run reuses the least-recently-used
set, keeping the search space fresh without restarting from scratch.
"""

from __future__ import annotations

import logging

from joborion.llm import get_client

log = logging.getLogger(__name__)

DEFAULT_MIN_SCORE = 7
DEFAULT_TITLE_LIMIT = 10
MAX_QUERIES_PER_CALL = 8

_QUERY_SYSTEM_PROMPT = (
    "You are helping a job seeker expand their search queries. "
    "Given their top-fit job titles and profile keywords, suggest concise "
    "search queries for job boards. Prefer exact title phrasing and common "
    "industry synonyms. Return each query on its own line in the format "
    f"QUERY|TIER where TIER is 1 (exact, high precision), 2 (broad), or "
    f"3 (wide net). No more than {MAX_QUERIES_PER_CALL} queries. "
    "Never include personal data or contact information."
)


def _profile_keywords() -> list[str]:
    """Target-role + skill terms from the profile, deduplicated in order."""
    try:
        from joborion.config import load_profile
        profile = load_profile()
    except Exception:
        return []

    keywords: list[str] = []
    experience = profile.get("experience") or {}
    target_role = (experience.get("target_role") or "").strip()
    if target_role:
        keywords.append(target_role)
    skills = profile.get("skills_boundary") or {}
    for group in ("programming_languages", "frameworks", "tools"):
        keywords.extend(
            entry.strip() for entry in (skills.get(group) or []) if entry and entry.strip()
        )

    seen: list[str] = []
    for keyword in keywords:
        if keyword not in seen:
            seen.append(keyword)
    return seen


def _top_fit_titles(conn, limit: int = DEFAULT_TITLE_LIMIT, min_score: int = DEFAULT_MIN_SCORE) -> list[str]:
    """Titles of the highest-fit evaluated jobs."""
    rows = conn.execute(
        """SELECT title FROM jobs
           WHERE fit_score IS NOT NULL AND fit_score >= ? AND title IS NOT NULL
           ORDER BY fit_score DESC, scored_at DESC
           LIMIT ?""",
        (min_score, limit),
    ).fetchall()
    return [row["title"] for row in rows if row["title"]]


def _build_messages(titles: list[str], keywords: list[str]) -> list[dict]:
    title_block = "\n".join(f"- {t}" for t in titles[:DEFAULT_TITLE_LIMIT])
    keyword_block = ", ".join(keywords) if keywords else "(none)"
    user_content = (
        f"TOP-FIT TITLES:\n{title_block}\n\n"
        f"PROFILE KEYWORDS:\n{keyword_block}\n\n"
        "Generate expanded search queries."
    )
    return [
        {"role": "system", "content": _QUERY_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


def _parse_queries_response(response: str) -> list[dict]:
    """Parse QUERY|TIER lines into a list of query dicts.

    Non-conforming lines are skipped; tier values are clamped to 1-3.
    """
    queries: list[dict] = []
    for line in response.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        query, _, tier_raw = line.partition("|")
        query = query.strip()
        if not query:
            continue
        try:
            tier = int(tier_raw.strip())
        except ValueError:
            continue
        queries.append({"query": query, "tier": max(1, min(3, tier))})
    return queries


def _store(conn, queries: list[dict]) -> list[dict]:
    """Persist new queries; return only those not already in history."""
    existing = {
        row["query"]
        for row in conn.execute("SELECT query FROM query_history").fetchall()
    }
    fresh = [q for q in queries if q["query"] not in existing]
    if not fresh:
        return []
    conn.executemany(
        "INSERT INTO query_history (query, tier, origin) VALUES (?, ?, 'llm')",
        [(q["query"], q["tier"]) for q in fresh],
    )
    conn.commit()
    return fresh


def expand_queries(conn, client=None, limit: int = DEFAULT_TITLE_LIMIT,
                   min_score: int = DEFAULT_MIN_SCORE) -> list[dict]:
    """LLM-generate tiered queries from top-fit titles; store and return them.

    Skips the LLM call entirely when no evaluated jobs meet `min_score`.
    """
    titles = _top_fit_titles(conn, limit=limit, min_score=min_score)
    if not titles:
        return []

    client = client or get_client()
    messages = _build_messages(titles, _profile_keywords())
    try:
        response = client.chat(messages, max_tokens=300, temperature=0.7)
    except Exception as exc:
        log.warning("Query evolution LLM call failed: %s", exc)
        return []

    queries = _parse_queries_response(response)[:MAX_QUERIES_PER_CALL]
    if not queries:
        return []
    return _store(conn, queries)


def active_queries(conn, limit: int | None = None) -> list[dict]:
    """Active evolved queries ordered for tier rotation: unused first, then LRU."""
    rows = conn.execute(
        """SELECT query, tier FROM query_history
           WHERE active = 1
           ORDER BY (used_at IS NULL) DESC, used_at ASC, id ASC"""
    ).fetchall()
    queries = [{"query": row["query"], "tier": row["tier"]} for row in rows]
    if limit is not None:
        queries = queries[:limit]
    return queries


def mark_queries_used(conn, queries: list[dict]) -> None:
    """Stamp `used_at` so rotation moves on to the next set next run."""
    if not queries:
        return
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        "UPDATE query_history SET used_at = ? WHERE query = ? AND origin = 'llm'",
        [(now, q["query"]) for q in queries],
    )
    conn.commit()


def record_query_passes(conn, queries: list[dict], passed: int) -> None:
    """Record how many gated jobs came from each query (feedback for ranking)."""
    if not queries:
        return
    conn.executemany(
        "UPDATE query_history SET last_passed = ? WHERE query = ? AND origin = 'llm'",
        [(passed, q["query"]) for q in queries],
    )
    conn.commit()
