"""Tests for joborion.wizard.preferences — the 4-question preference wizard."""

import yaml
import pytest
from unittest.mock import patch

from joborion.wizard.preferences import (
    DEFAULT_PREFERENCES,
    load_preferences,
    run_preferences_wizard,
    save_preferences,
    validate,
    apply_flags,
)


class TestPreferencesWizard:
    def test_writes_yaml_with_answers(self, tmp_path):
        with patch("joborion.wizard.preferences.Prompt.ask", side_effect=[
            "remote", "worldwide", "fulltime", "60000", "mid, senior", "software, ai",
        ]), patch("joborion.wizard.preferences.Confirm.ask", return_value=True):
            prefs = run_preferences_wizard()

        prefs_path = tmp_path / "preferences.yaml"
        save_preferences(prefs, prefs_path)

        saved = yaml.safe_load(prefs_path.read_text(encoding="utf-8"))
        assert saved["arrangement"] == "remote"
        assert saved["locations"] == ["worldwide"]
        assert saved["job_types"] == ["fulltime"]
        assert saved["min_salary"] == 60000
        assert saved["seniority"] == ["mid", "senior"]
        assert saved["sponsorship_ok"] is True
        assert saved["industries"] == ["software", "ai"]

    def test_prefills_existing_answers(self):
        existing = {
            "arrangement": "hybrid",
            "locations": ["canada", "germany"],
            "job_types": ["fulltime"],
            "min_salary": 80000,
            "seniority": ["senior"],
            "sponsorship_ok": False,
            "industries": ["finance"],
        }
        defaults_seen: list[str] = []

        def fake_ask(prompt, **kwargs):
            defaults_seen.append(kwargs.get("default", ""))
            return kwargs.get("default") or "all"

        with patch("joborion.wizard.preferences.Prompt.ask", side_effect=fake_ask), \
             patch("joborion.wizard.preferences.Confirm.ask", return_value=True):
            prefs = run_preferences_wizard(existing)

        assert prefs["arrangement"] == "hybrid"
        assert prefs["min_salary"] == 80000
        assert "hybrid" in defaults_seen


class TestPreferencesValidation:
    def test_accepts_valid_preferences(self):
        assert validate(DEFAULT_PREFERENCES) == []

    def test_rejects_bad_arrangement(self):
        errors = validate({"arrangement": "sideways"})
        assert any("arrangement" in e for e in errors)

    def test_rejects_negative_min_salary(self):
        errors = validate({"arrangement": "all", "min_salary": -5})
        assert any("min_salary" in e for e in errors)


class TestPreferencesLoadSave:
    def test_load_missing_returns_defaults(self, tmp_path):
        missing = tmp_path / "nope.yaml"
        assert load_preferences(missing) == DEFAULT_PREFERENCES

    def test_roundtrip(self, tmp_path):
        prefs_path = tmp_path / "preferences.yaml"
        save_preferences(
            {"arrangement": "remote", "locations": ["worldwide"], "job_types": ["all"]},
            prefs_path,
        )
        loaded = load_preferences(prefs_path)
        assert loaded["arrangement"] == "remote"
        assert loaded["min_salary"] is None

    def test_load_invalid_raises(self, tmp_path):
        prefs_path = tmp_path / "preferences.yaml"
        prefs_path.write_text("arrangement: banana\n", encoding="utf-8")
        with pytest.raises(ValueError):
            load_preferences(prefs_path)


class TestApplyFlags:
    def test_overrides_only_provided_fields(self):
        prefs = apply_flags(
            {"arrangement": "all", "locations": ["worldwide"], "job_types": ["all"]},
            arrangement="remote",
            locations="US, GB",
            min_salary=70000,
        )
        assert prefs["arrangement"] == "remote"
        assert prefs["locations"] == ["us", "gb"]
        assert prefs["min_salary"] == 70000
        assert prefs["job_types"] == ["all"]

    def test_blank_locations_fall_back_to_worldwide(self):
        prefs = apply_flags({"arrangement": "all"}, locations="")
        assert prefs["locations"] == ["worldwide"]
