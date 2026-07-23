"""Tests for joborion.scoring.output_checker — validation logic."""

import pytest
from joborion.scoring.output_checker import (
    BANNED_WORDS,
    FABRICATION_WATCHLIST,
    LLM_LEAK_PHRASES,
    REQUIRED_SECTIONS,
    sanitize_text,
    validate_json_fields,
    validate_cover_letter,
    validate_tailored_resume,
)

SAMPLE_PROFILE = {
    "personal": {
        "full_name": "Jane Doe",
        "email": "jane@example.com",
        "phone": "555-1234",
    },
    "resume_facts": {
        "preserved_companies": ["Acme Corp"],
        "preserved_projects": ["Project Alpha"],
        "preserved_school": "MIT",
    },
    "skills_boundary": {
        "languages": ["Python", "JavaScript"],
        "frameworks": ["React", "FastAPI"],
        "tools": ["Docker", "PostgreSQL"],
    },
}

SAMPLE_JSON_DATA = {
    "title": "Senior Python Engineer",
    "summary": "Experienced engineer with 5 years building web services.",
    "skills": {"languages": "Python, JavaScript", "frameworks": "FastAPI, React"},
    "experience": [
        {
            "header": "Acme Corp — Senior Engineer",
            "bullets": [
                "Built data pipelines processing 1M events/day",
                "Led migration from monolith to microservices",
            ],
        }
    ],
    "projects": [
        {"header": "Project Alpha", "bullets": ["Open source data visualization tool"]}
    ],
    "education": "B.S. Computer Science, MIT",
}


# ── sanitize_text ──────────────────────────────────────────────────────


class TestSanitizeText:
    def test_em_dash_to_comma(self):
        assert sanitize_text("foo \u2014 bar") == "foo, bar"

    def test_em_dash_no_spaces(self):
        assert sanitize_text("foo\u2014bar") == "foo, bar"

    def test_en_dash_to_hyphen(self):
        assert sanitize_text("node\u2013js") == "node-js"

    def test_smart_double_quotes(self):
        assert sanitize_text("\u201chello\u201d") == '"hello"'

    def test_smart_single_quotes(self):
        assert sanitize_text("it\u2019s") == "it's"

    def test_clean_text_unchanged(self):
        assert sanitize_text("hello world") == "hello world"

    def test_strips_whitespace(self):
        assert sanitize_text("  hello  ") == "hello"


# ── BANNED_WORDS and constants ─────────────────────────────────────────


class TestConstants:
    def test_banned_words_not_empty(self):
        assert len(BANNED_WORDS) > 20

    def test_llm_leak_phrases_not_empty(self):
        assert len(LLM_LEAK_PHRASES) > 10

    def test_fabrication_watchlist_not_empty(self):
        assert len(FABRICATION_WATCHLIST) > 5

    def test_required_sections(self):
        assert REQUIRED_SECTIONS == {"SUMMARY", "TECHNICAL SKILLS", "EXPERIENCE", "PROJECTS", "EDUCATION"}


# ── validate_json_fields ───────────────────────────────────────────────


class TestValidateJsonFields:
    def test_valid_data_passes(self):
        result = validate_json_fields(SAMPLE_JSON_DATA, SAMPLE_PROFILE)
        assert result["passed"] is True
        assert result["errors"] == []

    def test_missing_required_field(self):
        data = {k: v for k, v in SAMPLE_JSON_DATA.items() if k != "summary"}
        result = validate_json_fields(data, SAMPLE_PROFILE)
        assert result["passed"] is False
        assert any("Missing required field: summary" in e for e in result["errors"])

    def test_fabricated_skill_detected(self):
        data = dict(SAMPLE_JSON_DATA)
        data["skills"] = {"languages": "Python", "frameworks": "Django"}
        result = validate_json_fields(data, SAMPLE_PROFILE)
        assert result["passed"] is False
        assert any("fabricated skill" in e.lower() and "django" in e.lower() for e in result["errors"])

    def test_company_missing(self):
        data = dict(SAMPLE_JSON_DATA)
        data["experience"] = [{"header": "Other Corp", "bullets": ["did stuff"]}]
        result = validate_json_fields(data, SAMPLE_PROFILE)
        assert result["passed"] is False
        assert any("Acme Corp" in e for e in result["errors"])

    def test_banned_words_strict_mode(self):
        data = dict(SAMPLE_JSON_DATA)
        data["summary"] = "I am passionate about building scalable solutions."
        result = validate_json_fields(data, SAMPLE_PROFILE, mode="strict")
        assert result["passed"] is False
        assert any("Banned words" in e for e in result["errors"])

    def test_banned_words_normal_mode_is_warning(self):
        data = dict(SAMPLE_JSON_DATA)
        data["summary"] = "I am passionate about building scalable solutions."
        result = validate_json_fields(data, SAMPLE_PROFILE, mode="normal")
        assert result["passed"] is True
        assert any("Banned words" in w for w in result["warnings"])

    def test_banned_words_lenient_mode_ignored(self):
        data = dict(SAMPLE_JSON_DATA)
        data["summary"] = "I am passionate about building scalable solutions."
        result = validate_json_fields(data, SAMPLE_PROFILE, mode="lenient")
        assert result["passed"] is True
        assert len(result["warnings"]) == 0

    def test_llm_leak_always_error(self):
        data = dict(SAMPLE_JSON_DATA)
        data["summary"] = "I am sorry for the inconvenience. Here is the revised version."
        for mode in ("strict", "normal", "lenient"):
            result = validate_json_fields(data, SAMPLE_PROFILE, mode=mode)
            assert result["passed"] is False
            assert any("LLM self-talk" in e for e in result["errors"])

    def test_school_missing(self):
        data = dict(SAMPLE_JSON_DATA)
        data["education"] = "B.S. Computer Science, Stanford"
        result = validate_json_fields(data, SAMPLE_PROFILE)
        assert result["passed"] is False
        assert any("MIT" in e for e in result["errors"])


# ── validate_cover_letter ──────────────────────────────────────────────


class TestValidateCoverLetter:
    def test_valid_letter_passes(self):
        letter = "Dear Hiring Manager,\n\nI am writing to express my interest in the role."
        result = validate_cover_letter(letter)
        assert result["passed"] is True

    def test_must_start_with_dear(self):
        letter = "Hello,\n\nI am writing to express my interest."
        result = validate_cover_letter(letter)
        assert result["passed"] is False
        assert any("Dear" in e for e in result["errors"])

    def test_em_dash_is_error(self):
        letter = "Dear Hiring Manager,\n\nI have experience \u2014 three years."
        result = validate_cover_letter(letter)
        assert result["passed"] is False
        assert any("dash" in e.lower() for e in result["errors"])

    def test_llm_leak_is_error(self):
        letter = "Dear Hiring Manager,\n\nI am sorry for the delay in my response."
        result = validate_cover_letter(letter)
        assert result["passed"] is False
        assert any("LLM self-talk" in e for e in result["errors"])

    def test_banned_words_strict(self):
        letter = "Dear Hiring Manager,\n\n" + " ".join(["passionate"] * 50)
        result = validate_cover_letter(letter, mode="strict")
        assert result["passed"] is False
        assert any("Banned words" in e for e in result["errors"])

    def test_banned_words_normal_is_warning(self):
        letter = "Dear Hiring Manager,\n\n" + " ".join(["passionate"] * 50)
        result = validate_cover_letter(letter, mode="normal")
        assert result["passed"] is True
        assert any("Banned words" in w for w in result["warnings"])

    def test_word_count_strict(self):
        letter = "Dear Hiring Manager,\n\n" + "word " * 260
        result = validate_cover_letter(letter, mode="strict")
        assert result["passed"] is False
        assert any("Too long" in e for e in result["errors"])

    def test_word_count_normal_warning(self):
        letter = "Dear Hiring Manager,\n\n" + "word " * 280
        result = validate_cover_letter(letter, mode="normal")
        assert result["passed"] is True
        assert any("Long" in w for w in result["warnings"])

    def test_word_count_lenient_no_check(self):
        letter = "Dear Hiring Manager,\n\n" + "word " * 500
        result = validate_cover_letter(letter, mode="lenient")
        assert result["passed"] is True


# ── validate_tailored_resume ───────────────────────────────────────────


class TestValidateTailoredResume:
    VALID_RESUME = """Jane Doe
Senior Python Engineer
New York, NY
jane@example.com | 555-1234

SUMMARY
Experienced engineer with 5 years building web services.

TECHNICAL SKILLS
Languages: Python, JavaScript
Frameworks: FastAPI, React
Tools: Docker, PostgreSQL

EXPERIENCE
Acme Corp - Senior Engineer
- Built data pipelines processing 1M events/day
- Led migration from monolith to microservices

PROJECTS
Project Alpha
- Open source data visualization tool

EDUCATION
B.S. Computer Science, MIT
"""

    def test_valid_resume_passes(self):
        result = validate_tailored_resume(self.VALID_RESUME, SAMPLE_PROFILE)
        assert result["passed"] is True

    def test_missing_name_warning(self):
        text = self.VALID_RESUME.replace("Jane Doe", "John Smith")
        result = validate_tailored_resume(text, SAMPLE_PROFILE)
        assert any("Jane Doe" in w for w in result["warnings"])

    def test_missing_company_error(self):
        text = self.VALID_RESUME.replace("Acme Corp", "Other Corp")
        result = validate_tailored_resume(text, SAMPLE_PROFILE)
        assert result["passed"] is False
        assert any("Acme Corp" in e for e in result["errors"])

    def test_missing_school_error(self):
        text = self.VALID_RESUME.replace("MIT", "Stanford")
        result = validate_tailored_resume(text, SAMPLE_PROFILE)
        assert result["passed"] is False
        assert any("MIT" in e for e in result["errors"])

    def test_missing_section_error(self):
        text = self.VALID_RESUME.replace("TECHNICAL SKILLS", "MY CUSTOM SECTION")
        result = validate_tailored_resume(text, SAMPLE_PROFILE)
        assert result["passed"] is False
        assert any("Missing required section" in e for e in result["errors"])

    def test_em_dash_error(self):
        text = self.VALID_RESUME.replace("1M events/day", "1M events \u2014 day")
        result = validate_tailored_resume(text, SAMPLE_PROFILE)
        assert result["passed"] is False
        assert any("dash" in e.lower() for e in result["errors"])

    def test_banned_words_error(self):
        text = self.VALID_RESUME.replace("Experienced engineer", "passionate and dedicated engineer")
        result = validate_tailored_resume(text, SAMPLE_PROFILE)
        assert result["passed"] is False
        assert any("Banned words" in e for e in result["errors"])

    def test_llm_leak_error(self):
        text = self.VALID_RESUME + "\n\nI am sorry for any issues."
        result = validate_tailored_resume(text, SAMPLE_PROFILE)
        assert result["passed"] is False
        assert any("LLM self-talk" in e for e in result["errors"])

    def test_fabricated_skill_in_skills_section(self):
        text = self.VALID_RESUME.replace(
            "Tools: Docker, PostgreSQL",
            "Tools: Docker, Django, PostgreSQL",
        )
        result = validate_tailored_resume(text, SAMPLE_PROFILE)
        assert result["passed"] is False
        assert any("django" in e.lower() for e in result["errors"])

    def test_new_tool_warning_when_comparing_to_original(self):
        original = "Python JavaScript Docker"
        text = self.VALID_RESUME.replace("FastAPI", "FastAPI, Django")
        result = validate_tailored_resume(text, SAMPLE_PROFILE, original_text=original)
        assert any("django" in w.lower() for w in result["warnings"])
