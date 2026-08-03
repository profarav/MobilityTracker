from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import Base, engine, get_db
from app.models import EventStatus, JobChangeEvent, Person, PersonStatus
from app.routers import enrichment, events, people
from app.schemas import Stats

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Client Mobility Monitor", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(people.router)
app.include_router(events.router)
app.include_router(enrichment.router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/stats", response_model=Stats)
def get_stats(db: Session = Depends(get_db)):
    total_people = db.query(func.count(Person.id)).scalar() or 0
    active_people = (
        db.query(func.count(Person.id))
        .filter(Person.status == PersonStatus.active)
        .scalar()
        or 0
    )
    new_job_changes = (
        db.query(func.count(JobChangeEvent.id))
        .filter(JobChangeEvent.status == EventStatus.new)
        .scalar()
        or 0
    )
    return Stats(
        total_people=total_people,
        active_people=active_people,
        new_job_changes=new_job_changes,
    )
