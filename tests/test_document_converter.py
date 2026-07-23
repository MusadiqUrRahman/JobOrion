"""Tests for joborion.scoring.document_converter — resume parsing and HTML generation."""

import pytest
from joborion.scoring.document_converter import (
    parse_resume,
    parse_skills,
    parse_entries,
    build_html,
)

SAMPLE_RESUME = """\
Jane Doe
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
Acme Corp — Senior Engineer
Jan 2022 - Present
- Built data pipelines processing 1M events/day
- Led migration from monolith to microservices

B Corp — Software Engineer
Jun 2020 - Dec 2021
- Designed REST APIs serving 10K requests/sec

PROJECTS
Project Alpha
- Open source data visualization tool
- 500+ GitHub stars

EDUCATION
B.S. Computer Science, MIT
"""


# ── parse_resume ───────────────────────────────────────────────────────


class TestParseResume:
    def test_name_extracted(self):
        result = parse_resume(SAMPLE_RESUME)
        assert result["name"] == "Jane Doe"

    def test_title_extracted(self):
        result = parse_resume(SAMPLE_RESUME)
        assert result["title"] == "Senior Python Engineer"

    def test_location_extracted(self):
        result = parse_resume(SAMPLE_RESUME)
        assert result["location"] == "New York, NY"

    def test_contact_extracted(self):
        result = parse_resume(SAMPLE_RESUME)
        assert "jane@example.com" in result["contact"]

    def test_sections_present(self):
        result = parse_resume(SAMPLE_RESUME)
        sections = result["sections"]
        assert "SUMMARY" in sections
        assert "TECHNICAL SKILLS" in sections
        assert "EXPERIENCE" in sections
        assert "PROJECTS" in sections
        assert "EDUCATION" in sections

    def test_summary_content(self):
        result = parse_resume(SAMPLE_RESUME)
        assert "5 years" in result["sections"]["SUMMARY"]

    def test_experience_content(self):
        result = parse_resume(SAMPLE_RESUME)
        assert "Acme Corp" in result["sections"]["EXPERIENCE"]

    def test_empty_input(self):
        result = parse_resume("")
        assert result["name"] == ""
        assert result["title"] == ""
        assert result["sections"] == {}

    def test_no_sections(self):
        text = "John Doe\nSoftware Engineer\n"
        result = parse_resume(text)
        assert result["name"] == "John Doe"
        assert result["sections"] == {}

    def test_header_with_only_name_and_title(self):
        text = "Jane Doe\nEngineer\n\nSUMMARY\nExperienced."
        result = parse_resume(text)
        assert result["name"] == "Jane Doe"
        assert result["title"] == "Engineer"
        assert result["location"] == ""
        assert result["contact"] == ""

    def test_header_with_email_in_third_line(self):
        text = "Jane Doe\nEngineer\njane@example.com\n\nSUMMARY\nExperienced."
        result = parse_resume(text)
        assert result["contact"] == "jane@example.com"
        assert result["location"] == ""

    def test_multiple_sections(self):
        text = "Jane Doe\nEngineer\n\nSUMMARY\nStuff\n\nEXPERIENCE\nWork\n\nEDUCATION\nMIT"
        result = parse_resume(text)
        assert len(result["sections"]) == 3


# ── parse_skills ───────────────────────────────────────────────────────


class TestParseSkills:
    def test_basic_skills(self):
        text = "Languages: Python, JavaScript\nFrameworks: FastAPI, React"
        result = parse_skills(text)
        assert len(result) == 2
        assert result[0] == ("Languages", "Python, JavaScript")
        assert result[1] == ("Frameworks", "FastAPI, React")

    def test_empty_input(self):
        result = parse_skills("")
        assert result == []

    def test_colon_in_value(self):
        text = "Tools: Docker: advanced, PostgreSQL"
        result = parse_skills(text)
        assert result[0] == ("Tools", "Docker: advanced, PostgreSQL")

    def test_single_skill(self):
        text = "Cloud: AWS"
        result = parse_skills(text)
        assert result == [("Cloud", "AWS")]


# ── parse_entries ──────────────────────────────────────────────────────


class TestParseEntries:
    def test_basic_entries(self):
        text = "Acme Corp — Senior Engineer\n- Built pipelines\n- Led migration"
        result = parse_entries(text)
        assert len(result) == 1
        assert result[0]["title"] == "Acme Corp — Senior Engineer"
        assert len(result[0]["bullets"]) == 2

    def test_multiple_entries(self):
        text = (
            "Acme Corp — Senior\n- Did stuff\n\n"
            "B Corp — Engineer\n- Built things"
        )
        result = parse_entries(text)
        assert len(result) == 2

    def test_empty_input(self):
        result = parse_entries("")
        assert result == []

    def test_entry_with_subtitle(self):
        text = "Acme Corp\nSenior Engineer\n- Built stuff"
        result = parse_entries(text)
        assert result[0]["subtitle"] == "Senior Engineer"

    def test_bullet_points(self):
        text = "My Project\n- Point one\n- Point two\n- Point three"
        result = parse_entries(text)
        assert len(result) >= 1
        assert len(result[0]["bullets"]) == 3

    def test_unicode_bullet(self):
        text = "My Project\n\u2022 Point one\n\u2022 Point two"
        result = parse_entries(text)
        assert len(result) >= 1
        assert len(result[0]["bullets"]) == 2


# ── build_html ─────────────────────────────────────────────────────────


class TestBuildHtml:
    def test_produces_valid_html(self):
        resume = parse_resume(SAMPLE_RESUME)
        html = build_html(resume)
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html

    def test_contains_name(self):
        resume = parse_resume(SAMPLE_RESUME)
        html = build_html(resume)
        assert "Jane Doe" in html

    def test_contains_title(self):
        resume = parse_resume(SAMPLE_RESUME)
        html = build_html(resume)
        assert "Senior Python Engineer" in html

    def test_contains_skills(self):
        resume = parse_resume(SAMPLE_RESUME)
        html = build_html(resume)
        assert "Python" in html
        assert "JavaScript" in html

    def test_contains_experience(self):
        resume = parse_resume(SAMPLE_RESUME)
        html = build_html(resume)
        assert "Acme Corp" in html
        assert "data pipelines" in html

    def test_contains_projects(self):
        resume = parse_resume(SAMPLE_RESUME)
        html = build_html(resume)
        assert "Project Alpha" in html
        assert "GitHub stars" in html

    def test_contains_education(self):
        resume = parse_resume(SAMPLE_RESUME)
        html = build_html(resume)
        assert "MIT" in html

    def test_empty_resume_produces_html(self):
        resume = parse_resume("")
        html = build_html(resume)
        assert "<!DOCTYPE html>" in html

    def test_contact_pipe_separator(self):
        resume = parse_resume(SAMPLE_RESUME)
        html = build_html(resume)
        assert "|&nbsp;" in html or "555-1234" in html

    def test_location_rendered(self):
        resume = parse_resume(SAMPLE_RESUME)
        html = build_html(resume)
        assert "New York, NY" in html

    def test_section_titles_present(self):
        resume = parse_resume(SAMPLE_RESUME)
        html = build_html(resume)
        assert "Technical Skills" in html
        assert "Experience" in html
        assert "Projects" in html
        assert "Education" in html
        assert "Summary" in html
