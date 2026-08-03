import uuid
import enum
from datetime import datetime

from sqlalchemy import Column, String, Float, DateTime, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.database import Base


class PersonStatus(str, enum.Enum):
    active = "active"
    inactive = "inactive"
    archived = "archived"


class EventStatus(str, enum.Enum):
    new = "new"
    reviewed = "reviewed"
    dismissed = "dismissed"
    converted = "converted"


class Person(Base):
    __tablename__ = "people"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name = Column(String, nullable=False)
    work_email = Column(String, unique=True, nullable=False, index=True)
    linkedin_url = Column(String, nullable=True)
    current_company = Column(String, nullable=True)
    current_title = Column(String, nullable=True)
    relationship_owner = Column(String, nullable=True)
    source_system = Column(String, nullable=True)
    status = Column(Enum(PersonStatus), default=PersonStatus.active, nullable=False)
    last_checked_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    snapshots = relationship(
        "EmploymentSnapshot",
        back_populates="person",
        order_by="EmploymentSnapshot.snapshot_date.desc()",
        cascade="all, delete-orphan",
    )
    job_change_events = relationship(
        "JobChangeEvent",
        back_populates="person",
        order_by="JobChangeEvent.detected_at.desc()",
        cascade="all, delete-orphan",
    )


class EmploymentSnapshot(Base):
    __tablename__ = "employment_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id = Column(
        UUID(as_uuid=True), ForeignKey("people.id"), nullable=False, index=True
    )
    company = Column(String, nullable=True)
    title = Column(String, nullable=True)
    source = Column(String, nullable=True)
    confidence_score = Column(Float, nullable=True)
    snapshot_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    raw_payload_json = Column(JSONB, nullable=True)

    person = relationship("Person", back_populates="snapshots")


class JobChangeEvent(Base):
    __tablename__ = "job_change_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id = Column(
        UUID(as_uuid=True), ForeignKey("people.id"), nullable=False, index=True
    )
    old_company = Column(String, nullable=True)
    new_company = Column(String, nullable=True)
    old_title = Column(String, nullable=True)
    new_title = Column(String, nullable=True)
    confidence_score = Column(Float, nullable=True)
    detected_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    status = Column(Enum(EventStatus), default=EventStatus.new, nullable=False)

    person = relationship("Person", back_populates="job_change_events")
