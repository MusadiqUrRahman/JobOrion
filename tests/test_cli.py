"""Tests for joborion.cli — configure command and preference-driven run search."""

import json
import yaml
from unittest.mock import patch

from typer.testing import CliRunner

from joborion.cli import app

runner = CliRunner()


class TestRunAutonomousFlag:
    def test_run_declares_autonomous_flag(self, cli_flags):
        assert "--autonomous" in cli_flags["run"]

    def test_run_keeps_agentic_alias(self, cli_flags):
        assert "--agentic" in cli_flags["run"]


class TestConfigureCommand:
    def test_configure_runs_wizard_and_writes_preferences(self, tmp_path):
        profile = {"experience": {"target_role": "Backend Engineer"}}
        profile_path = tmp_path / "profile.json"
        profile_path.write_text(json.dumps(profile), encoding="utf-8")

        with patch("joborion.config.PREFERENCES_PATH", tmp_path / "preferences.yaml"), \
             patch("joborion.config.PROFILE_PATH", profile_path), \
             patch("joborion.database.DB_PATH", tmp_path / "joborion.db"), \
             patch("joborion.wizard.preferences.Prompt.ask", side_effect=[
                 "remote", "worldwide", "fulltime", "60000", "mid, senior", "software, ai",
             ]), \
             patch("joborion.wizard.preferences.Confirm.ask", return_value=True):
            result = runner.invoke(app, ["configure"])

        assert result.exit_code == 0
        saved = yaml.safe_load((tmp_path / "preferences.yaml").read_text(encoding="utf-8"))
        assert saved["arrangement"] == "remote"
        assert saved["min_salary"] == 60000


class TestRunSearchPreferencesHook:
    def test_run_search_prompts_when_no_preferences(self, tmp_path):
        with patch("joborion.config.PREFERENCES_PATH", tmp_path / "preferences.yaml"), \
             patch("joborion.database.DB_PATH", tmp_path / "joborion.db"), \
             patch("joborion.config.load_profile",
                   return_value={"experience": {"target_role": "Backend Engineer"}}), \
             patch("joborion.wizard.preferences.Prompt.ask", side_effect=[
                 "remote", "worldwide", "fulltime", "60000", "mid, senior", "software, ai",
             ]), \
             patch("joborion.wizard.preferences.Confirm.ask", return_value=True), \
             patch("joborion.pipeline.run_pipeline",
                   return_value={"stages": [], "errors": {}}) as mock_pipeline:
            result = runner.invoke(app, ["run", "search"])

        assert result.exit_code == 0
        assert (tmp_path / "preferences.yaml").exists()
        mock_pipeline.assert_called_once()

    def test_run_search_refuses_without_target_role(self, tmp_path):
        with patch("joborion.config.PREFERENCES_PATH", tmp_path / "preferences.yaml"), \
             patch("joborion.database.DB_PATH", tmp_path / "joborion.db"), \
             patch("joborion.config.load_profile",
                   return_value={"experience": {"target_role": ""}}), \
             patch("joborion.pipeline.run_pipeline") as mock_pipeline:
            result = runner.invoke(app, ["run", "search", "--no-ask"])

        assert result.exit_code != 0
        mock_pipeline.assert_not_called()

    def test_run_search_no_ask_skips_prompt(self, tmp_path):
        (tmp_path / "preferences.yaml").write_text(
            yaml.safe_dump({"arrangement": "remote"}), encoding="utf-8",
        )
        with patch("joborion.config.PREFERENCES_PATH", tmp_path / "preferences.yaml"), \
             patch("joborion.database.DB_PATH", tmp_path / "joborion.db"), \
             patch("joborion.config.load_profile",
                   return_value={"experience": {"target_role": "ML Engineer"}}), \
             patch("joborion.wizard.preferences.run_preferences_wizard") as mock_wizard, \
             patch("joborion.pipeline.run_pipeline",
                   return_value={"stages": [], "errors": {}}) as mock_pipeline:
            result = runner.invoke(app, ["run", "search", "--no-ask"])

        assert result.exit_code == 0
        mock_wizard.assert_not_called()
        mock_pipeline.assert_called_once()

    def test_run_search_uses_flag_mode(self, tmp_path):
        with patch("joborion.config.PREFERENCES_PATH", tmp_path / "preferences.yaml"), \
             patch("joborion.database.DB_PATH", tmp_path / "joborion.db"), \
             patch("joborion.config.load_profile",
                   return_value={"experience": {"target_role": "Data Engineer"}}), \
             patch("joborion.wizard.preferences.run_preferences_wizard") as mock_wizard, \
             patch("joborion.pipeline.run_pipeline",
                   return_value={"stages": [], "errors": {}}) as mock_pipeline:
            result = runner.invoke(
                app, ["run", "search", "--arrangement", "remote", "--min-salary", "50000"],
            )

        assert result.exit_code == 0
        mock_wizard.assert_not_called()
        assert mock_pipeline.call_args.kwargs["mode"] == "remote"
