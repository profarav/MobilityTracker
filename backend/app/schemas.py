from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel

from app.models import EventStatus, PersonStatus


class PersonBase(BaseModel):
    full_name: str
    work_email: str
    linkedin_url: Optional[str] = None
    current_company: Optional[str] = None
    current_title: Optional[str] = None
    relationship_owner: Optional[str] = None
    source_system: Optional[str] = None
    status: PersonStatus = PersonStatus.active


class PersonCreate(PersonBase):
    pass


class PersonUpdate(BaseModel):
    full_name: Optional[str] = None
    linkedin_url: Optional[str] = None
    current_company: Optional[str] = None
    current_title: Optional[str] = None
    relationship_owner: Optional[str] = None
    status: Optional[PersonStatus] = None


class PersonOut(PersonBase):
    id: UUID
    last_checked_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SnapshotOut(BaseModel):
    id: UUID
    person_id: UUID
    company: Optional[str] = None
    title: Optional[str] = None
    source: Optional[str] = None
    confidence_score: Optional[float] = None
    snapshot_date: datetime
    raw_payload_json: Optional[Any] = None

    model_config = {"from_attributes": True}


class JobChangeEventOut(BaseModel):
    id: UUID
    person_id: UUID
    old_company: Optional[str] = None
    new_company: Optional[str] = None
    old_title: Optional[str] = None
    new_title: Optional[str] = None
    confidence_score: Optional[float] = None
    detected_at: datetime
    status: EventStatus
    person: Optional[PersonOut] = None

    model_config = {"from_attributes": True}


class EventStatusUpdate(BaseModel):
    status: EventStatus


class RefreshResult(BaseModel):
    person_id: str
    enriched: dict
    job_change_detected: bool
    event_id: Optional[str] = None


class BulkRefreshResult(BaseModel):
    refreshed: int
    job_changes_detected: int
    errors: list[str]


class CSVImportResult(BaseModel):
    created: int
    updated: int
    skipped: int
    errors: list[str]


class Stats(BaseModel):
    total_people: int
    active_people: int
    new_job_changes: int
