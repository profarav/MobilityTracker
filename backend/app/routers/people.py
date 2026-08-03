import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Person, PersonStatus
from app.schemas import CSVImportResult, PersonCreate, PersonOut, PersonUpdate

router = APIRouter(prefix="/people", tags=["people"])


@router.get("/", response_model=list[PersonOut])
def list_people(
    status: Optional[PersonStatus] = None,
    search: Optional[str] = None,
    limit: int = Query(200, le=500),
    offset: int = 0,
    db: Session = Depends(get_db),
):
    q = db.query(Person)
    if status:
        q = q.filter(Person.status == status)
    if search:
        term = f"%{search}%"
        q = q.filter(
            Person.full_name.ilike(term)
            | Person.work_email.ilike(term)
            | Person.current_company.ilike(term)
        )
    return q.order_by(Person.created_at.desc()).offset(offset).limit(limit).all()


@router.get("/{person_id}", response_model=PersonOut)
def get_person(person_id: str, db: Session = Depends(get_db)):
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    return person


@router.post("/", response_model=PersonOut, status_code=201)
def create_person(data: PersonCreate, db: Session = Depends(get_db)):
    if db.query(Person).filter(Person.work_email == data.work_email).first():
        raise HTTPException(status_code=409, detail="Email already exists")
    person = Person(**data.model_dump())
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


@router.patch("/{person_id}", response_model=PersonOut)
def update_person(person_id: str, data: PersonUpdate, db: Session = Depends(get_db)):
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(person, field, value)
    db.commit()
    db.refresh(person)
    return person


@router.delete("/{person_id}", status_code=204)
def delete_person(person_id: str, db: Session = Depends(get_db)):
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    db.delete(person)
    db.commit()


@router.post("/import/csv", response_model=CSVImportResult)
async def import_csv(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not (file.filename or "").endswith(".csv"):
        raise HTTPException(status_code=400, detail="File must be a .csv")

    content = await file.read()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))

    created = updated = skipped = 0
    errors: list[str] = []

    for row_num, row in enumerate(reader, start=2):
        email = (row.get("work_email") or "").strip().lower()
        full_name = (row.get("full_name") or "").strip()

        if not email:
            errors.append(f"Row {row_num}: missing work_email — skipped")
            skipped += 1
            continue
        if not full_name:
            errors.append(f"Row {row_num}: missing full_name — skipped")
            skipped += 1
            continue

        try:
            existing = db.query(Person).filter(Person.work_email == email).first()
            if existing:
                for field in (
                    "current_company",
                    "current_title",
                    "linkedin_url",
                    "relationship_owner",
                ):
                    val = (row.get(field) or "").strip() or None
                    if val:
                        setattr(existing, field, val)
                db.commit()
                updated += 1
            else:
                person = Person(
                    full_name=full_name,
                    work_email=email,
                    linkedin_url=(row.get("linkedin_url") or "").strip() or None,
                    current_company=(row.get("current_company") or "").strip() or None,
                    current_title=(row.get("current_title") or "").strip() or None,
                    relationship_owner=(row.get("relationship_owner") or "").strip() or None,
                    source_system=(row.get("source_system") or "csv_import").strip(),
                )
                db.add(person)
                db.commit()
                created += 1
        except Exception as exc:
            db.rollback()
            errors.append(f"Row {row_num}: {exc}")
            skipped += 1

    return CSVImportResult(created=created, updated=updated, skipped=skipped, errors=errors)
