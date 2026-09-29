from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Category(str, Enum):
    HOTEL = "Hotel"
    FLIGHTS = "Flugreisen"
    MEALS = "Verpflegung"
    OTHER = "Sonstige Ausgaben"


class UserCreate(BaseModel):
    email: str = Field(min_length=5, max_length=320, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def strip_email(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def normalize(self):
        self.email = self.email.strip().casefold()
        self.display_name = self.display_name.strip()
        if not self.display_name:
            raise ValueError("Display name cannot be blank")
        return self


class UserLogin(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    display_name: str
    created_at: datetime


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class RegistrationStatus(BaseModel):
    enabled: bool


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
    field: str | None = Field(default=None, max_length=100)


Money = Annotated[Decimal, Field(max_digits=18, decimal_places=6, allow_inf_nan=False)]


class ItemEvidence(Evidence):
    field: str | None = Field(
        default=None,
        max_length=100,
        json_schema_extra={"enum": ["net", "tax", "gross", "description", None]},
    )


class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: str = Field(min_length=1, max_length=500)
    category: Category | None = None
    net: Money | None = None
    tax: Money | None = None
    gross: Money | None = None
    is_breakfast: bool = False
    evidence: list[ItemEvidence] = Field(default_factory=list, max_length=20)


class ReceiptFacts(BaseModel):
    """Structured extraction contract and internal validation."""

    model_config = ConfigDict(extra="forbid")
    merchant: str | None = Field(default=None, max_length=500)
    invoice_number: str | None = Field(default=None, max_length=200)
    invoice_date: date | None = None
    service_start: date | None = None
    service_end: date | None = None
    category: Category | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    total: Money | None = None
    net_total: Money | None = None
    tax_total: Money | None = None
    breakfast_total: Money | None = None
    breakfast_net: Money | None = None
    breakfast_tax: Money | None = None
    items: list[LineItem] = Field(default_factory=list, max_length=200)
    multiple_receipts: bool = False
    notes: list[str] = Field(default_factory=list, max_length=50)
    notices: list[str] = Field(default_factory=list, max_length=50)
    evidence: list[Evidence] = Field(default_factory=list, max_length=50)


class Coverage(BaseModel):
    supplied: int
    processed: int
    failed: int
    needs_review: int


class Source(Evidence):
    document_id: str


class ValidationIssue(BaseModel):
    code: str
    message: str
    fields: list[str] = Field(default_factory=list)
    pages: list[int] = Field(default_factory=list)


class ReviewInput(BaseModel):
    decision: Literal["approved", "rejected", "pending"]
    comment: str = Field(default="", max_length=2000)


class ReviewEvent(ReviewInput):
    user_id: str
    user_name: str
    reviewed_at: datetime


class DocumentResult(BaseModel):
    document_id: str
    filename: str
    sha256: str
    page_count: int
    facts: ReceiptFacts
    sources: list[Source]
    warnings: list[str]
    notices: list[str] = Field(default_factory=list)
    extraction_failed: bool
    status: str
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    items_reconciled: bool = False
    recheck_attempted: bool = False
    initial_issues: list[ValidationIssue] = Field(default_factory=list)
    derived_fields: list[str] = Field(default_factory=list)
    review_history: list[ReviewEvent] = Field(default_factory=list)


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
    excluded: str = "0"
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
    filename: str = ""
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
    notices: list[ReviewNote] = Field(default_factory=list)
