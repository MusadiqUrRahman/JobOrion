"""Tests for GoalParser — natural language goal parsing."""

from joborion.agent.goal_parser import GoalParser


class TestGoalParser:
    def setup_method(self):
        self.parser = GoalParser()

    def test_parse_basic_goal(self):
        result = self.parser.parse("Find Python jobs")
        assert result["query"] == "python"
        assert result["actions"]["search"] is True

    def test_extract_query_multiple_techs(self):
        result = self.parser.parse("Find Python and React jobs")
        assert "python" in result["query"]
        assert "react" in result["query"]

    def test_extract_query_no_match(self):
        result = self.parser.parse("Find jobs")
        assert result["query"] == ""

    def test_extract_remote_filter(self):
        result = self.parser.parse("Find remote Python jobs")
        assert result["filters"]["remote"] is True

    def test_extract_wfh_filter(self):
        result = self.parser.parse("Find work from home Python jobs")
        assert result["filters"]["remote"] is True

    def test_extract_salary_filter_k(self):
        result = self.parser.parse("Find Python jobs paying 150k")
        assert result["filters"]["min_salary"] == 150000

    def test_extract_salary_filter_dollar(self):
        result = self.parser.parse("Find Python jobs paying $100k+")
        assert result["filters"]["min_salary"] == 100000

    def test_extract_min_score_high(self):
        result = self.parser.parse("Find best Python jobs")
        assert result["filters"]["min_score"] == 8

    def test_extract_min_score_good(self):
        result = self.parser.parse("Find good Python jobs")
        assert result["filters"]["min_score"] == 7

    def test_extract_actions_tailor(self):
        result = self.parser.parse("Find and tailor resume for Python jobs")
        assert result["actions"]["tailor"] is True
        assert result["actions"]["letter"] is True
        assert result["actions"]["export"] is True

    def test_extract_actions_apply(self):
        result = self.parser.parse("Find and apply to Python jobs")
        assert all(result["actions"].values())

    def test_extract_actions_default(self):
        result = self.parser.parse("Find Python jobs")
        assert result["actions"]["search"] is True
        assert result["actions"]["details"] is True
        assert result["actions"]["evaluate"] is True
        assert result["actions"]["tailor"] is False

    def test_extract_limits_find(self):
        result = self.parser.parse("Find 10 Python jobs")
        assert result["limits"]["max_jobs"] == 10

    def test_extract_limits_apply(self):
        result = self.parser.parse("Find Python jobs and apply to 5")
        assert result["limits"]["max_applications"] == 5

    def test_extract_limits_top(self):
        result = self.parser.parse("Find Python jobs, apply to top 3")
        assert result["limits"]["max_applications"] == 3

    def test_no_match_defaults(self):
        result = self.parser.parse("hello world")
        assert result["query"] == ""
        assert result["filters"]["remote"] is False
        assert result["filters"]["min_salary"] is None
        assert result["limits"]["max_jobs"] is None
