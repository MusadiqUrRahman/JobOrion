"""Tests for the LLM fit scorer: parsing, retry on unparseable responses,
and persistence rules (score 0 failures must not be written to the DB)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from joborion.database import close_connection, init_db
from joborion.scoring.fit_scorer import (
    _chat_for_score,
    _parse_score_response,
    score_jobs,
)


@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"


@pytest.fixture
def conn(db_path):
    close_connection(str(db_path))
    c = init_db(str(db_path))
    yield c
    close_connection(str(db_path))


@pytest.fixture
def seeded_db(conn):
    jobs = [
        ("http://example.com/job/1", "Senior Python Engineer", "Remote",
         "Python, Django, FastAPI, PostgreSQL, Docker, AWS."),
        ("http://example.com/job/2", "Backend Developer", "Remote",
         "Python, Flask, MySQL, Redis, REST APIs."),
        ("http://example.com/job/3", "Data Engineer", "Remote",
         "Python, Spark, Airflow, AWS, SQL, dbt."),
    ]
    now = datetime.now(timezone.utc).isoformat()
    for url, title, loc, desc in jobs:
        conn.execute(
            "INSERT INTO jobs (url, title, site, location, full_description, discovered_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (url, title, "test", loc, desc, now),
        )
    conn.commit()
    return conn


@pytest.fixture
def resume_file(tmp_path):
    resume = tmp_path / "resume.txt"
    resume.write_text(
        "John Doe\nSoftware Engineer\nPython, Django, FastAPI, PostgreSQL, Docker, AWS, Git",
        encoding="utf-8",
    )
    return resume


def test_parse_valid_response():
    response = (
        "SCORE: 8\n"
        "KEYWORDS: python, fastapi\n"
        "REASONING: Strong match on Python backend experience."
    )
    result = _parse_score_response(response)
    assert result["score"] == 8
    assert "python" in result["keywords"]
    assert "Strong match" in result["reasoning"]


def test_parse_clamps_score_to_1_10():
    result = _parse_score_response("SCORE: 42\nKEYWORDS: x\nREASONING: y")
    assert result["score"] == 10


def test_parse_missing_score_line_returns_zero():
    result = _parse_score_response("REASONING: no score line here")
    assert result["score"] == 0


def test_parse_truncated_response_returns_zero():
    result = _parse_score_response(
        "Given the eligibility rules, the candidate requires sponsorship... "
        "The role is"
    )
    assert result["score"] == 0


def test_chat_for_score_retries_terse_prompt_on_truncation():
    client = MagicMock()
    client.chat.side_effect = [
        "The role requires work authorization the candidate does not have. The role is",
        "SCORE: 1\nKEYWORDS: python\nREASONING: Hard reject on sponsorship.",
    ]
    result = _chat_for_score(client, [{"role": "user", "content": "prompt"}])
    assert result["score"] == 1
    assert client.chat.call_count == 2
    terse = client.chat.call_args_list[1][0][0]
    assert terse[-1]["content"].startswith("Output only the score")


def test_chat_for_score_returns_zero_after_all_retries():
    client = MagicMock()
    client.chat.return_value = "still no score line"
    result = _chat_for_score(client, [{"role": "user", "content": "prompt"}])
    assert result["score"] == 0


def test_score_jobs_does_not_persist_score_zero(seeded_db, resume_file, db_path):
    client = MagicMock()
    client.chat.return_value = "unparseable truncated response"

    with patch("joborion.scoring.fit_scorer.get_client", return_value=client):
        with patch("joborion.scoring.fit_scorer.RESUME_PATH", resume_file):
            with patch("joborion.database.DB_PATH", str(db_path)):
                result = score_jobs(rescore=True)

    assert result["errors"] == 3
    conn = seeded_db
    zero_rows = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE fit_score = 0"
    ).fetchone()[0]
    assert zero_rows == 0


def test_score_jobs_persists_retried_scores(seeded_db, resume_file, db_path):
    client = MagicMock()
    client.chat.side_effect = [
        "truncated response without score",
        "SCORE: 7\nKEYWORDS: python\nREASONING: Good fit after retry.",
        "SCORE: 5\nKEYWORDS: flask\nREASONING: Moderate match.",
        "SCORE: 3\nKEYWORDS: spark\nREASONING: Weak match.",
        "SCORE: 2\nKEYWORDS: airflow\nREASONING: Poor match.",
        "SCORE: 4\nKEYWORDS: dbt\nREASONING: Weak match.",
    ]

    with patch("joborion.scoring.fit_scorer.get_client", return_value=client):
        with patch("joborion.scoring.fit_scorer.RESUME_PATH", resume_file):
            with patch("joborion.database.DB_PATH", str(db_path)):
                result = score_jobs(rescore=True)

    assert result["scored"] == 3
    conn = seeded_db
    scores = conn.execute("SELECT fit_score FROM jobs").fetchall()
    assert all(s["fit_score"] >= 1 for s in scores)
