"""
Compares an enriched profile against the last stored snapshot and creates
a JobChangeEvent when the company or title has changed.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models import EmploymentSnapshot, EventStatus, JobChangeEvent, Person


def _normalize(value: Optional[str]) -> str:
    return (value or "").strip().lower()


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
    company_changed = bool(baseline_company) and _normalize(new_company) != _normalize(baseline_company)
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
