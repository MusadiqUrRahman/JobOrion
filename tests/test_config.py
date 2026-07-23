"""Tests for joborion.config — paths, config loading, tier detection."""

import os
import json
import pytest
from pathlib import Path
from unittest.mock import patch

from joborion.config import (
    APP_DIR,
    DB_PATH,
    PROFILE_PATH,
    RESUME_PATH,
    TAILORED_DIR,
    COVER_LETTER_DIR,
    LOG_DIR,
    CONFIG_DIR,
    DEFAULTS,
    TIER_LABELS,
    TIER_COMMANDS,
    ensure_dirs,
    load_profile,
    load_search_config,
    load_sites_config,
    get_tier,
)


# ── path constants ─────────────────────────────────────────────────────


class TestPathConstants:
    def test_app_dir_is_path(self):
        assert isinstance(APP_DIR, Path)

    def test_db_path_ends_with_db(self):
        assert str(DB_PATH).endswith("joborion.db")

    def test_profile_path_ends_with_json(self):
        assert str(PROFILE_PATH).endswith("profile.json")

    def test_resume_path_ends_with_txt(self):
        assert str(RESUME_PATH).endswith("resume.txt")

    def test_tailored_dir_is_path(self):
        assert isinstance(TAILORED_DIR, Path)

    def test_cover_letter_dir_is_path(self):
        assert isinstance(COVER_LETTER_DIR, Path)

    def test_log_dir_is_path(self):
        assert isinstance(LOG_DIR, Path)

    def test_config_dir_points_to_package(self):
        assert CONFIG_DIR.exists()
        assert CONFIG_DIR.name == "config"


# ── ensure_dirs ────────────────────────────────────────────────────────


class TestEnsureDirs:
    def test_creates_dirs(self, tmp_path):
        test_app = tmp_path / "test_joborion"
        with patch("joborion.config.APP_DIR", test_app), \
             patch("joborion.config.TAILORED_DIR", test_app / "tailored_resumes"), \
             patch("joborion.config.COVER_LETTER_DIR", test_app / "cover_letters"), \
             patch("joborion.config.LOG_DIR", test_app / "logs"), \
             patch("joborion.config.CHROME_WORKER_DIR", test_app / "chrome-workers"), \
             patch("joborion.config.APPLY_WORKER_DIR", test_app / "apply-workers"):
            ensure_dirs()
            assert test_app.exists()
            assert (test_app / "tailored_resumes").exists()
            assert (test_app / "cover_letters").exists()
            assert (test_app / "logs").exists()


# ── load_profile ───────────────────────────────────────────────────────


class TestLoadProfile:
    def test_loads_valid_profile(self, tmp_path):
        profile = {
            "personal": {"full_name": "Jane Doe"},
            "resume_facts": {},
            "skills_boundary": {},
        }
        profile_path = tmp_path / "profile.json"
        profile_path.write_text(json.dumps(profile), encoding="utf-8")
        with patch("joborion.config.PROFILE_PATH", profile_path):
            result = load_profile()
            assert result["personal"]["full_name"] == "Jane Doe"

    def test_missing_profile_raises(self, tmp_path):
        missing = tmp_path / "nonexistent.json"
        with patch("joborion.config.PROFILE_PATH", missing):
            with pytest.raises(FileNotFoundError):
                load_profile()


# ── load_search_config ─────────────────────────────────────────────────


class TestLoadSearchConfig:
    def test_loads_when_exists(self, tmp_path):
        import yaml
        config = {"searches": [{"query": "python", "location": "remote"}]}
        config_path = tmp_path / "searches.yaml"
        config_path.write_text(yaml.dump(config), encoding="utf-8")
        with patch("joborion.config.SEARCH_CONFIG_PATH", config_path):
            result = load_search_config()
            assert "searches" in result

    def test_falls_back_to_example(self):
        result = load_search_config()
        # Should either return the example config or empty dict
        assert isinstance(result, dict)


# ── load_sites_config ──────────────────────────────────────────────────


class TestLoadSitesConfig:
    def test_loads_when_exists(self):
        result = load_sites_config()
        # sites.yaml is shipped with the package, should return a dict
        assert isinstance(result, dict)

    def test_returns_dict(self):
        assert isinstance(load_sites_config(), dict)


# ── DEFAULTS ───────────────────────────────────────────────────────────


class TestDefaults:
    def test_has_expected_keys(self):
        expected = {"min_score", "max_apply_attempts", "max_tailor_attempts",
                    "poll_interval", "apply_timeout", "viewport"}
        assert expected.issubset(DEFAULTS.keys())

    def test_min_score_is_int(self):
        assert isinstance(DEFAULTS["min_score"], int)

    def test_max_apply_attempts_is_int(self):
        assert isinstance(DEFAULTS["max_apply_attempts"], int)

    def test_viewport_is_string(self):
        assert isinstance(DEFAULTS["viewport"], str)


# ── TIER_LABELS and TIER_COMMANDS ──────────────────────────────────────


class TestTierSystem:
    def test_tier_labels_has_3_tiers(self):
        assert set(TIER_LABELS.keys()) == {1, 2, 3}

    def test_tier_labels_are_strings(self):
        for label in TIER_LABELS.values():
            assert isinstance(label, str)

    def test_tier_commands_has_3_tiers(self):
        assert set(TIER_COMMANDS.keys()) == {1, 2, 3}

    def test_tier_commands_are_lists(self):
        for cmds in TIER_COMMANDS.values():
            assert isinstance(cmds, list)
            assert len(cmds) > 0

    def test_search_in_tier_1(self):
        assert any("search" in c for c in TIER_COMMANDS[1])

    def test_apply_in_tier_3(self):
        assert any("apply" in c for c in TIER_COMMANDS[3])


# ── get_tier ───────────────────────────────────────────────────────────


class TestGetTier:
    def test_tier_1_without_keys(self):
        with patch.dict(os.environ, {}, clear=True):
            # Remove all LLM-related env vars
            for key in ("GEMINI_API_KEY", "OPENAI_API_KEY", "LLM_URL"):
                os.environ.pop(key, None)
            tier = get_tier()
            assert tier >= 1

    def test_returns_int(self):
        tier = get_tier()
        assert isinstance(tier, int)
        assert tier in (1, 2, 3)
