"""Tests for Phase F3: notification — rich summary + email digest."""

from joborion.notifier import (
    build_digest,
    digest_from_stats,
    load_notify_config,
    send_digest,
)


class TestLoadNotifyConfig:
    def test_no_config_returns_empty(self, monkeypatch):
        monkeypatch.delenv("SMTP_HOST", raising=False)
        assert load_notify_config() == {}

    def test_reads_host_and_defaults(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_USER", "user@example.com")
        cfg = load_notify_config()
        assert cfg["host"] == "smtp.example.com"
        assert cfg["port"] == 587
        assert cfg["from_addr"] == "user@example.com"

    def test_reads_full_config(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_PORT", "465")
        monkeypatch.setenv("NOTIFY_TO", "me@example.com")
        monkeypatch.setenv("NOTIFY_FROM", "bot@example.com")
        cfg = load_notify_config()
        assert cfg["port"] == 465
        assert cfg["to_addr"] == "me@example.com"
        assert cfg["from_addr"] == "bot@example.com"


class TestBuildDigest:
    def test_generates_nonempty_report(self):
        digest = build_digest({"goal": "Find python jobs", "stages": [], "errors": []})
        assert isinstance(digest, str)
        assert "python" in digest.lower()

    def test_digest_from_stats(self):
        stats = {"total": 40, "with_description": 25, "scored": 12, "tailored": 3}
        data = digest_from_stats(stats, goal="test", total_cost=0.15)
        assert data["total_cost"] == 0.15
        stages = {s["name"]: s["count"] for s in data["stages"]}
        assert stages["search"] == 40
        assert stages["evaluate"] == 12
        assert stages["tailor"] == 3


class TestSendDigest:
    def test_not_configured_returns_false(self):
        assert send_digest("hello", cfg={}) is False

    def test_sends_message(self, monkeypatch):
        sent = []

        class FakeSMTP:
            def __init__(self, host, port, timeout=None):
                self.host = host
                self.port = port

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def starttls(self):
                pass

            def login(self, user, password):
                assert user == "user@example.com"

            def send_message(self, msg):
                sent.append(msg)

        monkeypatch.setattr("joborion.notifier.smtplib.SMTP", FakeSMTP)
        cfg = {
            "host": "smtp.example.com",
            "port": 587,
            "user": "user@example.com",
            "password": "secret",
            "from_addr": "user@example.com",
            "to_addr": "me@example.com",
        }
        assert send_digest("digest body", cfg=cfg) is True
        assert len(sent) == 1
        assert sent[0]["To"] == "me@example.com"
        assert sent[0]["Subject"] == "JobOrion daily digest"

    def test_smtp_failure_returns_false(self, monkeypatch):
        class BrokenSMTP:
            def __init__(self, host, port, timeout=None):
                raise OSError("connection refused")

        monkeypatch.setattr("joborion.notifier.smtplib.SMTP", BrokenSMTP)
        cfg = {
            "host": "smtp.example.com",
            "port": 587,
            "user": "",
            "password": "",
            "from_addr": "bot@example.com",
            "to_addr": "me@example.com",
        }
        assert send_digest("digest body", cfg=cfg) is False


class TestCLINotify:
    def test_notify_help_shows_to(self, cli_flags):
        from joborion.cli import app
        from typer.testing import CliRunner
        result = CliRunner().invoke(app, ["notify", "--help"])
        assert result.exit_code == 0
        assert "--to" in cli_flags["notify"]

    def test_notify_without_config_errors(self, monkeypatch):
        from joborion.cli import app
        from typer.testing import CliRunner
        monkeypatch.setattr("joborion.notifier.load_notify_config", lambda: {})
        result = CliRunner().invoke(app, ["notify"])
        assert result.exit_code == 1
