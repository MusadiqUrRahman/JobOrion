"""Job fit scoring: LLM-powered evaluation of candidate-job match quality.

Scores jobs on a 1-10 scale by comparing the user's resume against each
job description. All personal data is loaded at runtime from the user's
profile and resume file.
"""

import logging
import re
import time
from datetime import datetime, timezone

from joborion.config import RESUME_PATH
from joborion.database import get_connection, get_jobs_by_stage
from joborion.eligibility import constraints_from_profile, evaluate_job
from joborion.llm import get_client

log = logging.getLogger(__name__)


# ── Scoring Prompt ────────────────────────────────────────────────────────

SCORE_PROMPT = """You are a job fit evaluator. Given a candidate's resume and a job description, score how well the candidate fits the role.

SCORING CRITERIA:
- 9-10: Perfect match. Candidate has direct experience in nearly all required skills and qualifications.
- 7-8: Strong match. Candidate has most required skills, minor gaps easily bridged.
- 5-6: Moderate match. Candidate has some relevant skills but missing key requirements.
- 3-4: Weak match. Significant skill gaps, would need substantial ramp-up.
- 1-2: Poor match. Completely different field or experience level.

CANDIDATE CONSTRAINTS:
- Location: {candidate_location}
- Work authorization: {work_auth}
- Visa sponsorship required: {sponsorship}

ELIGIBILITY RULES (HARD REJECT — always score 1):
- The role requires onsite/office attendance in a country the candidate cannot work in.
- The role requires work authorization the candidate does not have (e.g. "must be US citizen", "must have US work authorization", "sponsorship not available", "candidates must already be authorized to work in the US/UK/Canada", etc.).
- The role is location-restricted to a country the candidate cannot work in, even if listed as "remote" (e.g. "Remote, US only", "remote — must reside in the US").

IMPORTANT FACTORS:
- Weight technical skills heavily (programming languages, frameworks, tools)
- Consider transferable experience (automation, scripting, API work)
- Factor in the candidate's project experience
- Be realistic about experience level vs. job requirements (years of experience, seniority)

RESPOND IN EXACTLY THIS FORMAT (no other text):
SCORE: [1-10]
KEYWORDS: [comma-separated ATS keywords from the job description that match or could match the candidate]
REASONING: [2-3 sentences explaining the score; if ineligible, say so explicitly]"""

# Larger output budget than the old 512 so the REASONING section (and the
# SCORE line that follows it) isn't cut off mid-response.
_SCORE_MAX_TOKENS = 1024

# Terse follow-up used when a response is truncated / format-breaking and has
# no SCORE line. Cheap enough to retry without re-paying for the full context.
_SCORE_RETRIES = 2
_SCORE_ONLY_PROMPT = "Output only the score, as exactly: SCORE: [1-10]"


def _parse_score_response(response: str) -> dict:
    """Parse the LLM's score response into structured data.

    Args:
        response: Raw LLM response text.

    Returns:
        {"score": int, "keywords": str, "reasoning": str}
    """
    score = 0
    keywords = ""
    reasoning = response

    for line in response.split("\n"):
        line = line.strip()
        if line.startswith("SCORE:"):
            try:
                score = int(re.search(r"\d+", line).group())
                score = max(1, min(10, score))
            except (AttributeError, ValueError):
                score = 0
        elif line.startswith("KEYWORDS:"):
            keywords = line.replace("KEYWORDS:", "").strip()
        elif line.startswith("REASONING:"):
            reasoning = line.replace("REASONING:", "").strip()

    return {"score": score, "keywords": keywords, "reasoning": reasoning}


def _candidate_constraints() -> dict:
    """Build candidate eligibility context from the user's profile."""
    try:
        from joborion.config import load_profile
        profile = load_profile()
    except Exception:
        return {
            "candidate_location": "unknown",
            "work_auth": "unknown",
            "sponsorship": "unknown",
            "country": "",
            "home_country": "",
            "authorized_countries": [],
            "sponsorship_needed": True,
            "relocation_willing": False,
            "legally_authorized": False,
            "work_permit_type": "",
        }
    return constraints_from_profile(profile)


def _chat_for_score(client, messages: list[dict]) -> dict:
    """Run the scoring chat, retrying when the response has no SCORE line.

    The scoring prompt asks for SCORE/KEYWORDS/REASONING, but models
    occasionally write long prose first and the response gets truncated
    before the SCORE line. A terse follow-up ("output only the score")
    normally recovers the number. Returns the parsed result; score stays 0
    only when every attempt was unparseable.
    """
    result = _parse_score_response(client.chat(messages, max_tokens=_SCORE_MAX_TOKENS, temperature=0.2))
    for _ in range(_SCORE_RETRIES):
        if result["score"] > 0:
            return result
        log.warning(
            "Score response unparseable (no SCORE line); retrying with terse prompt"
        )
        result = _parse_score_response(
            client.chat(messages + [{"role": "user", "content": _SCORE_ONLY_PROMPT}],
                        max_tokens=32, temperature=0.2)
        )
    return result


def score_job(resume_text: str, job: dict, constraints: dict | None = None,
              mode: str = "all") -> dict:
    """Score a single job against the resume.

    Args:
        resume_text: The candidate's full resume text.
        job: Job dict with keys: title, site, location, full_description.
        constraints: Candidate eligibility context from _candidate_constraints().
        mode: Search mode driving eligibility (remote/local/sponsorship/all).

    Returns:
        {"score": int, "keywords": str, "reasoning": str,
         "rejection_reason": str | None, "rejection_suggestion": str | None}
    """
    if constraints is None:
        constraints = _candidate_constraints()

    try:
        from joborion.config import load_profile
        profile = load_profile()
    except Exception:
        profile = {}

    elig = evaluate_job(job, profile, mode=mode)
    if not elig.eligible:
        return {
            "score": 1,
            "keywords": "",
            "reasoning": f"Hard rejected: {elig.suggestion or elig.reason}",
            "rejection_reason": elig.reason,
            "rejection_suggestion": elig.suggestion,
        }

    prompt = SCORE_PROMPT.format(**constraints)
    job_text = (
        f"TITLE: {job['title']}\n"
        f"COMPANY: {job['site']}\n"
        f"LOCATION: {job.get('location', 'N/A')}\n\n"
        f"DESCRIPTION:\n{(job.get('full_description') or '')[:6000]}"
    )

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"RESUME:\n{resume_text}\n\n---\n\nJOB POSTING:\n{job_text}"},
    ]

    try:
        client = get_client()
        result = _chat_for_score(client, messages)
        result["rejection_reason"] = None
        result["rejection_suggestion"] = None
        return result
    except Exception as e:
        log.error("LLM error scoring job '%s': %s", job.get("title", "?"), e)
        return {
            "score": 0,
            "keywords": "",
            "reasoning": f"LLM error: {e}",
            "rejection_reason": None,
            "rejection_suggestion": None,
        }


def score_jobs(limit: int = 0, rescore: bool = False) -> dict:
    """Score unscored jobs that have full descriptions.

    Args:
        limit: Maximum number of jobs to score in this run.
        rescore: If True, re-score all jobs (not just unscored ones).

    Returns:
        {"scored": int, "errors": int, "elapsed": float, "distribution": list}
    """
    resume_text = RESUME_PATH.read_text(encoding="utf-8")
    constraints = _candidate_constraints()
    conn = get_connection()

    try:
        from joborion.config import load_search_config
        mode = load_search_config().get("defaults", {}).get("search_mode", "all")
    except Exception:
        mode = "all"

    if rescore:
        query = "SELECT * FROM jobs WHERE full_description IS NOT NULL"
        if limit > 0:
            query += f" LIMIT {limit}"
        jobs = conn.execute(query).fetchall()
    else:
        jobs = get_jobs_by_stage(conn=conn, stage="pending_score", limit=limit)

    if not jobs:
        log.info("No unscored jobs with descriptions found.")
        return {"scored": 0, "errors": 0, "elapsed": 0.0, "distribution": []}

    # Convert sqlite3.Row to dicts if needed
    if jobs and not isinstance(jobs[0], dict):
        columns = jobs[0].keys()
        jobs = [dict(zip(columns, row)) for row in jobs]

    log.info("Scoring %d jobs sequentially...", len(jobs))
    t0 = time.time()
    completed = 0
    errors = 0
    results: list[dict] = []

    for job in jobs:
        result = score_job(resume_text, job, constraints, mode=mode)
        result["url"] = job["url"]
        completed += 1

        if result["score"] == 0:
            errors += 1

        results.append(result)

        log.info(
            "[%d/%d] score=%d  %s",
            completed, len(jobs), result["score"], job.get("title", "?")[:60],
        )

    # Write scores to DB
    now = datetime.now(timezone.utc).isoformat()
    for r in results:
        if r["score"] == 0:
            # Scoring failed (LLM/parse error). Leave fit_score NULL so the
            # job is picked up again by a later run instead of being frozen
            # at a fake 0.
            log.warning("Not persisting score 0 for %s (retry next run)", r["url"])
            continue
        conn.execute(
            "UPDATE jobs SET fit_score = ?, score_reasoning = ?, scored_at = ?, "
            "rejection_reason = ?, rejection_suggestion = ? WHERE url = ?",
            (r["score"], f"{r['keywords']}\n{r['reasoning']}", now,
             r.get("rejection_reason"), r.get("rejection_suggestion"), r["url"]),
        )
    conn.commit()

    elapsed = time.time() - t0
    log.info("Done: %d scored in %.1fs (%.1f jobs/sec)", len(results), elapsed, len(results) / elapsed if elapsed > 0 else 0)

    # Score distribution
    dist = conn.execute("""
        SELECT fit_score, COUNT(*) FROM jobs
        WHERE fit_score IS NOT NULL
        GROUP BY fit_score ORDER BY fit_score DESC
    """).fetchall()
    distribution = [(row[0], row[1]) for row in dist]

    return {
        "scored": len(results),
        "errors": errors,
        "elapsed": elapsed,
        "distribution": distribution,
    }
