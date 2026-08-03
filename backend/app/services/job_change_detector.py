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

    event = None

    if latest_snapshot is not None:
        company_changed = _normalize(new_company) != _normalize(latest_snapshot.company)
        title_changed = _normalize(new_title) != _normalize(latest_snapshot.title)

        if company_changed or title_changed:
            event = JobChangeEvent(
                person_id=person.id,
                old_company=latest_snapshot.company,
                new_company=new_company,
                old_title=latest_snapshot.title,
                new_title=new_title,
                confidence_score=confidence,
                detected_at=datetime.utcnow(),
                status=EventStatus.new,
            )
            db.add(event)

            if company_changed:
                person.current_company = new_company
            if title_changed:
                person.current_title = new_title
    else:
        # First snapshot — seed current fields, no event
        person.current_company = new_company or person.current_company
        person.current_title = new_title or person.current_title

    db.commit()
    return event
