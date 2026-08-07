"""Shared test fixtures.

Environment-agnostic helpers for CLI flag assertions. Rich's rich-rendered
help output is truncated differently depending on whether a terminal is
detected (e.g. GitHub Actions forces `GITHUB_ACTIONS` -> `force_terminal`),
so asserting on rendered help text is unreliable across environments. These
helpers assert on the registered option declarations instead.
"""

import inspect

import pytest


@pytest.fixture
def cli_flags() -> dict[str, set[str]]:
    """Map typer command name -> set of declared option flags (e.g. '--auto')."""
    from joborion.cli import app

    flags: dict[str, set[str]] = {}
    for info in app.registered_commands:
        name = info.callback.__name__
        declared: set[str] = set()
        for param in inspect.signature(info.callback).parameters.values():
            decls = getattr(param.default, "param_decls", None)
            if decls:
                declared.update(decls)
        flags[name] = declared
    return flags
