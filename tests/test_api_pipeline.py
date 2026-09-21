from datetime import date, timedelta
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
            evidence=[{"page": pages[0]["page"], "quote": "Hotel"}],
        )


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
    assert "641,20" in result["markdown"]
    assert client.get(f"/summary-jobs/{job['id']}/markdown").status_code == 200
    upload(client, tid, "hotel_invoice_zh.pdf")
    assert client.get(f"/summary-jobs/{job['id']}/result").json()["is_stale"] is True
    assert len(result["documents"]) == 1


def test_failed_extraction_is_visible(api):
    client, factory, _ = api
    tid = trip(client)
    upload(client, tid)
    job = client.post(f"/trips/{tid}/summaries").json()

    class BrokenExtractor:
        def extract(self, *_):
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


def test_missing_breakfast_keeps_total_and_markdown_escapes_content():
    item = record(breakfast=None)
    item["facts"]["merchant"] = "<script>evil</script> | [click](https://example.com)\n# Heading"
    report = make_report([item], "test", "test")
    assert report["expenses"][0]["amount"] == "712.60"
    assert report["accommodation"][0]["without_breakfast"] is None
    assert "<script>" not in report["markdown"]
    assert "\\|" in report["markdown"]
    assert "\\[click\\]" in report["markdown"]
