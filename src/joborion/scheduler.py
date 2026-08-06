"""Scheduler — repeat pipeline runs on a schedule using APScheduler."""

from __future__ import annotations

import re

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

_HOURS = {"hourly": 1, "daily": 24, "weekly": 7 * 24}

_AT_PATTERN = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


def interval_to_trigger(interval: str, at: str | None = None) -> BaseTrigger:
    """Map an interval name to an APScheduler trigger.

    Args:
        interval: One of "hourly", "daily", "weekly".
        at: Optional "HH:MM" start time, only valid for daily.

    Returns:
        APScheduler trigger for the requested schedule.

    Raises:
        ValueError: If interval is unknown or at is malformed/not applicable.
    """
    if interval not in _HOURS:
        raise ValueError(
            f"Invalid interval '{interval}'. Choose from: {', '.join(_HOURS)}"
        )

    if at is None:
        return IntervalTrigger(hours=_HOURS[interval])

    if interval != "daily":
        raise ValueError("--at is only supported for daily schedules")

    match = _AT_PATTERN.match(at)
    if not match:
        raise ValueError(f"Invalid --at '{at}'. Use HH:MM (24h).")
    return CronTrigger(hour=int(match.group(1)), minute=int(match.group(2)))


class ScheduledRunner:
    """Wrap a background APScheduler for repeat pipeline runs."""

    def __init__(self, interval: str = "daily", at: str | None = None) -> None:
        self._interval = interval
        self._at = at
        self._scheduler = BackgroundScheduler()

    def add_job(self, fn, job_id: str = "pipeline") -> str:
        """Register a repeat job and return its id."""
        trigger = interval_to_trigger(self._interval, self._at)
        return self._scheduler.add_job(
            fn, trigger=trigger, id=job_id, replace_existing=True
        ).id

    def pending_jobs(self) -> list[str]:
        """Return unique ids of all registered jobs."""
        return sorted({job.id for job in self._scheduler.get_jobs()})

    @property
    def is_running(self) -> bool:
        return self._scheduler.running

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
