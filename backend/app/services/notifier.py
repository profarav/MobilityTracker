"""
Email notifications for detected job changes.

Sends via SMTP using credentials from environment variables. If SMTP is not
configured (no host / user / password), sending is skipped silently so that
enrichment still works in dev / mock mode without mail set up.

Env vars:
  SMTP_HOST       e.g. smtp.gmail.com
  SMTP_PORT       e.g. 587  (STARTTLS)
  SMTP_USER       the account that authenticates to the SMTP server
  SMTP_PASSWORD   app password / SMTP password
  SMTP_FROM       From address (defaults to SMTP_USER)
  NOTIFY_EMAIL    recipient for job-change alerts (e.g. Hugh)
"""

import os
import smtplib
import logging
from email.message import EmailMessage
from typing import Optional

from app.models import JobChangeEvent, Person

logger = logging.getLogger("notifier")


def _config() -> Optional[dict]:
    host = os.environ.get("SMTP_HOST", "").strip()
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "").strip()
    recipient = os.environ.get("NOTIFY_EMAIL", "").strip()

    if not (host and user and password and recipient):
        return None

    return {
        "host": host,
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": user,
        "password": password,
        "from": os.environ.get("SMTP_FROM", "").strip() or user,
        "to": recipient,
    }


def _describe(event: JobChangeEvent, person: Person) -> str:
    lines = [f"• {person.full_name} ({person.work_email})"]
    if (event.old_company or "") != (event.new_company or ""):
        lines.append(f"    Company: {event.old_company or '—'}  →  {event.new_company or '—'}")
    if (event.old_title or "") != (event.new_title or ""):
        lines.append(f"    Title:   {event.old_title or '—'}  →  {event.new_title or '—'}")
    if person.relationship_owner:
        lines.append(f"    Owner:   {person.relationship_owner}")
    if event.confidence_score is not None:
        lines.append(f"    Confidence: {event.confidence_score:.0%}")
    return "\n".join(lines)


def _send(subject: str, body: str) -> None:
    cfg = _config()
    if not cfg:
        logger.info("SMTP not configured — skipping email notification.")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["from"]
    msg["To"] = cfg["to"]
    msg.set_content(body)

    try:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as server:
            server.starttls()
            server.login(cfg["user"], cfg["password"])
            server.send_message(msg)
        logger.info("Sent job-change email to %s", cfg["to"])
    except Exception as exc:  # don't let a mail failure break enrichment
        logger.error("Failed to send job-change email: %s", exc)


def notify_job_changes(pairs: list[tuple[JobChangeEvent, Person]]) -> None:
    """Send one digest email covering all job changes in this batch."""
    if not pairs:
        return

    count = len(pairs)
    subject = (
        f"[Mobility] {count} job change{'s' if count != 1 else ''} detected"
    )
    header = (
        f"{count} contact{'s' if count != 1 else ''} changed jobs "
        f"in the latest refresh:\n\n"
    )
    body = header + "\n\n".join(_describe(e, p) for e, p in pairs)
    _send(subject, body)


def notify_single_change(event: JobChangeEvent, person: Person) -> None:
    """Send an email for one detected job change."""
    subject = f"[Mobility] {person.full_name} changed jobs"
    _send(subject, _describe(event, person))
