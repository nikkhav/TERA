from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(UTC)


def new_id():
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class Employee(Base):
    __tablename__ = "employees"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Trip(Base):
    __tablename__ = "trips"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    starts_on: Mapped[date | None]
    ends_on: Mapped[date | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("trip_id", "sha256", name="uq_document_trip_hash"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id"), index=True)
    filename: Mapped[str] = mapped_column(String(255))
    object_key: Mapped[str] = mapped_column(String(500), unique=True)
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int]
    page_count: Mapped[int]
    pages: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SummaryJob(Base):
    __tablename__ = "summary_jobs"
    __table_args__ = (
        Index(
            "uq_active_job_per_trip",
            "trip_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
            sqlite_where=text("status IN ('queued', 'running')"),
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    document_ids: Mapped[list] = mapped_column(JSON)
    model: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(default=0)
    lease_token: Mapped[str | None] = mapped_column(String(36))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_chunks: Mapped[int] = mapped_column(default=0)
    total_chunks: Mapped[int] = mapped_column(default=0)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
