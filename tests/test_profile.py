"""Tests for multi-profile workspace isolation."""

import pytest
from typer.testing import CliRunner

import joborion.config as config


@pytest.fixture(autouse=True)
def isolated_app_dir(monkeypatch, tmp_path):
    """Point APP_DIR at a temp dir and reset profile state after each test."""
    config.reset_profile()
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    monkeypatch.delenv("JOBORION_PROFILE", raising=False)
    config.reset_profile()
    yield
    config.reset_profile()


class TestConfigProfile:
    def test_set_profile_rebinds_paths(self):
        config.set_profile("a")
        assert config.get_profile() == "a"
        assert config.get_profile_dir() == config.APP_DIR / "profiles" / "a"
        assert config.DB_PATH == config.APP_DIR / "profiles" / "a" / "joborion.db"
        assert config.RESUME_PATH == config.APP_DIR / "profiles" / "a" / "resume.txt"
        assert config.TAILORED_DIR == config.APP_DIR / "profiles" / "a" / "tailored_resumes"
        assert config.SEARCH_CONFIG_PATH == config.APP_DIR / "profiles" / "a" / "searches.yaml"

    def test_set_profile_none_restores_defaults(self):
        config.set_profile("a")
        config.set_profile(None)
        assert config.get_profile() is None
        assert config.DB_PATH == config.APP_DIR / "joborion.db"

    def test_get_profile_dir_default(self):
        assert config.get_profile() is None
        assert config.get_profile_dir() == config.APP_DIR

    @pytest.mark.parametrize(
        "name",
        ["", ".", "..", "../x", "a/b", "a\\b", "a b"],
    )
    def test_invalid_names_raise(self, name):
        with pytest.raises(ValueError):
            config.set_profile(name)

    def test_valid_names(self):
        for name in ("a", "A", "my-job", "my_job", "a.b", "x-1"):
            config.set_profile(name)
            assert config.get_profile() == name

    def test_list_profiles_includes_default(self):
        assert config.list_profiles() == ["default"]
        (config.APP_DIR / "profiles" / "work").mkdir(parents=True)
        (config.APP_DIR / "profiles" / "search").mkdir(parents=True)
        assert config.list_profiles() == ["default", "search", "work"]


class TestProfileCLI:
    def invoke(self, *args):
        from joborion.cli import app

        return CliRunner().invoke(app, list(args))

    def test_create_profile(self):
        result = self.invoke("profile", "create", "work")
        assert result.exit_code == 0
        assert (config.APP_DIR / "profiles" / "work").is_dir()
        assert (config.APP_DIR / "profiles" / "work" / "tailored_resumes").is_dir()

    def test_create_again_is_idempotent(self):
        assert self.invoke("profile", "create", "work").exit_code == 0
        assert self.invoke("profile", "create", "work").exit_code == 0

    def test_create_invalid_name(self):
        result = self.invoke("profile", "create", "../evil")
        assert result.exit_code != 0
        assert "Profile names" in result.output

    def test_list_shows_profiles(self):
        self.invoke("profile", "create", "work")
        result = self.invoke("profile", "list")
        assert result.exit_code == 0
        assert "work" in result.output
        assert "default" in result.output

    def test_status_with_profile_is_isolated(self):
        result = self.invoke("--profile", "work", "status")
        assert result.exit_code == 0
        assert (config.APP_DIR / "profiles" / "work" / "joborion.db").exists()
        assert not (config.APP_DIR / "joborion.db").exists()

    def test_status_default_uses_root(self):
        result = self.invoke("status")
        assert result.exit_code == 0
        assert (config.APP_DIR / "joborion.db").exists()
        assert not (config.APP_DIR / "profiles" / "work" / "joborion.db").exists()

    def test_invalid_profile_flag_exits_nonzero(self):
        result = self.invoke("--profile", "../evil", "status")
        assert result.exit_code != 0
        assert "Profile names" in result.output

    def test_profile_list_marks_active(self):
        result = self.invoke("--profile", "work", "profile", "list")
        assert result.exit_code == 0
        assert "work *" in result.output

    def test_run_flag_declared(self, cli_flags):
        import inspect

        from joborion.cli import main

        param = inspect.signature(main).parameters["profile"]
        assert "--profile" in param.default.param_decls
