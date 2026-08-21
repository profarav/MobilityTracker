from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Person, PersonStatus
from app.schemas import BulkRefreshResult, RefreshResult
from app.services.job_change_detector import detect_and_record
from app.services.notifier import notify_job_changes, notify_single_change

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
