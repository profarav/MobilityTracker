from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import JobChangeEvent, Person, PersonStatus
from app.schemas import BulkRefreshResult, RefreshResult
from app.services.job_change_detector import detect_and_record
from app.services.notifier import (
    notify_job_changes,
    notify_single_change,
    send_test_email,
)

import os

if os.environ.get("ENRICHMENT_PROVIDER", "mock").lower() == "apollo":
    from app.services.apollo_enrichment import enrich_person
else:
    from app.services.mock_enrichment import enrich_person

router = APIRouter(prefix="/enrichment", tags=["enrichment"])


@router.post("/refresh/{person_id}", response_model=RefreshResult)
def refresh_person(person_id: str, db: Session = Depends(get_db)):
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    enriched = enrich_person(
        person_id=str(person.id),
        current_company=person.current_company,
        current_title=person.current_title,
        linkedin_url=person.linkedin_url,
        email=person.work_email,
        full_name=person.full_name,
    )
    event = detect_and_record(db, person, enriched)
    if event:
        notify_single_change(event, person)

    return RefreshResult(
        person_id=str(person.id),
        enriched=enriched,
        job_change_detected=event is not None,
        event_id=str(event.id) if event else None,
    )


@router.post("/refresh-all", response_model=BulkRefreshResult)
def refresh_all(db: Session = Depends(get_db)):
    people = db.query(Person).filter(Person.status == PersonStatus.active).all()

    refreshed = job_changes = 0
    errors: list[str] = []
    changes: list[tuple] = []

    for person in people:
        try:
            enriched = enrich_person(
                person_id=str(person.id),
                current_company=person.current_company,
                current_title=person.current_title,
                linkedin_url=person.linkedin_url,
                email=person.work_email,
                full_name=person.full_name,
            )
            event = detect_and_record(db, person, enriched)
            refreshed += 1
            if event:
                job_changes += 1
                changes.append((event, person))
        except Exception as exc:
            errors.append(f"{person.full_name}: {exc}")

    notify_job_changes(changes)

    return BulkRefreshResult(
        refreshed=refreshed,
        job_changes_detected=job_changes,
        errors=errors,
    )


@router.post("/test-email")
def test_email():
    """Send a dummy email to verify SMTP is configured and Gmail accepts login."""
    return send_test_email()


@router.post("/resend-digest")
def resend_digest(
    since: str = Query(..., description="Include events detected on/after this date (YYYY-MM-DD)"),
    until: Optional[str] = Query(None, description="Exclusive upper bound (YYYY-MM-DD)"),
    db: Session = Depends(get_db),
):
    """
    Re-send a digest email for job changes already recorded in a date window
    (e.g. changes from a past run that predated email being configured).
    Does not re-enrich or create new events — just emails existing ones.
    """
    try:
        since_dt = datetime.fromisoformat(since)
    except ValueError:
        raise HTTPException(status_code=400, detail="since must be YYYY-MM-DD")

    q = (
        db.query(JobChangeEvent)
        .options(joinedload(JobChangeEvent.person))
        .filter(JobChangeEvent.detected_at >= since_dt)
    )
    if until:
        try:
            until_dt = datetime.fromisoformat(until)
        except ValueError:
            raise HTTPException(status_code=400, detail="until must be YYYY-MM-DD")
        q = q.filter(JobChangeEvent.detected_at < until_dt)

    events = q.order_by(JobChangeEvent.detected_at.desc()).all()
    pairs = [(e, e.person) for e in events if e.person is not None]
    notify_job_changes(pairs)

    return {"since": since, "until": until, "events_emailed": len(pairs)}
