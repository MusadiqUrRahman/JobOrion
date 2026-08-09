"""Tests for field-agnostic search query extraction."""

from joborion.agent.query import extract_query


class TestExtractQuery:
    def test_strips_fillers_and_limits(self):
        assert extract_query("Find 10 remote accountant jobs") == "accountant"

    def test_keeps_seniority_level(self):
        query = extract_query("search senior data analyst roles")
        assert "senior" in query
        assert "data analyst" in query

    def test_non_tech_field(self):
        assert extract_query("find nursing jobs") == "nursing"
        assert extract_query("find graphic designer jobs") == "graphic designer"

    def test_strips_salary_figure(self):
        assert extract_query("find python jobs paying 150k") == "python"

    def test_strips_standalone_numbers(self):
        assert extract_query("find 3 electrician jobs") == "electrician"

    def test_filler_only_returns_empty(self, monkeypatch):
        monkeypatch.setattr("joborion.agent.query._profile_target_role", lambda: "")
        assert extract_query("find me some jobs") == ""

    def test_explicit_fallback_used_when_empty(self):
        assert extract_query("find me some jobs", fallback="Accountant") == "Accountant"

    def test_profile_target_role_fallback(self, monkeypatch):
        monkeypatch.setattr("joborion.agent.query._profile_target_role", lambda: "Nurse")
        assert extract_query("find some jobs") == "Nurse"

    def test_arbitrary_text_becomes_query(self):
        assert extract_query("hello world") == "hello world"

    def test_remote_only_goal_keeps_role(self):
        assert extract_query("remote wfh design jobs") == "design"
