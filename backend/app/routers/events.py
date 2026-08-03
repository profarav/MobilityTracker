from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import EventStatus, JobChangeEvent
from app.schemas import EventStatusUpdate, JobChangeEventOut

router = APIRouter(prefix="/events", tags=["events"])


@router.get("/", response_model=list[JobChangeEventOut])
def list_events(
    status: Optional[EventStatus] = None,
    limit: int = Query(200, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(JobChangeEvent).options(joinedload(JobChangeEvent.person))
    if status:
        q = q.filter(JobChangeEvent.status == status)
    return q.order_by(JobChangeEvent.detected_at.desc()).offset(offset).limit(limit).all()


@router.get("/{event_id}", response_model=JobChangeEventOut)
def get_event(event_id: str, db: Session = Depends(get_db)):
    event = (
        db.query(JobChangeEvent)
        .options(joinedload(JobChangeEvent.person))
        .filter(JobChangeEvent.id == event_id)
        .first()
    )
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event


@router.patch("/{event_id}/status", response_model=JobChangeEventOut)
def update_event_status(
    event_id: str, data: EventStatusUpdate, db: Session = Depends(get_db)
):
    event = (
        db.query(JobChangeEvent)
        .options(joinedload(JobChangeEvent.person))
        .filter(JobChangeEvent.id == event_id)
        .first()
    )
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    event.status = data.status
    db.commit()
    db.refresh(event)
    return event
