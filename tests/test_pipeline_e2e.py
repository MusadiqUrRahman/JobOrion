"""End-to-end pipeline integration tests.

Tests the full data flow: search → enrich → score → tailor → letter → export.
Real SQLite DB, mocked external I/O (LLM, jobspy, Playwright).
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from joborion.database import close_connection, init_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
def sample_jobs():
    return [
        {
            "url": "http://example.com/job/1",
            "title": "Senior Python Engineer",
            "site": "linkedin",
            "location": "Remote",
            "full_description": (
                "We are looking for a Senior Python Engineer with 5+ years experience. "
                "Requirements: Python, Django, FastAPI, PostgreSQL, Docker, AWS. "
                "Nice to have: Kubernetes, Terraform, Redis."
            ),
            "discovered_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "url": "http://example.com/job/2",
            "title": "Backend Developer",
            "site": "indeed",
            "location": "New York, NY",
            "full_description": (
                "Backend Developer role. Tech stack: Python, Flask, MySQL, Redis. "
                "Experience with REST APIs and microservices required."
            ),
            "discovered_at": datetime.now(timezone.utc).isoformat(),
        },
        {
            "url": "http://example.com/job/3",
            "title": "Data Engineer",
            "site": "glassdoor",
            "location": "San Francisco, CA",
            "full_description": (
                "Data Engineer building pipelines. Python, Spark, Airflow, AWS. "
                "SQL expertise required. Experience with dbt is a plus."
            ),
            "discovered_at": datetime.now(timezone.utc).isoformat(),
        },
    ]


@pytest.fixture
def seeded_db(conn, sample_jobs):
    for job in sample_jobs:
        conn.execute(
            "INSERT INTO jobs (url, title, site, location, full_description, discovered_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (job["url"], job["title"], job["site"], job["location"],
             job["full_description"], job["discovered_at"]),
        )
    conn.commit()
    return conn


@pytest.fixture
def resume_file(tmp_path):
    resume = tmp_path / "resume.txt"
    resume.write_text(
        "John Doe\n"
        "Software Engineer\n\n"
        "EXPERIENCE\n"
        "Senior Python Developer at Acme Corp (2020-2024)\n"
        "- Built REST APIs with FastAPI and Django\n"
        "- Deployed microservices on AWS ECS with Docker\n"
        "- Managed PostgreSQL databases serving 10M+ requests/day\n\n"
        "SKILLS\n"
        "Python, Django, FastAPI, PostgreSQL, Docker, AWS, Redis, Git",
        encoding="utf-8",
    )
    return resume


@pytest.fixture
def profile_file(tmp_path):
    profile = tmp_path / "profile.json"
    profile.write_text(
        json.dumps({
            "personal": {
                "full_name": "John Doe",
                "preferred_name": "John",
                "email": "john@example.com",
            },
            "skills_boundary": {
                "languages": ["Python", "JavaScript"],
                "frameworks": ["Django", "FastAPI", "React"],
                "infrastructure": ["Docker", "AWS", "PostgreSQL"],
            },
            "resume_facts": {
                "preserved_companies": ["Acme Corp"],
                "preserved_school": "MIT",
                "real_metrics": ["10M+ requests/day", "50ms p99 latency"],
            },
        }),
        encoding="utf-8",
    )
    return profile


VALID_TAILORED_JSON = json.dumps({
    "title": "Senior Python Engineer",
    "summary": "Senior Python engineer with 4+ years building scalable APIs.",
    "experience": [
        {
            "header": "Senior Python Developer at Acme Corp",
            "subtitle": "Python, FastAPI | 2020-2024",
            "bullets": [
                "Built REST APIs with FastAPI serving 10M+ requests/day",
                "Deployed Docker containers on AWS ECS",
            ],
        }
    ],
    "projects": [
        {
            "header": "JobOrion - AI Job Pipeline",
            "subtitle": "Python, LLMs | 2024",
            "bullets": [
                "Built automated job application pipeline with Python",
            ],
        }
    ],
    "skills": {
        "Languages": "Python",
        "Frameworks": "FastAPI, React",
        "Databases": "PostgreSQL",
        "DevOps & Infra": "Docker, AWS",
        "Tools": "Git",
    },
    "education": "MIT | BS Computer Science",
})


# ---------------------------------------------------------------------------
# Scoring e2e tests
# ---------------------------------------------------------------------------

class TestScoringE2E:
    def test_score_jobs_writes_scores_to_db(self, seeded_db, resume_file, db_path):
        mock_client = MagicMock()
        mock_client.chat.return_value = (
            "SCORE: 8\n"
            "KEYWORDS: python, django, fastapi, postgresql\n"
            "REASONING: Strong match with Python backend experience."
        )

        with patch("joborion.scoring.fit_scorer.get_client", return_value=mock_client):
            with patch("joborion.scoring.fit_scorer.RESUME_PATH", resume_file):
                with patch("joborion.database.DB_PATH", str(db_path)):
                    from joborion.scoring.fit_scorer import score_jobs
                    result = score_jobs(rescore=True)

        assert result["scored"] == 3

        conn = seeded_db
        scores = conn.execute(
            "SELECT url, fit_score, score_reasoning FROM jobs ORDER BY url"
        ).fetchall()
        assert all(row["fit_score"] is not None for row in scores)
        assert all(row["fit_score"] >= 1 for row in scores)
        assert all(row["score_reasoning"] for row in scores)

    def test_score_single_job(self, seeded_db, resume_file, db_path):
        mock_client = MagicMock()
        mock_client.chat.return_value = (
            "SCORE: 9\n"
            "KEYWORDS: python, fastapi\n"
            "REASONING: Perfect match."
        )

        with patch("joborion.scoring.fit_scorer.get_client", return_value=mock_client):
            with patch("joborion.scoring.fit_scorer.RESUME_PATH", resume_file):
                with patch("joborion.config.RESUME_PATH", resume_file):
                    with patch("joborion.database.DB_PATH", str(db_path)):
                        from joborion.tools.scoring import ScoreSingleJobTool
                        tool = ScoreSingleJobTool()
                        result = tool.execute(url="http://example.com/job/1")

        assert result.status == "ok"
        assert result.details["score"] == 9

        conn = seeded_db
        row = conn.execute(
            "SELECT fit_score FROM jobs WHERE url = ?",
            ("http://example.com/job/1",),
        ).fetchone()
        assert row["fit_score"] == 9


# ---------------------------------------------------------------------------
# Tailoring e2e tests
# ---------------------------------------------------------------------------

class TestTailoringE2E:
    def _seed_scored_job(self, conn, url, score=8):
        conn.execute(
            "UPDATE jobs SET fit_score = ?, score_reasoning = ? WHERE url = ?",
            (score, "Strong match", url),
        )
        conn.commit()

    def test_tailor_resume_writes_file(self, seeded_db, resume_file, profile_file, db_path, tmp_path):
        self._seed_scored_job(seeded_db, "http://example.com/job/1", score=9)
        tailored_dir = tmp_path / "tailored"
        tailored_dir.mkdir()

        mock_client = MagicMock()
        mock_client.chat.return_value = VALID_TAILORED_JSON

        with patch("joborion.scoring.resume_tailor.get_client", return_value=mock_client):
            with patch("joborion.scoring.resume_tailor.RESUME_PATH", resume_file):
                with patch("joborion.scoring.resume_tailor.TAILORED_DIR", tailored_dir):
                    with patch("joborion.scoring.resume_tailor.load_profile",
                               return_value=json.loads(profile_file.read_text())):
                        with patch("joborion.database.DB_PATH", str(db_path)):
                            from joborion.scoring.resume_tailor import tailor_resumes
                            tailor_resumes(min_score=7, validation_mode="lenient")

        conn = seeded_db
        row = conn.execute(
            "SELECT tailored_resume_path FROM jobs WHERE url = ?",
            ("http://example.com/job/1",),
        ).fetchone()
        assert row is not None
        assert row["tailored_resume_path"] is not None
        assert Path(row["tailored_resume_path"]).exists()

    def test_tailor_skips_low_score(self, seeded_db, resume_file, profile_file, db_path, tmp_path):
        self._seed_scored_job(seeded_db, "http://example.com/job/2", score=3)
        tailored_dir = tmp_path / "tailored"
        tailored_dir.mkdir()

        mock_client = MagicMock()

        with patch("joborion.scoring.resume_tailor.get_client", return_value=mock_client):
            with patch("joborion.scoring.resume_tailor.RESUME_PATH", resume_file):
                with patch("joborion.scoring.resume_tailor.TAILORED_DIR", tailored_dir):
                    with patch("joborion.scoring.resume_tailor.load_profile",
                               return_value=json.loads(profile_file.read_text())):
                        with patch("joborion.database.DB_PATH", str(db_path)):
                            from joborion.scoring.resume_tailor import tailor_resumes
                            tailor_resumes(min_score=7)

        conn = seeded_db
        row = conn.execute(
            "SELECT tailored_resume_path FROM jobs WHERE url = ?",
            ("http://example.com/job/2",),
        ).fetchone()
        assert row["tailored_resume_path"] is None
        mock_client.chat.assert_not_called()


# ---------------------------------------------------------------------------
# Cover letter e2e tests
# ---------------------------------------------------------------------------

class TestCoverLetterE2E:
    def _seed_tailored_job(self, conn, url, tailored_path="/tmp/test_resume.pdf"):
        conn.execute(
            "UPDATE jobs SET fit_score = 8, tailored_resume_path = ? WHERE url = ?",
            (tailored_path, url),
        )
        conn.commit()

    def test_cover_letter_writes_file(self, seeded_db, resume_file, profile_file, db_path, tmp_path):
        tailored = tmp_path / "tailored.txt"
        tailored.write_text("Tailored resume content", encoding="utf-8")
        self._seed_tailored_job(seeded_db, "http://example.com/job/1", str(tailored))
        cover_dir = tmp_path / "covers"
        cover_dir.mkdir()

        mock_client = MagicMock()
        mock_client.chat.return_value = (
            "Dear Hiring Manager,\n\n"
            "I am writing to express my interest in the Senior Python Engineer role. "
            "At Acme Corp, I built REST APIs with FastAPI serving 10M+ requests per day.\n\n"
            "Happy to discuss further.\n\n"
            "Best regards,\nJohn"
        )

        with patch("joborion.scoring.cover_writer.get_client", return_value=mock_client):
            with patch("joborion.scoring.cover_writer.RESUME_PATH", resume_file):
                with patch("joborion.scoring.cover_writer.COVER_LETTER_DIR", cover_dir):
                    with patch("joborion.scoring.cover_writer.load_profile",
                               return_value=json.loads(profile_file.read_text())):
                        with patch("joborion.database.DB_PATH", str(db_path)):
                            from joborion.scoring.cover_writer import write_cover_letters
                            write_cover_letters(min_score=7)

        conn = seeded_db
        row = conn.execute(
            "SELECT cover_letter_path FROM jobs WHERE url = ?",
            ("http://example.com/job/1",),
        ).fetchone()
        assert row is not None
        assert row["cover_letter_path"] is not None
        assert Path(row["cover_letter_path"]).exists()


# ---------------------------------------------------------------------------
# Data flow e2e tests
# ---------------------------------------------------------------------------

class TestDataFlow:
    def test_full_flow_score_to_cover(self, seeded_db, resume_file, profile_file, db_path, tmp_path):
        """Test complete flow: score -> tailor -> cover letter for 3 jobs."""
        tailored_dir = tmp_path / "tailored"
        tailored_dir.mkdir()
        cover_dir = tmp_path / "covers"
        cover_dir.mkdir()
        db = str(db_path)

        mock_client = MagicMock()

        def mock_chat(messages, **kwargs):
            sys_content = messages[0].get("content", "") if messages else ""

            if "job fit evaluator" in sys_content.lower():
                return "SCORE: 8\nKEYWORDS: python\nREASONING: Good match."

            if "tailored resume" in sys_content.lower():
                return VALID_TAILORED_JSON

            return "Dear Hiring Manager,\n\nI am interested.\n\nBest,\nJohn"

        mock_client.chat.side_effect = mock_chat

        with patch("joborion.scoring.fit_scorer.get_client", return_value=mock_client):
            with patch("joborion.scoring.resume_tailor.get_client", return_value=mock_client):
                with patch("joborion.scoring.cover_writer.get_client", return_value=mock_client):
                    with patch("joborion.scoring.fit_scorer.RESUME_PATH", resume_file):
                        with patch("joborion.scoring.resume_tailor.RESUME_PATH", resume_file):
                            with patch("joborion.scoring.cover_writer.RESUME_PATH", resume_file):
                                with patch("joborion.scoring.resume_tailor.TAILORED_DIR", tailored_dir):
                                    with patch("joborion.scoring.cover_writer.COVER_LETTER_DIR", cover_dir):
                                        with patch("joborion.scoring.resume_tailor.load_profile",
                                                   return_value=json.loads(profile_file.read_text())):
                                            with patch("joborion.scoring.cover_writer.load_profile",
                                                       return_value=json.loads(profile_file.read_text())):
                                                with patch("joborion.database.DB_PATH", db):
                                                    from joborion.scoring.fit_scorer import score_jobs
                                                    from joborion.scoring.resume_tailor import tailor_resumes
                                                    from joborion.scoring.cover_writer import write_cover_letters

                                                    score_jobs(rescore=True)
                                                    tailor_resumes(min_score=7, validation_mode="lenient")
                                                    write_cover_letters(min_score=7)

        from joborion.database import get_connection
        close_connection(db)
        conn = get_connection(db)
        jobs = conn.execute(
            "SELECT url, fit_score, tailored_resume_path, cover_letter_path "
            "FROM jobs ORDER BY url"
        ).fetchall()

        for job in jobs:
            assert job["fit_score"] is not None
            assert job["fit_score"] >= 1
            assert job["tailored_resume_path"] is not None
            assert Path(job["tailored_resume_path"]).exists()
            assert job["cover_letter_path"] is not None
            assert Path(job["cover_letter_path"]).exists()


# ---------------------------------------------------------------------------
# Error recovery e2e tests
# ---------------------------------------------------------------------------

class TestErrorRecovery:
    def test_scoring_continues_after_one_llm_error(self, seeded_db, resume_file, db_path):
        call_idx = 0

        def mock_chat(messages, **kwargs):
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                raise RuntimeError("API timeout")
            return "SCORE: 7\nKEYWORDS: python\nREASONING: Good match."

        mock_client = MagicMock()
        mock_client.chat.side_effect = mock_chat

        with patch("joborion.scoring.fit_scorer.get_client", return_value=mock_client):
            with patch("joborion.scoring.fit_scorer.RESUME_PATH", resume_file):
                with patch("joborion.database.DB_PATH", str(db_path)):
                    from joborion.scoring.fit_scorer import score_jobs
                    result = score_jobs(rescore=True)

        assert result["scored"] == 3
        assert result["errors"] == 1

        conn = seeded_db
        scores = conn.execute(
            "SELECT url, fit_score FROM jobs ORDER BY url"
        ).fetchall()
        high_score_count = sum(1 for row in scores if row["fit_score"] is not None and row["fit_score"] > 0)
        assert high_score_count == 2
