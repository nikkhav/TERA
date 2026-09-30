from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tera.api import app
from tera.chunking import chunk_pages, prompt_budget
from tera.config import Settings
from tera.db import get_session
from tera.jobs import LostLease, claim_job, update_job
from tera.models import Base, SummaryJob, now
from tera.pdf import extract_pages
from tera.prompts import build_prompt
from tera.reporting import make_report, merge_fragments
from tera.schemas import ReceiptFacts
from tera.storage import get_store
from tera.worker import process_job

DATA = Path(__file__).resolve().parents[1] / "research" / "data"


class MemoryStore:
    def __init__(self):
        self.objects = {}

    def put(self, key, data):
        self.objects[key] = data

    def read(self, key):
        return self.objects[key]

    def delete(self, key):
        del self.objects[key]


@pytest.fixture
def api():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    store = MemoryStore()

    def sessions():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    app.dependency_overrides[get_store] = lambda: store
    with TestClient(app) as client:
        auth = client.post(
            "/auth/register",
            json={
                "email": "test@example.com",
                "display_name": "Test User",
                "password": "correct horse battery staple",
            },
        )
        assert auth.status_code == 201, auth.text
        client.headers["Authorization"] = f"Bearer {auth.json()['access_token']}"
        yield client, factory, store
    app.dependency_overrides.clear()
    engine.dispose()


def trip(client):
    employee = client.post("/employees", json={"name": "Alex"}).json()
    response = client.post(f"/employees/{employee['id']}/trips", json={"name": "Berlin"})
    assert response.status_code == 201
    return response.json()["id"]


def upload(client, trip_id, name="hotel_invoice.pdf"):
    return client.post(
        f"/trips/{trip_id}/documents",
        files={"file": (name, (DATA / name).read_bytes(), "application/pdf")},
    )


class FakeExtractor:
    def extract(self, document_id, pages):
        return ReceiptFacts(
            merchant="Hotel",
            invoice_number="INV-1",
            invoice_date=date(2026, 9, 14),
            category="Hotel",
            currency="EUR",
            total="712.60",
            breakfast_total="71.40",
            items=[
                {"description": "Unterkunft", "category": "Hotel", "gross": "641.20"},
                {
                    "description": "Frühstück",
                    "category": "Verpflegung",
                    "gross": "71.40",
                    "is_breakfast": True,
                },
            ],
            evidence=[{"page": pages[0]["page"], "quote": "Hotel"}],
        )


def test_employee_list_is_sorted_and_paginated(api):
    client, _, _ = api
    for name in ("Zulu", "beta", "Alpha"):
        assert client.post("/employees", json={"name": name}).status_code == 201
    first_page = client.get("/employees", params={"limit": 2, "offset": 0}).json()
    second_page = client.get("/employees", params={"limit": 2, "offset": 2}).json()
    assert [employee["name"] for employee in first_page] == ["Alpha", "beta"]
    assert [employee["name"] for employee in second_page] == ["Zulu"]


def test_complete_api_workflow_and_snapshot(api):
    client, factory, store = api
    tid = trip(client)
    assert client.post(f"/trips/{tid}/summaries").status_code == 409
    document = upload(client, tid)
    assert document.status_code == 201
    doc_id = document.json()["id"]
    assert (
        client.get(f"/documents/{doc_id}/download").content
        == (DATA / "hotel_invoice.pdf").read_bytes()
    )
    assert len(store.objects) == 1
    assert upload(client, tid).status_code == 409
    job = client.post(f"/trips/{tid}/summaries").json()
    assert client.post(f"/trips/{tid}/summaries").json()["id"] == job["id"]
    assert client.get(f"/summary-jobs/{job['id']}/result").status_code == 409
    settings = Settings(_env_file=None)
    claim = claim_job(factory, settings)
    assert claim_job(factory, settings) is None
    process_job(factory, settings, *claim, extractor=FakeExtractor())
    result = client.get(f"/summary-jobs/{job['id']}/result").json()
    assert result["status"] == "completed"
    assert result["is_stale"] is False
    assert result["totals"]["by_currency"][0]["confirmed"] == "712.60"
    assert [e["amount"] for e in result["expenses"]] == ["641.20", "71.40"]
    assert "markdown" not in result
    assert client.get(f"/summary-jobs/{job['id']}/markdown").status_code == 404
    upload(client, tid, "hotel_invoice_zh.pdf")
    assert client.get(f"/summary-jobs/{job['id']}/result").json()["is_stale"] is True
    assert len(result["documents"]) == 1


def test_failed_extraction_is_visible(api):
    client, factory, _ = api
    tid = trip(client)
    upload(client, tid)
    job = client.post(f"/trips/{tid}/summaries").json()

    class BrokenExtractor:
        def extract(self, *_, **kwargs):
            raise TimeoutError("offline")

    settings = Settings(_env_file=None)
    process_job(factory, settings, *claim_job(factory, settings), extractor=BrokenExtractor())
    result = client.get(f"/summary-jobs/{job['id']}/result").json()
    assert result["status"] == "failed"
    assert result["coverage"]["failed"] == 1
    assert result["expenses"][0]["amount"] is None
    assert result["totals"]["by_currency"][0]["unknown_amounts"] == 1


def test_expired_lease_and_stale_worker(api):
    client, factory, _ = api
    tid = trip(client)
    upload(client, tid)
    client.post(f"/trips/{tid}/summaries")
    settings = Settings(_env_file=None)
    first = claim_job(factory, settings)
    with factory.begin() as session:
        session.get(SummaryJob, first[0]).lease_until = now() - timedelta(seconds=1)
    second = claim_job(factory, settings)
    assert first[0] == second[0] and first[1] != second[1]
    with pytest.raises(LostLease):
        update_job(factory, settings, *first, completed_chunks=1)


def test_bad_uploads_and_invalid_names(api):
    client, _, store = api
    assert client.post("/employees", json={"name": "  "}).status_code == 422
    tid = trip(client)
    response = client.post(f"/trips/{tid}/documents", files={"file": ("x.pdf", b"not a pdf")})
    assert response.status_code == 422
    assert not store.objects
    with pymupdf.open() as pdf:
        pdf.new_page()
        response = client.post(
            f"/trips/{tid}/documents", files={"file": ("scan.pdf", pdf.tobytes())}
        )
    assert response.status_code == 422
    assert not store.objects


def test_chunking_preserves_multilingual_text_and_bounds_every_request():
    settings = Settings(_env_file=None)
    pages = [
        {"page": 1, "text": '早餐 60元\\"\n' * 1400},
        {"page": 2, "text": "Gesamtbetrag 712,60 EUR"},
    ]
    chunks = chunk_pages("receipt", pages, settings)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(build_prompt("receipt", chunk).encode()) <= prompt_budget(settings)
    for page in pages:
        recovered = "".join(
            p["text"] for chunk in chunks for p in chunk if p["page"] == page["page"]
        )
        assert recovered == page["text"]


def test_pdf_text_in_both_languages():
    settings = Settings(_env_file=None)
    assert (
        "NORTHSTAR" in extract_pages((DATA / "hotel_invoice.pdf").read_bytes(), settings)[0]["text"]
    )
    assert (
        "上海晨星酒店"
        in extract_pages((DATA / "hotel_invoice_zh.pdf").read_bytes(), settings)[0]["text"]
    )


def record(currency="EUR", total="712.60", breakfast="71.40", identifier="a", invoice="INV-1"):
    document = SimpleNamespace(id=identifier, filename="hotel.pdf", sha256=identifier, page_count=1)
    facts = ReceiptFacts(
        merchant="Hotel",
        invoice_number=invoice,
        invoice_date="2026-09-14",
        category="Hotel",
        currency=currency,
        total=total,
        breakfast_total=breakfast,
        items=[
            {
                "description": "Unterkunft",
                "category": "Hotel",
                "gross": str(Decimal(total) - Decimal(breakfast or "0")),
            },
        ]
        + (
            [
                {
                    "description": "Frühstück",
                    "category": "Verpflegung",
                    "gross": breakfast,
                    "is_breakfast": True,
                }
            ]
            if breakfast
            else []
        ),
        evidence=[{"page": 1, "quote": "Hotel"}],
    )
    chunks = [[{"page": 1, "part": 1, "text": "Hotel"}]]
    return merge_fragments(document, [facts], [], chunks)


def test_currency_separation_and_no_double_counting():
    report = make_report([record(), record("CNY", "2220", "180", "b")], "test", "test")
    totals = {t["currency"]: t["confirmed"] for t in report["totals"]["by_currency"]}
    assert totals == {"CNY": "2220", "EUR": "712.60"}
    assert len(report["totals"]["by_category"]) == 8


def test_duplicates_are_not_confirmed():
    report = make_report([record(), record(identifier="b")], "test", "test")
    assert report["totals"]["by_currency"][0]["confirmed"] == "0"
    assert report["coverage"]["needs_review"] == 2


def test_conflicting_fragments_are_not_summed():
    document = SimpleNamespace(id="a", filename="bill.pdf", sha256="a", page_count=2)
    fragments = [ReceiptFacts(total="100"), ReceiptFacts(total="200")]
    merged = merge_fragments(document, fragments, [], [])
    assert merged["facts"]["total"] is None
    assert any("Widersprüchliche" in w for w in merged["warnings"])


def test_missing_breakfast_keeps_total():
    item = record(breakfast=None)
    report = make_report([item], "test", "test")
    assert report["expenses"][0]["amount"] == "712.60"
    assert report["accommodation"][0]["without_breakfast"] is None


def test_manual_review_persists_audit_and_recalculates_totals(api):
    from uuid import uuid4

    client, factory, _ = api
    tid = trip(client)
    doc_id = upload(client, tid).json()["id"]
    job_id = client.post(f"/trips/{tid}/summaries").json()["id"]
    url = f"/summary-jobs/{job_id}/documents/{doc_id}/review"
    assert client.put(url, json={"decision": "approved"}).status_code == 409

    class UncertainExtractor(FakeExtractor):
        def extract(self, document_id, pages, feedback=None):
            facts = super().extract(document_id, pages)
            facts.notes = ["Bitte Rechnungsdatum prüfen."]
            return facts

    settings = Settings(_env_file=None)
    process_job(factory, settings, *claim_job(factory, settings), extractor=UncertainExtractor())
    response = client.put(url, json={"decision": "approved", "comment": "Mit PDF abgeglichen"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "completed" and not result["warnings"]
    assert result["totals"]["by_currency"][0]["confirmed"] == "712.60"
    assert result["documents"][0]["warnings"]  # Original findings are retained.
    event = result["documents"][0]["review_history"][0]
    assert event["user_name"] == "Test User" and event["reviewed_at"]
    assert event["comment"] == "Mit PDF abgeglichen"
    result = client.put(url, json={"decision": "rejected"}).json()
    total = result["totals"]["by_currency"][0]
    assert total["confirmed"] == "0" and total["in_review"] == "0"
    assert total["excluded"] == "712.60"
    assert all(e["status"] == "rejected" for e in result["expenses"])
    result = client.put(url, json={"decision": "pending"}).json()
    assert result["status"] == "needs_review"
    assert result["warnings"][0]["filename"] == "hotel_invoice.pdf"
    assert len(result["documents"][0]["review_history"]) == 3
    assert client.get(f"/summary-jobs/{job_id}/result").json() == result
    assert (
        client.put(url.replace(doc_id, str(uuid4())), json={"decision": "approved"}).status_code
        == 404
    )
    client.headers.pop("Authorization")
    assert client.put(url, json={"decision": "approved"}).status_code == 401


def test_incomplete_extraction_cannot_be_manually_approved(api):
    client, factory, _ = api
    tid = trip(client)
    doc_id = upload(client, tid).json()["id"]
    job_id = client.post(f"/trips/{tid}/summaries").json()["id"]

    class BrokenExtractor:
        def extract(self, *_, **kwargs):
            raise TimeoutError("offline")

    settings = Settings(_env_file=None)
    process_job(factory, settings, *claim_job(factory, settings), extractor=BrokenExtractor())
    response = client.put(
        f"/summary-jobs/{job_id}/documents/{doc_id}/review", json={"decision": "approved"}
    )
    assert response.status_code == 409


def test_trip_can_be_edited_without_changing_documents_or_employee(api):
    client, _, _ = api
    tid = trip(client)
    document = upload(client, tid).json()
    original = client.get(f"/trips/{tid}").json()
    response = client.put(
        f"/trips/{tid}",
        json={
            "name": "Hamburg",
            "starts_on": "2026-10-01",
            "ends_on": "2026-10-04",
        },
    )
    assert response.status_code == 200
    updated = response.json()
    assert updated["id"] == tid and updated["employee_id"] == original["employee_id"]
    assert updated["name"] == "Hamburg" and updated["ends_on"] == "2026-10-04"
    assert client.get(f"/trips/{tid}/documents").json()[0]["id"] == document["id"]
    assert client.get(f"/employees/{original['employee_id']}/trips").json() == [updated]
    assert client.put(f"/trips/{tid}", json={"name": " "}).status_code == 422
    assert (
        client.put(
            f"/trips/{tid}",
            json={"name": "Invalid", "starts_on": "2026-10-05", "ends_on": "2026-10-01"},
        ).status_code
        == 422
    )
    assert client.get(f"/trips/{tid}").json() == updated
    cleared = client.put(
        f"/trips/{tid}", json={"name": "Hamburg", "starts_on": None, "ends_on": None}
    )
    assert cleared.json()["starts_on"] is None
    client.headers.pop("Authorization")
    assert client.put(f"/trips/{tid}", json={"name": "Unauthorized"}).status_code == 401


def test_manual_correction_validates_audits_and_recalculates(api):
    client, factory, _ = api
    tid = trip(client)
    doc_id = upload(client, tid).json()["id"]
    job_id = client.post(f"/trips/{tid}/summaries").json()["id"]
    settings = Settings(_env_file=None)
    process_job(factory, settings, *claim_job(factory, settings), extractor=FakeExtractor())
    result_url = f"/summary-jobs/{job_id}/result"
    url = f"/summary-jobs/{job_id}/documents/{doc_id}/correction"
    before = client.get(result_url).json()["documents"][0]["facts"]
    facts = {
        **before,
        "total": "100",
        "breakfast_total": None,
        "breakfast_net": None,
        "breakfast_tax": None,
        "items": [{"description": "Korrigierte Unterkunft", "category": "Hotel", "gross": "100"}],
    }
    invalid = client.put(url, json={"facts": {**facts, "total": "200"}})
    assert invalid.status_code == 422
    assert client.get(result_url).json()["documents"][0]["facts"] == before
    response = client.put(url, json={"facts": facts, "comment": "Im Original geprüft"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["totals"]["by_currency"][0]["confirmed"] == "100"
    assert result["totals"]["eur"][0]["confirmed"] == "100.00"
    assert result["documents"][0]["status"] == "approved"
    event = result["documents"][0]["correction_history"][0]
    assert event["before"]["total"] == before["total"]
    assert event["after"]["total"] == "100"
    assert event["user_name"] == "Test User"
    assert client.get(result_url).json() == result
    reset = client.put(url.replace("/correction", "/review"), json={"decision": "pending"}).json()
    assert reset["documents"][0]["status"] == "needs_review"
    client.headers.pop("Authorization")
    assert client.put(url, json={"facts": facts}).status_code == 401
