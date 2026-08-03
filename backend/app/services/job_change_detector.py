"""
Compares an enriched profile against the last stored snapshot and creates
a JobChangeEvent when the company or title has changed.
"""

import re
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import EmploymentSnapshot, EventStatus, JobChangeEvent, Person

_LEGAL_SUFFIXES = re.compile(
    r"\b(inc|incorporated|llc|ltd|limited|corp|corporation|co|company|"
    r"group|holdings|plc)\b\.?",
    re.IGNORECASE,
)


def _normalize(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def _company_key(value: Optional[str]) -> str:
    """
    Collapse a company name to a bare comparison key: strip punctuation,
    legal suffixes (Inc, LLC, Corp...), and all whitespace, so
    "Swiss Monkey, Inc" and "SwissMonkey" normalize to the same key.
    """
    text = (value or "").lower()
    text = re.sub(r"[.,]", "", text)
    text = _LEGAL_SUFFIXES.sub("", text)
    text = re.sub(r"\s+", "", text)
    return text


def _company_changed(new_company: Optional[str], baseline_company: Optional[str]) -> bool:
    if not baseline_company:
        return False
    new_key = _company_key(new_company)
    baseline_key = _company_key(baseline_company)
    if not new_key or not baseline_key:
        return _normalize(new_company) != _normalize(baseline_company)
    if new_key == baseline_key:
        return False
    # One name is a shortened/abbreviated form of the other
    # (e.g. "Superbrewed" vs "Superbrewed Food Inc").
    if new_key in baseline_key or baseline_key in new_key:
        return False
    return True


def detect_and_record(
    db: Session, person: Person, enriched: dict
) -> Optional[JobChangeEvent]:
    """
    Always stores a new snapshot.
    Returns a JobChangeEvent if company or title differs from the last snapshot,
    otherwise returns None.
    """
    new_company = enriched.get("company")
    new_title = enriched.get("title")
    confidence = enriched.get("confidence_score")

    latest_snapshot = (
        db.query(EmploymentSnapshot)
        .filter(EmploymentSnapshot.person_id == person.id)
        .order_by(EmploymentSnapshot.snapshot_date.desc())
        .first()
    )

    snapshot = EmploymentSnapshot(
        person_id=person.id,
        company=new_company,
        title=new_title,
        source=enriched.get("source", "unknown"),
        confidence_score=confidence,
        snapshot_date=datetime.utcnow(),
        raw_payload_json=enriched.get("raw"),
    )
    db.add(snapshot)

    person.last_checked_at = datetime.utcnow()

    # Compare against the last enrichment snapshot if one exists, otherwise
    # fall back to the person's known company/title (e.g. from CSV import) —
    # that's real baseline data too, not something to silently skip.
    baseline_company = latest_snapshot.company if latest_snapshot else person.current_company
    baseline_title = latest_snapshot.title if latest_snapshot else person.current_title

    event = None
    company_changed = _company_changed(new_company, baseline_company)
    title_changed = bool(baseline_title) and _normalize(new_title) != _normalize(baseline_title)

    if company_changed or title_changed:
        event = JobChangeEvent(
            person_id=person.id,
            old_company=baseline_company,
            new_company=new_company,
            old_title=baseline_title,
            new_title=new_title,
            confidence_score=confidence,
            detected_at=datetime.utcnow(),
            status=EventStatus.new,
        )
        db.add(event)

    if company_changed or not baseline_company:
        person.current_company = new_company or person.current_company
    if title_changed or not baseline_title:
        person.current_title = new_title or person.current_title

    db.commit()
    return event
