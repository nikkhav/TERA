from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Category(str, Enum):
    HOTEL = "Hotel"
    FLIGHTS = "Flugreisen"
    MEALS = "Verpflegung"
    OTHER = "Sonstige Ausgaben"


class EmployeeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def strip_name(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("Name cannot be blank")
        return self


class EmployeeOut(EmployeeCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    created_at: datetime


class TripCreate(EmployeeCreate):
    starts_on: date | None = None
    ends_on: date | None = None

    @model_validator(mode="after")
    def dates_in_order(self):
        if self.starts_on and self.ends_on and self.starts_on > self.ends_on:
            raise ValueError("Trip end precedes its start")
        return self


class TripOut(TripCreate):
    model_config = ConfigDict(from_attributes=True)
    id: str
    employee_id: str
    created_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    trip_id: str
    filename: str
    sha256: str
    size_bytes: int
    page_count: int
    created_at: datetime


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    trip_id: str
    status: str
    document_ids: list[str]
    model: str
    prompt_version: str
    attempts: int
    completed_chunks: int
    total_chunks: int
    error: str | None
    created_at: datetime
    finished_at: datetime | None


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    page: int = Field(ge=1)
    quote: str = Field(min_length=1, max_length=1000)


class ReceiptFacts(BaseModel):
    """Internal validation only: this schema is never sent to the model."""

    model_config = ConfigDict(extra="forbid")
    merchant: str | None = Field(default=None, max_length=500)
    invoice_number: str | None = Field(default=None, max_length=200)
    invoice_date: date | None = None
    service_start: date | None = None
    service_end: date | None = None
    category: Category | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    total: Decimal | None = Field(
        default=None, max_digits=18, decimal_places=6, allow_inf_nan=False
    )
    breakfast_total: Decimal | None = Field(
        default=None, max_digits=18, decimal_places=6, allow_inf_nan=False
    )
    multiple_receipts: bool = False
    notes: list[str] = Field(default_factory=list, max_length=50)
    evidence: list[Evidence] = Field(default_factory=list, max_length=50)


class Coverage(BaseModel):
    supplied: int
    processed: int
    failed: int
    needs_review: int


class Source(Evidence):
    document_id: str


class DocumentResult(BaseModel):
    document_id: str
    filename: str
    sha256: str
    page_count: int
    facts: ReceiptFacts
    sources: list[Source]
    warnings: list[str]
    extraction_failed: bool
    status: str


class ExpenseBase(BaseModel):
    document_id: str
    filename: str
    date: str | None
    service_start: str | None
    service_end: str | None
    merchant: str | None
    currency: str | None
    status: str
    pages: list[int]


class Expense(ExpenseBase):
    category: Category
    description: str
    amount: str | None


class Accommodation(ExpenseBase):
    total: str | None
    breakfast: str | None
    without_breakfast: str | None


class CurrencyTotal(BaseModel):
    currency: str | None
    confirmed: str
    in_review: str
    unknown_amounts: int


class DateTotal(CurrencyTotal):
    date: str | None


class CategoryTotal(CurrencyTotal):
    category: Category


class Totals(BaseModel):
    by_currency: list[CurrencyTotal]
    by_date: list[DateTotal]
    by_category: list[CategoryTotal]


class ReviewNote(BaseModel):
    document_id: str
    message: str


class SummaryResult(BaseModel):
    schema_version: int
    job_id: str
    trip_id: str
    status: str
    is_stale: bool
    language: str
    model: str
    prompt_version: str
    coverage: Coverage
    documents: list[DocumentResult]
    expenses: list[Expense]
    accommodation: list[Accommodation]
    totals: Totals
    warnings: list[ReviewNote]
    markdown: str
