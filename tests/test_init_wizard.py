"""Tests for the first-time setup wizard — target role requirement."""

from unittest.mock import patch

from joborion.wizard.init import _prompt_target_role


class TestTargetRoleRequired:
    def test_blank_target_role_reprompts(self):
        with patch("joborion.wizard.init.Prompt.ask", side_effect=["", "", "Backend Engineer"]):
            role = _prompt_target_role({}, "Python Dev")
        assert role == "Backend Engineer"

    def test_nonblank_returns_immediately(self):
        with patch("joborion.wizard.init.Prompt.ask", return_value="ML Engineer"):
            role = _prompt_target_role({}, "")
        assert role == "ML Engineer"

    def test_whitespace_only_reprompts(self):
        with patch("joborion.wizard.init.Prompt.ask", side_effect=["   ", "Data Analyst"]):
            role = _prompt_target_role({}, "")
        assert role == "Data Analyst"
