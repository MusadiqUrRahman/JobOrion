"""Notifier — builds and sends email digests for pipeline runs.

SMTP is configured via environment variables; with no SMTP_HOST the notifier
is inert and sending is skipped rather than failing.
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.text import MIMEText

log = logging.getLogger(__name__)

SMTP_HOST_ENV = "SMTP_HOST"
SMTP_PORT_ENV = "SMTP_PORT"
SMTP_USER_ENV = "SMTP_USER"
SMTP_PASS_ENV = "SMTP_PASS"
NOTIFY_FROM_ENV = "NOTIFY_FROM"
NOTIFY_TO_ENV = "NOTIFY_TO"


def load_notify_config() -> dict:
    """Read SMTP config from env vars. Returns {} if SMTP is not configured."""
    host = os.environ.get(SMTP_HOST_ENV, "").strip()
    if not host:
        return {}
    user = os.environ.get(SMTP_USER_ENV, "").strip()
    return {
        "host": host,
        "port": int(os.environ.get(SMTP_PORT_ENV, "587") or "587"),
        "user": user,
        "password": os.environ.get(SMTP_PASS_ENV, "").strip(),
        "from_addr": os.environ.get(NOTIFY_FROM_ENV, "").strip() or user,
        "to_addr": os.environ.get(NOTIFY_TO_ENV, "").strip(),
    }


def digest_from_stats(stats: dict, goal: str = "", total_cost: float = 0.0) -> dict:
    """Package pipeline DB stats into run_data digest shape."""
    return {
        "goal": goal or "Recent pipeline run",
        "duration_s": 0.0,
        "total_cost": total_cost,
        "stages": [
            {"name": "search", "status": "ok", "count": stats.get("total", 0)},
            {"name": "details", "status": "ok", "count": stats.get("with_description", 0)},
            {"name": "evaluate", "status": "ok", "count": stats.get("scored", 0)},
            {"name": "tailor", "status": "ok", "count": stats.get("tailored", 0)},
        ],
        "top_jobs": [],
        "errors": [],
    }


def build_digest(run_data: dict) -> str:
    """Build a plain-text email digest from run data."""
    from joborion.agent.reporter import RunReporter
    return RunReporter().generate(run_data)


def send_digest(digest: str, cfg: dict | None = None) -> bool:
    """Email the digest via SMTP.

    Args:
        digest: Plain-text digest body.
        cfg: SMTP config dict (see load_notify_config). Uses env if None.

    Returns:
        True if the email was sent, False if not configured or on failure.
    """
    cfg = cfg if cfg is not None else load_notify_config()
    if not cfg:
        log.info("Email not configured; skipping digest")
        return False
    try:
        msg = MIMEText(digest)
        msg["Subject"] = "JobOrion daily digest"
        msg["From"] = cfg["from_addr"]
        msg["To"] = cfg["to_addr"]
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=30) as server:
            if cfg.get("user") and cfg.get("password"):
                server.starttls()
                server.login(cfg["user"], cfg["password"])
            server.send_message(msg)
        return True
    except Exception as e:
        log.error("Failed to send digest email: %s", e)
        return False
