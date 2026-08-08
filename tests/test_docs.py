"""Drift guard: keep README documentation honest against the real CLI."""

from pathlib import Path


def _known_commands() -> set[str]:
    from joborion.cli import app, profile_app

    names = {info.name or info.callback.__name__ for info in app.registered_commands}
    names |= {info.name or info.callback.__name__ for info in profile_app.registered_commands}
    return names


def _readme_lines() -> list[str]:
    root = Path(__file__).resolve().parent.parent
    return (root / "README.md").read_text(encoding="utf-8").splitlines()


class TestREADMECommands:
    def test_every_example_references_a_real_command(self):
        known = _known_commands()
        missing: list[str] = []
        for line in _readme_lines():
            tokens = line.strip().split()
            if not tokens or tokens[0] != "joborion":
                continue
            if not any(tok in known for tok in tokens):
                missing.append(line)
        assert not missing, f"README examples reference unknown commands: {missing}"

    def test_documented_provider_boards(self):
        text = "\n".join(_readme_lines())
        for board in ("Remotive", "RemoteOK", "WeWorkRemotely", "Jobicy", "Arbeitnow", "Working Nomads"):
            assert board in text, f"Board {board} missing from README"


class TestREADMEFlags:
    def test_key_run_flags_declared(self, cli_flags):
        for flag in ("--notify", "--report", "--schedule"):
            assert flag in cli_flags["run"]

    def test_daemon_flags_declared(self, cli_flags):
        for flag in ("--notify", "--report"):
            assert flag in cli_flags["daemon"]

    def test_report_flags_declared(self, cli_flags):
        for flag in ("--days", "--top", "--json"):
            assert flag in cli_flags["report"]

    def test_profile_flag_declared(self):
        import inspect

        from joborion.cli import main

        param = inspect.signature(main).parameters["profile"]
        assert "--profile" in param.default.param_decls
