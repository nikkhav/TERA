import hashlib
import logging
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tera.config import get_settings
from tera.db import get_session
from tera.models import Document, Employee, SummaryJob, Trip, new_id
from tera.pdf import extract_pages
from tera.prompts import PROMPT_VERSION
from tera.schemas import (
    DocumentOut,
    EmployeeCreate,
    EmployeeOut,
    JobOut,
    SummaryResult,
    TripCreate,
    TripOut,
)
from tera.storage import ObjectStore, get_store

app = FastAPI(title="TERA API", version="0.1.0", description="Local travel expense research API")
DB = Annotated[Session, Depends(get_session)]
Store = Annotated[ObjectStore, Depends(get_store)]
Limit = Annotated[int, Query(ge=1, le=500)]
Offset = Annotated[int, Query(ge=0)]
logger = logging.getLogger(__name__)


def require(session, model, identifier):
    item = session.get(model, str(identifier))
    if item is None:
        raise HTTPException(404, "Not found")
    return item


def lock_trip(session, trip_id):
    trip = session.scalar(select(Trip).where(Trip.id == str(trip_id)).with_for_update())
    if trip is None:
        raise HTTPException(404, "Trip not found")
    return trip


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready(session: DB, store: Store):
    try:
        session.execute(text("SELECT 1"))
        store.client.head_bucket(Bucket=store.bucket)
    except Exception as exc:
        raise HTTPException(503, "Database or document storage unavailable") from exc
    return {"status": "ready"}


@app.post("/employees", response_model=EmployeeOut, status_code=201)
def create_employee(body: EmployeeCreate, session: DB):
    employee = Employee(**body.model_dump())
    session.add(employee)
    session.commit()
    return employee


@app.get("/employees", response_model=list[EmployeeOut])
def list_employees(session: DB, limit: Limit = 100, offset: Offset = 0):
    return session.scalars(
        select(Employee).order_by(Employee.created_at, Employee.id).offset(offset).limit(limit)
    ).all()


@app.get("/employees/{employee_id}", response_model=EmployeeOut)
def get_employee(employee_id: UUID, session: DB):
    return require(session, Employee, employee_id)


@app.post("/employees/{employee_id}/trips", response_model=TripOut, status_code=201)
def create_trip(employee_id: UUID, body: TripCreate, session: DB):
    require(session, Employee, employee_id)
    trip = Trip(employee_id=str(employee_id), **body.model_dump())
    session.add(trip)
    session.commit()
    return trip


@app.get("/employees/{employee_id}/trips", response_model=list[TripOut])
def list_trips(employee_id: UUID, session: DB, limit: Limit = 100, offset: Offset = 0):
    require(session, Employee, employee_id)
    return session.scalars(
        select(Trip)
        .where(Trip.employee_id == str(employee_id))
        .order_by(Trip.created_at, Trip.id)
        .offset(offset)
        .limit(limit)
    ).all()


@app.get("/trips/{trip_id}", response_model=TripOut)
def get_trip(trip_id: UUID, session: DB):
    return require(session, Trip, trip_id)


@app.get("/trips/{trip_id}/documents", response_model=list[DocumentOut])
def list_documents(trip_id: UUID, session: DB, limit: Limit = 100, offset: Offset = 0):
    require(session, Trip, trip_id)
    return session.scalars(
        select(Document)
        .where(Document.trip_id == str(trip_id))
        .order_by(Document.created_at, Document.id)
        .offset(offset)
        .limit(limit)
    ).all()


@app.post("/trips/{trip_id}/documents", response_model=DocumentOut, status_code=201)
def upload_document(trip_id: UUID, session: DB, store: Store, file: Annotated[UploadFile, File()]):
    settings = get_settings()
    require(session, Trip, trip_id)
    data = file.file.read(settings.max_upload_bytes + 1)
    file.file.close()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, "PDF exceeds the configured file size limit")
    try:
        pages = extract_pages(data, settings)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    lock_trip(session, trip_id)
    digest = hashlib.sha256(data).hexdigest()
    existing = session.scalar(
        select(Document).where(Document.trip_id == str(trip_id), Document.sha256 == digest)
    )
    if existing:
        raise HTTPException(
            409, {"message": "This PDF is already in the trip", "document_id": existing.id}
        )
    document_id = new_id()
    filename = (file.filename or "document.pdf").replace("\\", "/").rsplit("/", 1)[-1][:255]
    key = f"trips/{trip_id}/{document_id}.pdf"
    try:
        store.put(key, data)
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(503, "Document storage unavailable") from exc
    document = Document(
        id=document_id,
        trip_id=str(trip_id),
        filename=filename,
        object_key=key,
        sha256=digest,
        size_bytes=len(data),
        page_count=len(pages),
        pages=pages,
    )
    try:
        session.add(document)
        session.commit()
    except Exception:
        session.rollback()
        try:
            store.delete(key)
        except Exception:
            logger.exception("Could not clean up uncommitted object %s", key)
        raise
    return document


@app.get("/documents/{document_id}/download")
def download_document(document_id: UUID, session: DB, store: Store):
    document = require(session, Document, document_id)
    try:
        data = store.read(document.object_key)
    except (BotoCoreError, ClientError) as exc:
        raise HTTPException(503, "Document storage unavailable") from exc
    return Response(
        data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(document.filename, safe='')}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.post("/trips/{trip_id}/summaries", response_model=JobOut, status_code=202)
def generate_summary(trip_id: UUID, session: DB):
    lock_trip(session, trip_id)
    active = session.scalar(
        select(SummaryJob).where(
            SummaryJob.trip_id == str(trip_id), SummaryJob.status.in_(["queued", "running"])
        )
    )
    if active:
        return active
    ids = list(
        session.scalars(
            select(Document.id)
            .where(Document.trip_id == str(trip_id))
            .order_by(Document.created_at, Document.id)
        )
    )
    if not ids:
        raise HTTPException(409, "Upload at least one PDF before generating a summary")
    job = SummaryJob(
        trip_id=str(trip_id),
        document_ids=ids,
        model=get_settings().ollama_model,
        prompt_version=PROMPT_VERSION,
    )
    session.add(job)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "A summary is already queued or running") from exc
    return job


@app.get("/trips/{trip_id}/summaries", response_model=list[JobOut])
def list_summaries(trip_id: UUID, session: DB, limit: Limit = 100, offset: Offset = 0):
    require(session, Trip, trip_id)
    return session.scalars(
        select(SummaryJob)
        .where(SummaryJob.trip_id == str(trip_id))
        .order_by(SummaryJob.created_at.desc(), SummaryJob.id)
        .offset(offset)
        .limit(limit)
    ).all()


@app.get("/summary-jobs/{job_id}", response_model=JobOut)
def get_job(job_id: UUID, session: DB):
    return require(session, SummaryJob, job_id)


def result_for_job(job_id, session):
    job = require(session, SummaryJob, job_id)
    if job.result is None:
        raise HTTPException(409, {"status": job.status, "error": job.error})
    current_ids = set(session.scalars(select(Document.id).where(Document.trip_id == job.trip_id)))
    return {
        "job_id": job.id,
        "trip_id": job.trip_id,
        "status": job.status,
        "is_stale": current_ids != set(job.document_ids),
        **job.result,
    }


@app.get("/summary-jobs/{job_id}/result", response_model=SummaryResult)
def get_result(job_id: UUID, session: DB):
    return result_for_job(job_id, session)


@app.get("/summary-jobs/{job_id}/markdown")
def download_markdown(job_id: UUID, session: DB):
    result = result_for_job(job_id, session)
    return Response(
        result["markdown"],
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="summary-{job_id}.md"',
            "X-TERA-Stale": str(result["is_stale"]).lower(),
        },
    )
