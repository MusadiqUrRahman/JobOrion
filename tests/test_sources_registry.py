"""Tests for joborion.sources.registry — provider config, ordering, execution."""

from unittest.mock import patch

from joborion.sources.base import ProviderResult
from joborion.sources.registry import (
    build_providers,
    enabled_providers,
    load_sources_config,
    run_providers,
)


CONFIG = {
    "providers": {
        "jobspy": {"enabled": True, "priority": 10},
        "workday": {"enabled": True, "priority": 20},
        "adzuna": {"enabled": False, "priority": 30},
    }
}


class _FakeProvider:
    name = "fake"

    def __init__(self, cfg=None):
        self.cfg = cfg or {}
        self.calls = 0

    def search(self, intent):
        self.calls += 1
        return ProviderResult(provider=self.name, found=3, stored=2)


class _BrokenProvider:
    name = "broken"

    def search(self, intent):
        raise RuntimeError("boom")


class TestRegistry:
    def test_loads_config(self):
        cfg = load_sources_config()
        assert "providers" in cfg
        assert "jobspy" in cfg["providers"]

    def test_disabled_provider_skipped(self):
        with patch("joborion.sources.registry.load_sources_config", return_value=CONFIG):
            enabled = enabled_providers()
        names = [p["name"] for p in enabled]
        assert names == ["jobspy", "workday"]
        assert "adzuna" not in names

    def test_ordered_by_priority(self):
        with patch("joborion.sources.registry.load_sources_config", return_value=CONFIG):
            enabled = enabled_providers()
        assert enabled[0]["name"] == "jobspy"
        assert enabled[-1]["name"] == "workday"

    def test_build_providers_instantiates_enabled(self):
        fake_map = {
            "jobspy": _FakeProvider,
            "workday": _FakeProvider,
        }
        with (
            patch("joborion.sources.registry.load_sources_config", return_value=CONFIG),
            patch(
                "joborion.sources.registry._import_provider_class",
                side_effect=lambda name: fake_map.get(name),
            ),
        ):
            providers = build_providers()
        assert [p.name for p in providers] == ["fake", "fake"]

    def test_build_providers_skips_unknown(self):
        with (
            patch("joborion.sources.registry.load_sources_config", return_value=CONFIG),
            patch("joborion.sources.registry._import_provider_class", return_value=None),
        ):
            providers = build_providers()
        assert providers == []

    def test_run_providers_calls_each_once(self):
        fake = _FakeProvider()
        results = run_providers({"mode": "remote"}, providers=[fake])
        assert fake.calls == 1
        assert len(results) == 1
        assert results[0].provider == "fake"
        assert results[0].found == 3
        assert results[0].stored == 2

    def test_run_providers_catches_errors(self):
        broken = _BrokenProvider()
        results = run_providers({"mode": "remote"}, providers=[broken])
        assert len(results) == 1
        assert results[0].errors == 1
        assert results[0].error == "boom"
