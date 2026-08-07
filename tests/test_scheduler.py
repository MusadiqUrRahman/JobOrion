"""Tests for Phase F1: Scheduled Runs (scheduler + CLI)."""

from datetime import datetime

import pytest
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from joborion.scheduler import ScheduledRunner, interval_to_trigger


class TestIntervalToTrigger:
    def test_hourly(self):
        trigger = interval_to_trigger("hourly")
        assert isinstance(trigger, IntervalTrigger)
        assert trigger.interval.total_seconds() == 3600

    def test_daily(self):
        trigger = interval_to_trigger("daily")
        assert isinstance(trigger, IntervalTrigger)
        assert trigger.interval.total_seconds() == 24 * 3600

    def test_weekly(self):
        trigger = interval_to_trigger("weekly")
        assert isinstance(trigger, IntervalTrigger)
        assert trigger.interval.total_seconds() == 7 * 24 * 3600

    def test_daily_with_at_uses_cron(self):
        trigger = interval_to_trigger("daily", at="09:30")
        assert isinstance(trigger, CronTrigger)
        next_fire = trigger.get_next_fire_time(None, datetime(2026, 8, 6, 10, 0))
        assert next_fire.hour == 9 and next_fire.minute == 30

    def test_invalid_interval_raises(self):
        with pytest.raises(ValueError):
            interval_to_trigger("monthly")

    def test_at_invalid_with_hourly(self):
        with pytest.raises(ValueError):
            interval_to_trigger("hourly", at="09:30")

    def test_at_invalid_format(self):
        with pytest.raises(ValueError):
            interval_to_trigger("daily", at="25:99")


@pytest.fixture
def runner():
    r = ScheduledRunner(interval="daily")
    yield r
    r.shutdown()


class TestScheduledRunner:
    def test_no_pending_jobs_by_default(self, runner):
        assert runner.pending_jobs() == []

    def test_add_job_registers(self, runner):
        job_id = runner.add_job(lambda: None)
        assert job_id in runner.pending_jobs()

    def test_add_job_custom_id(self, runner):
        runner.add_job(lambda: None, job_id="pipeline")
        assert "pipeline" in runner.pending_jobs()

    def test_add_job_replaces_existing(self, runner):
        runner.add_job(lambda: None, job_id="pipeline")
        runner.add_job(lambda: None, job_id="pipeline")
        assert runner.pending_jobs().count("pipeline") == 1

    def test_start_stop_lifecycle(self):
        r = ScheduledRunner(interval="hourly")
        r.add_job(lambda: None)
        assert r.is_running is False
        r.start()
        assert r.is_running is True
        r.shutdown()
        assert r.is_running is False


class TestCLIScheduling:
    def test_run_help_shows_schedule(self, cli_flags):
        from joborion.cli import app
        from typer.testing import CliRunner
        result = CliRunner().invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--schedule" in cli_flags["run"]

    def test_daemon_help_shows_interval_and_at(self, cli_flags):
        from joborion.cli import app
        from typer.testing import CliRunner
        result = CliRunner().invoke(app, ["daemon", "--help"])
        assert result.exit_code == 0
        assert "--interval" in cli_flags["daemon"]
        assert "--at" in cli_flags["daemon"]
