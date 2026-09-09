"""
Email notifications for detected job changes.

Two transports, chosen at send time:

  1. Resend HTTP API (preferred) — used when RESEND_API_KEY is set. Sends over
     HTTPS/443, which works on Railway (Railway blocks outbound SMTP).
  2. SMTP (fallback) — used when Resend isn't configured.

If neither is configured, sending is skipped silently so enrichment still
works in dev / mock mode without mail set up.

Env vars:
  NOTIFY_EMAIL    recipient for job-change alerts

  # Resend (preferred)
  RESEND_API_KEY  Resend API key
  RESEND_FROM     From address; must be on a verified domain to reach
                  arbitrary recipients. Defaults to onboarding@resend.dev,
                  which can ONLY deliver to the Resend account owner.

  # SMTP (fallback)
  SMTP_HOST       e.g. smtp.gmail.com
  SMTP_PORT       e.g. 587  (STARTTLS)
  SMTP_USER       the account that authenticates to the SMTP server
  SMTP_PASSWORD   app password / SMTP password
  SMTP_FROM       From address (defaults to SMTP_USER)
"""

import os
import ssl
import socket
import smtplib
import logging
from email.message import EmailMessage
from typing import Optional

import httpx

from app.models import JobChangeEvent, Person

logger = logging.getLogger("notifier")

RESEND_ENDPOINT = "https://api.resend.com/emails"


def _resend_config() -> Optional[dict]:
    key = os.environ.get("RESEND_API_KEY", "").strip()
    recipient = os.environ.get("NOTIFY_EMAIL", "").strip()
    if not (key and recipient):
        return None
    return {
        "key": key,
        "from": os.environ.get("RESEND_FROM", "").strip() or "onboarding@resend.dev",
        "to": recipient,
    }


def _send_via_resend(rc: dict, subject: str, body: str) -> tuple[bool, str]:
    """Send through Resend's HTTP API. Returns (sent, detail)."""
    try:
        resp = httpx.post(
            RESEND_ENDPOINT,
            headers={
                "Authorization": f"Bearer {rc['key']}",
                "Content-Type": "application/json",
                "User-Agent": "MobilityMonitor/1.0",  # avoid Cloudflare UA block
            },
            json={"from": rc["from"], "to": [rc["to"]], "subject": subject, "text": body},
            timeout=20,
        )
        if resp.status_code >= 400:
            return False, f"HTTP {resp.status_code}: {resp.text}"
        return True, f"Sent to {rc['to']} (id {resp.json().get('id')})."
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


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


def _open_server(cfg: dict) -> smtplib.SMTP:
    """
    Open an authenticated SMTP connection, forcing IPv4.

    Railway containers often lack an IPv6 route, so a normal connect to
    smtp.gmail.com resolves to an AAAA address and fails with
    "[Errno 101] Network is unreachable". We resolve the A (IPv4) record
    explicitly and connect to that, while keeping the real hostname for TLS
    SNI / certificate validation.
    """
    infos = socket.getaddrinfo(cfg["host"], cfg["port"], socket.AF_INET, socket.SOCK_STREAM)
    if not infos:
        raise OSError(f"No IPv4 address found for {cfg['host']}")
    ip = infos[0][4][0]
    context = ssl.create_default_context()

    if cfg["port"] == 465:
        raw = socket.create_connection((ip, cfg["port"]), timeout=25)
        sock = context.wrap_socket(raw, server_hostname=cfg["host"])
        server = smtplib.SMTP_SSL(timeout=25)
        server._host = cfg["host"]
        server.sock = sock
        server.file = None
        code, _ = server.getreply()
        if code != 220:
            server.close()
            raise smtplib.SMTPConnectError(code, "server refused connection")
    else:
        server = smtplib.SMTP(timeout=25)
        server._host = cfg["host"]  # used as TLS server_hostname by starttls()
        server.sock = socket.create_connection((ip, cfg["port"]), timeout=25)
        server.file = None
        code, _ = server.getreply()
        if code != 220:
            server.close()
            raise smtplib.SMTPConnectError(code, "server refused connection")
        server.ehlo()
        server.starttls(context=context)

    server.ehlo()
    server.login(cfg["user"], cfg["password"])
    return server


def _send(subject: str, body: str) -> None:
    # Prefer Resend (works on Railway); fall back to SMTP.
    rc = _resend_config()
    if rc:
        sent, detail = _send_via_resend(rc, subject, body)
        if sent:
            logger.info("Sent job-change email via Resend: %s", detail)
        else:
            logger.error("Resend send failed: %s", detail)
        return

    cfg = _config()
    if not cfg:
        logger.info("Email not configured — skipping notification.")
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["from"]
    msg["To"] = cfg["to"]
    msg.set_content(body)

    try:
        server = _open_server(cfg)
        try:
            server.send_message(msg)
        finally:
            server.quit()
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


def send_test_email() -> dict:
    """Send a dummy email to verify the configured transport end-to-end.

    Returns a dict describing what happened (transport / sent / detail) so a
    caller can surface it without reading server logs.
    """
    subject = "[Mobility] Test email — notifications are working"
    body = (
        "This is a test from the Client Mobility Monitor.\n"
        "If you received this, job-change alert emails are configured correctly."
    )

    rc = _resend_config()
    if rc:
        sent, detail = _send_via_resend(rc, subject, body)
        return {"transport": "resend", "sent": sent, "detail": detail}

    cfg = _config()
    if not cfg:
        return {
            "transport": "none",
            "sent": False,
            "detail": "No transport configured (set RESEND_API_KEY+NOTIFY_EMAIL, or SMTP_*).",
        }

    msg = EmailMessage()
    msg["Subject"] = "[Mobility] Test email — notifications are working"
    msg["From"] = cfg["from"]
    msg["To"] = cfg["to"]
    msg.set_content(
        "This is a test from the Client Mobility Monitor.\n"
        "If you received this, job-change alert emails are configured correctly."
    )

    try:
        server = _open_server(cfg)
        try:
            server.send_message(msg)
        finally:
            server.quit()
        return {"transport": "smtp", "sent": True, "detail": f"Sent to {cfg['to']}."}
    except Exception as exc:
        return {"transport": "smtp", "sent": False, "detail": f"{type(exc).__name__}: {exc}"}
