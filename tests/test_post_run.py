"""Tests for the post-run notify/report automation hook."""

from joborion.cli import _post_run_output


class TestPostRunOutput:
    def test_notify_sends_digest(self, monkeypatch, capsys):
        sent = []
        monkeypatch.setattr(
            "joborion.database.get_stats",
            lambda conn=None: {
                "total": 5, "with_description": 4, "scored": 3, "tailored": 2,
            },
        )
        monkeypatch.setattr("joborion.database.get_total_cost", lambda conn=None: 1.25)
        monkeypatch.setattr(
            "joborion.notifier.load_notify_config",
            lambda: {"to_addr": "me@example.com"},
        )
        monkeypatch.setattr(
            "joborion.notifier.send_digest",
            lambda digest, cfg=None: sent.append((digest, cfg)) or True,
        )

        _post_run_output(None, notify=True, report=False, goal="pipeline:search")

        assert len(sent) == 1
        digest, cfg = sent[0]
        assert "JobOrion Run Report" in digest
        assert cfg["to_addr"] == "me@example.com"
        assert "Digest email sent" in capsys.readouterr().out

    def test_notify_skipped_without_smtp(self, monkeypatch):
        called = []
        monkeypatch.setattr(
            "joborion.database.get_stats",
            lambda conn=None: {
                "total": 1, "with_description": 1, "scored": 1, "tailored": 0,
            },
        )
        monkeypatch.setattr("joborion.database.get_total_cost", lambda conn=None: 0.0)
        monkeypatch.setattr("joborion.notifier.load_notify_config", lambda: {})
        monkeypatch.setattr(
            "joborion.notifier.send_digest",
            lambda digest, cfg=None: called.append(True) or True,
        )

        _post_run_output(None, notify=True, report=False)

        assert called == []

    def test_report_prints(self, monkeypatch, capsys):
        monkeypatch.setattr(
            "joborion.report.build_report",
            lambda conn=None, days=30, top=10: {
                "window_days": 30,
                "funnel": {"discovered": 1},
                "providers": [],
                "cost": {"calls": 0, "total_cost_usd": 0.0, "by_tool": []},
                "recent_runs": [],
            },
        )
        monkeypatch.setattr("joborion.report.render_report", lambda report: "REPORT-TEXT")

        _post_run_output(None, notify=False, report=True)

        assert "REPORT-TEXT" in capsys.readouterr().out

    def test_report_render_failure_is_graceful(self, monkeypatch, capsys):
        monkeypatch.setattr(
            "joborion.report.build_report",
            lambda conn=None, days=30, top=10: {},
        )
        monkeypatch.setattr(
            "joborion.report.render_report", lambda report: (_ for _ in ()).throw(ValueError("boom"))
        )

        _post_run_output(None, notify=False, report=True)

        assert "Report render failed" in capsys.readouterr().out

    def test_both_flags(self, monkeypatch, capsys):
        sent = []
        monkeypatch.setattr(
            "joborion.database.get_stats",
            lambda conn=None: {
                "total": 3, "with_description": 2, "scored": 1, "tailored": 0,
            },
        )
        monkeypatch.setattr("joborion.database.get_total_cost", lambda conn=None: 0.5)
        monkeypatch.setattr(
            "joborion.notifier.load_notify_config",
            lambda: {"to_addr": "me@example.com"},
        )
        monkeypatch.setattr(
            "joborion.notifier.send_digest",
            lambda digest, cfg=None: sent.append(True) or True,
        )
        monkeypatch.setattr("joborion.report.render_report", lambda report: "REPORT-TEXT")

        _post_run_output(None, notify=True, report=True)

        out = capsys.readouterr().out
        assert len(sent) == 1
        assert "REPORT-TEXT" in out


class TestCLIFlags:
    def test_run_has_notify_and_report(self, cli_flags):
        assert "--notify" in cli_flags["run"]
        assert "--report" in cli_flags["run"]

    def test_daemon_has_notify_and_report(self, cli_flags):
        assert "--notify" in cli_flags["daemon"]
        assert "--report" in cli_flags["daemon"]

    def test_run_help_still_works(self):
        from joborion.cli import app
        from typer.testing import CliRunner

        result = CliRunner().invoke(app, ["run", "--help"])
        assert result.exit_code == 0

    def test_daemon_help_still_works(self):
        from joborion.cli import app
        from typer.testing import CliRunner

        result = CliRunner().invoke(app, ["daemon", "--help"])
        assert result.exit_code == 0
