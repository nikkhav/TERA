import hashlib
import logging
from copy import deepcopy
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tera.auth import (
    CurrentUser,
    authenticate_user,
    create_access_token,
    get_current_user,
    hash_password,
)
from tera.config import get_settings
from tera.corrections import corrected_record
from tera.db import get_session
from tera.exchange_rates import attach_rate
from tera.models import Document, Employee, SummaryJob, Trip, User, new_id, now
from tera.pdf import extract_pages
from tera.prompts import PROMPT_VERSION
from tera.reporting import make_report
from tera.schemas import (
    AuthResponse,
    CorrectionInput,
    DocumentOut,
    EmployeeCreate,
    EmployeeOut,
    JobOut,
    RegistrationStatus,
    ReviewInput,
    SummaryResult,
    TripCreate,
    TripOut,
    UserCreate,
    UserLogin,
    UserOut,
)
from tera.storage import ObjectStore, StorageError, get_store

app = FastAPI(
    title="TERA API",
    version="0.1.0",
    description="Travel expense document processing API",
)
DB = Annotated[Session, Depends(get_session)]
Store = Annotated[ObjectStore, Depends(get_store)]
Limit = Annotated[int, Query(ge=1, le=500)]
Offset = Annotated[int, Query(ge=0)]
logger = logging.getLogger(__name__)
protected = APIRouter(dependencies=[Depends(get_current_user)])


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
        store.check_health()
    except Exception as exc:
        raise HTTPException(503, "Database or document storage unavailable") from exc
    return {"status": "ready"}


@app.get("/auth/registration", response_model=RegistrationStatus)
def registration_status():
    return {"enabled": get_settings().auth_allow_registration}


@app.post("/auth/register", response_model=AuthResponse, status_code=201)
def register(body: UserCreate, session: DB):
    if not get_settings().auth_allow_registration:
        raise HTTPException(403, "Registration is disabled")
    user = User(
        email=body.email,
        display_name=body.display_name,
        password_hash=hash_password(body.password),
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(409, "An account with this email already exists") from exc
    return {"access_token": create_access_token(user), "user": user}


@app.post("/auth/login", response_model=AuthResponse)
def login(body: UserLogin, session: DB):
    user = authenticate_user(session, body.email, body.password)
    if user is None:
        raise HTTPException(401, "Invalid email or password")
    return {"access_token": create_access_token(user), "user": user}


@app.get("/auth/me", response_model=UserOut)
def me(user: CurrentUser):
    return user


@protected.post("/employees", response_model=EmployeeOut, status_code=201)
def create_employee(body: EmployeeCreate, session: DB):
    employee = Employee(**body.model_dump())
    session.add(employee)
    session.commit()
    return employee


@protected.get("/employees", response_model=list[EmployeeOut])
def list_employees(session: DB, limit: Limit = 100, offset: Offset = 0):
    return session.scalars(
        select(Employee)
        .order_by(func.lower(Employee.name), Employee.id)
        .offset(offset)
        .limit(limit)
    ).all()


@protected.get("/employees/{employee_id}", response_model=EmployeeOut)
def get_employee(employee_id: UUID, session: DB):
    return require(session, Employee, employee_id)


@protected.post("/employees/{employee_id}/trips", response_model=TripOut, status_code=201)
def create_trip(employee_id: UUID, body: TripCreate, session: DB):
    require(session, Employee, employee_id)
    trip = Trip(employee_id=str(employee_id), **body.model_dump())
    session.add(trip)
    session.commit()
    return trip


@protected.get("/employees/{employee_id}/trips", response_model=list[TripOut])
def list_trips(employee_id: UUID, session: DB, limit: Limit = 100, offset: Offset = 0):
    require(session, Employee, employee_id)
    return session.scalars(
        select(Trip)
        .where(Trip.employee_id == str(employee_id))
        .order_by(Trip.created_at, Trip.id)
        .offset(offset)
        .limit(limit)
    ).all()


@protected.put("/trips/{trip_id}", response_model=TripOut)
def update_trip(trip_id: UUID, body: TripCreate, session: DB):
    trip = lock_trip(session, trip_id)
    for field, value in body.model_dump().items():
        setattr(trip, field, value)
    session.commit()
    return trip


@protected.get("/trips/{trip_id}", response_model=TripOut)
def get_trip(trip_id: UUID, session: DB):
    return require(session, Trip, trip_id)


@protected.get("/trips/{trip_id}/documents", response_model=list[DocumentOut])
def list_documents(trip_id: UUID, session: DB, limit: Limit = 100, offset: Offset = 0):
    require(session, Trip, trip_id)
    return session.scalars(
        select(Document)
        .where(Document.trip_id == str(trip_id))
        .order_by(Document.created_at, Document.id)
        .offset(offset)
        .limit(limit)
    ).all()


@protected.post("/trips/{trip_id}/documents", response_model=DocumentOut, status_code=201)
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
    except (BotoCoreError, ClientError, StorageError) as exc:
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


@protected.get("/documents/{document_id}/download")
def download_document(document_id: UUID, session: DB, store: Store):
    document = require(session, Document, document_id)
    try:
        data = store.read(document.object_key)
    except (BotoCoreError, ClientError, StorageError) as exc:
        raise HTTPException(503, "Document storage unavailable") from exc
    return Response(
        data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(document.filename, safe='')}",
            "X-Content-Type-Options": "nosniff",
        },
    )


@protected.post("/trips/{trip_id}/summaries", response_model=JobOut, status_code=202)
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
    logger.info(
        "summary_queued job_id=%s trip_id=%s documents=%s model=%s",
        job.id,
        trip_id,
        len(ids),
        job.model,
    )
    return job


@protected.get("/trips/{trip_id}/summaries", response_model=list[JobOut])
def list_summaries(trip_id: UUID, session: DB, limit: Limit = 100, offset: Offset = 0):
    require(session, Trip, trip_id)
    return session.scalars(
        select(SummaryJob)
        .where(SummaryJob.trip_id == str(trip_id))
        .order_by(SummaryJob.created_at.desc(), SummaryJob.id)
        .offset(offset)
        .limit(limit)
    ).all()


@protected.get("/summary-jobs/{job_id}", response_model=JobOut)
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


@protected.get("/summary-jobs/{job_id}/result", response_model=SummaryResult)
def get_result(job_id: UUID, session: DB):
    return result_for_job(job_id, session)


@protected.put(
    "/summary-jobs/{job_id}/documents/{document_id}/review", response_model=SummaryResult
)
def review_document(
    job_id: UUID, document_id: UUID, body: ReviewInput, session: DB, user: CurrentUser
):
    job = session.scalar(select(SummaryJob).where(SummaryJob.id == str(job_id)).with_for_update())
    if job is None:
        raise HTTPException(404, "Auswertung nicht gefunden.")
    if job.status in {"queued", "running"} or job.result is None:
        raise HTTPException(409, "Die Auswertung ist noch nicht abgeschlossen.")
    result = deepcopy(job.result)
    record = next((r for r in result["documents"] if r["document_id"] == str(document_id)), None)
    if record is None:
        raise HTTPException(404, "Beleg gehört nicht zu dieser Auswertung.")
    if body.decision == "approved":
        expenses = [e for e in result["expenses"] if e["document_id"] == str(document_id)]
        if (
            record["extraction_failed"]
            or not expenses
            or any(e["amount"] is None or e["currency"] is None for e in expenses)
        ):
            raise HTTPException(409, "Fehlende Beträge oder Währungen: Beleg zuerst neu auswerten.")
    record.setdefault("review_history", []).append(
        {
            "decision": body.decision,
            "comment": body.comment.strip(),
            "user_id": user.id,
            "user_name": user.display_name,
            "reviewed_at": now().isoformat(),
        }
    )
    job.result = make_report(result["documents"], result["model"], result["prompt_version"])
    job.status = "needs_review" if job.result["coverage"]["needs_review"] else "completed"
    if job.result["coverage"]["failed"] == job.result["coverage"]["supplied"]:
        job.status = "failed"
    session.commit()
    logger.info(
        "document_reviewed job_id=%s document_id=%s user_id=%s decision=%s",
        job.id,
        document_id,
        user.id,
        body.decision,
    )
    return result_for_job(job_id, session)


@protected.put(
    "/summary-jobs/{job_id}/documents/{document_id}/correction", response_model=SummaryResult
)
def correct_document(
    job_id: UUID, document_id: UUID, body: CorrectionInput, session: DB, user: CurrentUser
):
    job = session.scalar(select(SummaryJob).where(SummaryJob.id == str(job_id)).with_for_update())
    if job is None:
        raise HTTPException(404, "Auswertung nicht gefunden.")
    if job.status in {"queued", "running"} or job.result is None:
        raise HTTPException(409, "Die Auswertung ist noch nicht abgeschlossen.")
    result = deepcopy(job.result)
    records = result["documents"]
    index = next((i for i, r in enumerate(records) if r["document_id"] == str(document_id)), None)
    if index is None:
        raise HTTPException(404, "Beleg gehört nicht zu dieser Auswertung.")
    try:
        records[index] = corrected_record(
            records[index], body.facts, user.id, user.display_name, now().isoformat(), body.comment
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    attach_rate(records[index])
    job.result = make_report(records, result["model"], result["prompt_version"])
    job.status = "needs_review" if job.result["coverage"]["needs_review"] else "completed"
    session.commit()
    logger.info(
        "document_corrected job_id=%s document_id=%s user_id=%s", job.id, document_id, user.id
    )
    return result_for_job(job_id, session)


app.include_router(protected)
