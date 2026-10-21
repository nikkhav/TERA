from copy import deepcopy
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
        # Emit the fixed receipt only for the first part, including correction passes.
        if pages[0].get("text_start", 0) != 0:
            return ReceiptFacts()
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


class CountingExtractor(FakeExtractor):
    def __init__(self):
        self.document_ids = []

    def extract(self, document_id, pages, **kwargs):
        self.document_ids.append(document_id)
        return super().extract(document_id, pages)


def upload_distinct_receipt(client, tid, index):
    with pymupdf.open(DATA / "hotel_invoice.pdf") as pdf:
        pdf.set_metadata({"title": f"Receipt {index}"})
        data = pdf.tobytes()
    response = client.post(
        f"/trips/{tid}/documents",
        files={"file": (f"receipt-{index}.pdf", data, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_incremental_five_plus_one_preserves_decisions_and_rebuilds_links(api):
    client, factory, _ = api
    tid = trip(client)
    ids = [upload_distinct_receipt(client, tid, i) for i in range(5)]
    settings = Settings(_env_file=None)
    first = client.post(f"/trips/{tid}/summaries").json()
    extractor = CountingExtractor()
    process_job(factory, settings, *claim_job(factory, settings), extractor=extractor)
    assert set(extractor.document_ids) == set(ids)
    result = client.get(f"/summary-jobs/{first['id']}/result").json()
    facts = result["documents"][2]["facts"]
    facts["merchant"] = "Manually corrected hotel"
    corrected = client.put(
        f"/summary-jobs/{first['id']}/documents/{ids[2]}/correction",
        json={"facts": facts},
    )
    assert corrected.status_code == 200, corrected.text
    grouped = client.put(
        f"/summary-jobs/{first['id']}/relationships",
        json={"document_ids": ids[:2], "resolution": "same_expense", "primary_document_id": ids[0]},
    )
    assert grouped.status_code == 200, grouped.text
    before = {r["document_id"]: r for r in grouped.json()["documents"]}
    new_id = upload_distinct_receipt(client, tid, 5)
    second = client.post(f"/trips/{tid}/summaries").json()
    assert second["reused_documents"] == second["completed_documents"] == 5
    extractor = CountingExtractor()
    process_job(factory, settings, *claim_job(factory, settings), extractor=extractor)
    assert set(extractor.document_ids) == {new_id}
    result = client.get(f"/summary-jobs/{second['id']}/result").json()
    assert len(result["documents"]) == 6
    assert client.get(f"/summary-jobs/{second['id']}").json()["completed_documents"] == 6
    for record in result["documents"]:
        if record["document_id"] not in before:
            assert record["related_document_ids"]  # New document checked against saved ones.
            continue
        old = before[record["document_id"]]
        for key in ("facts", "review_history", "correction_history", "relationship_history"):
            assert record.get(key) == old.get(key)
    assert (
        next(r for r in result["documents"] if r["document_id"] == ids[1])["duplicate_of"] == ids[0]
    )
    # An unchanged set needs no model calls, and deletion only rebuilds the report.
    assert client.delete(f"/documents/{new_id}").status_code == 204
    third = client.post(f"/trips/{tid}/summaries").json()
    assert third["reused_documents"] == 5
    extractor = CountingExtractor()
    process_job(factory, settings, *claim_job(factory, settings), extractor=extractor)
    assert not extractor.document_ids
    final = client.get(f"/summary-jobs/{third['id']}/result").json()
    assert len(final["documents"]) == 5
    assert all(new_id not in r["related_document_ids"] for r in final["documents"])
    # Explicit full analysis bypasses saved results.
    forced = client.post(f"/trips/{tid}/summaries?force=true").json()
    assert forced["reused_documents"] == 0
    extractor = CountingExtractor()
    process_job(factory, settings, *claim_job(factory, settings), extractor=extractor)
    assert set(extractor.document_ids) == set(ids)


@pytest.mark.parametrize("invalidation", ["legacy", "configuration", "hash", "failed"])
def test_incremental_does_not_reuse_incompatible_or_failed_results(api, invalidation):
    client, factory, _ = api
    tid = trip(client)
    doc_id = upload(client, tid).json()["id"]
    first = client.post(f"/trips/{tid}/summaries").json()
    settings = Settings(_env_file=None)
    process_job(factory, settings, *claim_job(factory, settings), extractor=FakeExtractor())
    with factory.begin() as session:
        job = session.get(SummaryJob, first["id"])
        if invalidation == "legacy":
            job.processing_snapshot = None
        elif invalidation == "failed":
            result = deepcopy(job.result)
            result["documents"][0]["extraction_failed"] = True
            job.result = result
        else:
            snapshot = dict(job.processing_snapshot)
            if invalidation == "configuration":
                snapshot["fingerprint"] = "outdated"
            else:
                snapshot["hashes"] = {doc_id: "changed"}
            job.processing_snapshot = snapshot
    second = client.post(f"/trips/{tid}/summaries").json()
    assert second["reused_documents"] == 0
    extractor = CountingExtractor()
    process_job(factory, settings, *claim_job(factory, settings), extractor=extractor)
    assert set(extractor.document_ids) == {doc_id}


def test_employee_list_is_sorted_and_paginated(api):
    client, _, _ = api
    for name in ("Zulu", "beta", "Alpha"):
        assert client.post("/employees", json={"name": name}).status_code == 201
    first_page = client.get("/employees", params={"limit": 2, "offset": 0}).json()
    second_page = client.get("/employees", params={"limit": 2, "offset": 2}).json()
    assert [employee["name"] for employee in first_page] == ["Alpha", "beta"]
    assert [employee["name"] for employee in second_page] == ["Zulu"]


def test_saved_flight_report_shows_printed_round_trip_without_regeneration(api):
    from tera.models import Document

    client, factory, _ = api
    tid = trip(client)
    doc_id = upload(client, tid).json()["id"]
    first = client.post(f"/trips/{tid}/summaries").json()
    settings = Settings(_env_file=None)
    process_job(factory, settings, *claim_job(factory, settings), extractor=FakeExtractor())
    with factory.begin() as session:
        job = session.get(SummaryJob, first["id"])
        result = deepcopy(job.result)
        facts = result["documents"][0]["facts"]
        facts.update(
            category="Flugreisen",
            origin="FRA",
            destination="FRA",
            overnight_count=4,
            room_count=1,
            items=[],
            breakfast_total=None,
        )
        result["documents"][0]["items_reconciled"] = False
        facts.pop("flight_route", None)
        job.result = result
        doc = session.get(Document, doc_id)
        doc.pages = [{"page": 1, "text": "FRA-CAN-MEL-CAN-FRA(Q/Q/A/A舱)"}]
    result = client.get(f"/summary-jobs/{first['id']}/result").json()
    facts = result["documents"][0]["facts"]
    assert facts["flight_route"] == "FRA → CAN → MEL → CAN → FRA"
    assert facts["overnight_count"] is None and facts["room_count"] is None
    assert result["expenses"][0]["description"] == facts["flight_route"]
    assert facts["total"] == "712.60"
    # Presentation repair does not rewrite saved extraction or user decisions.
    with factory() as session:
        assert (
            session.get(SummaryJob, first["id"]).result["documents"][0]["facts"]["overnight_count"]
            == 4
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
    assert job["started_at"] is None
    assert client.post(f"/trips/{tid}/summaries").json()["id"] == job["id"]
    assert client.get(f"/summary-jobs/{job['id']}/result").status_code == 409
    settings = Settings(_env_file=None)
    claim = claim_job(factory, settings)
    assert claim_job(factory, settings) is None
    process_job(factory, settings, *claim, extractor=FakeExtractor())
    completed = client.get(f"/summary-jobs/{job['id']}").json()
    assert completed["started_at"].endswith("Z")
    assert completed["created_at"] <= completed["started_at"] <= completed["finished_at"]
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
        started = session.get(SummaryJob, first[0]).started_at
        session.get(SummaryJob, first[0]).lease_until = now() - timedelta(seconds=1)
    second = claim_job(factory, settings)
    assert first[0] == second[0] and first[1] != second[1]
    with factory() as session:
        assert session.get(SummaryJob, first[0]).started_at == started
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
    assert len(report["totals"]["by_category"]) == 10


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


def test_rejected_upload_identifies_file_and_does_not_block_other_documents(api):
    client, _, store = api
    tid = trip(client)
    assert upload(client, tid).status_code == 201
    with pymupdf.open() as pdf:
        pdf.new_page()
        scanned = pdf.tobytes()
    rejected = client.post(
        f"/trips/{tid}/documents",
        files={"file": ("scan.pdf", scanned, "application/pdf")},
    )
    assert rejected.status_code == 422
    assert rejected.json()["detail"] == {
        "filename": "scan.pdf",
        "message": "Page 1 has no extractable text",
    }
    assert upload(client, tid, "hotel_invoice_zh.pdf").status_code == 201
    documents = client.get(f"/trips/{tid}/documents").json()
    assert {d["filename"] for d in documents} == {"hotel_invoice.pdf", "hotel_invoice_zh.pdf"}
    assert len(store.objects) == 2


def test_delete_document_removes_file_marks_report_stale_and_allows_reupload(api):
    client, factory, store = api
    tid = trip(client)
    document = upload(client, tid).json()
    job = client.post(f"/trips/{tid}/summaries").json()
    settings = Settings(_env_file=None)
    process_job(factory, settings, *claim_job(factory, settings), extractor=FakeExtractor())
    url = f"/documents/{document['id']}"
    assert client.delete(url).status_code == 204
    assert not store.objects
    assert client.get(f"/trips/{tid}/documents").json() == []
    assert client.get(url + "/download").status_code == 404
    assert client.get(f"/summary-jobs/{job['id']}/result").json()["is_stale"] is True
    assert client.delete(url).status_code == 404
    assert upload(client, tid).status_code == 201


def test_delete_document_does_not_break_active_job(api):
    client, factory, store = api
    tid = trip(client)
    document = upload(client, tid).json()
    client.post(f"/trips/{tid}/summaries")
    url = f"/documents/{document['id']}"
    assert client.delete(url).status_code == 409
    assert len(store.objects) == 1
    settings = Settings(_env_file=None)
    claim_job(factory, settings)
    assert client.delete(url).status_code == 409
    assert client.get(url + "/download").status_code == 200


def test_failed_storage_deletion_keeps_document_available(api, monkeypatch):
    from tera.storage import StorageError

    client, _, store = api
    tid = trip(client)
    document = upload(client, tid).json()

    def unavailable(key):
        raise StorageError("unavailable")

    monkeypatch.setattr(store, "delete", unavailable)
    url = f"/documents/{document['id']}"
    assert client.delete(url).status_code == 503
    assert len(client.get(f"/trips/{tid}/documents").json()) == 1
    assert client.get(url + "/download").status_code == 200


def test_document_progress_has_fixed_total_despite_extra_processing_steps(api, monkeypatch):
    from tera import worker

    client, factory, _ = api
    tid = trip(client)
    upload(client, tid)
    upload(client, tid, "hotel_invoice_zh.pdf")
    job = client.post(f"/trips/{tid}/summaries").json()
    observed = []
    original_update = worker.update_job
    original_process = worker.process_document

    def capture(*args, **values):
        original_update(*args, **values)
        if "completed_documents" in values:
            current = client.get(f"/summary-jobs/{job['id']}").json()
            observed.append((current["completed_documents"], len(current["document_ids"])))

    def extra_steps(document, chunks, extractor, settings, progress, job_id=None):
        progress(added=3)
        progress(completed=3)
        return original_process(document, chunks, extractor, settings, progress, job_id)

    monkeypatch.setattr(worker, "update_job", capture)
    monkeypatch.setattr(worker, "process_document", extra_steps)
    settings = Settings(_env_file=None)
    process_job(factory, settings, *claim_job(factory, settings), extractor=FakeExtractor())
    assert observed == [(1, 2), (2, 2)]


def test_worker_refreshes_legacy_pdf_layout(api):
    from tera.models import Document

    client, factory, store = api
    tid = trip(client)
    doc_id = upload(client, tid).json()["id"]
    with factory.begin() as session:
        session.get(Document, doc_id).pages = [{"page": 1, "text": "legacy extraction"}]
    job = client.post(f"/trips/{tid}/summaries").json()
    settings = Settings(_env_file=None)

    class LayoutExtractor(FakeExtractor):
        def extract(self, document_id, pages):
            assert "legacy extraction" not in pages[0]["text"]
            assert pages[0]["blocks"]
            return super().extract(document_id, pages)

    process_job(
        factory, settings, *claim_job(factory, settings), extractor=LayoutExtractor(), store=store
    )
    result = client.get(f"/summary-jobs/{job['id']}/result").json()
    assert result["status"] == "completed"


def test_inline_pdf_preview_keeps_auth_and_original_bytes(api):
    client, _, _ = api
    tid = trip(client)
    document_id = upload(client, tid).json()["id"]
    preview = client.get(f"/documents/{document_id}/download?inline=true")
    assert preview.status_code == 200
    assert preview.content == (DATA / "hotel_invoice.pdf").read_bytes()
    assert preview.headers["content-type"] == "application/pdf"
    assert preview.headers["content-disposition"].startswith("inline;")
    assert preview.headers["cache-control"] == "private, no-store"
    assert (
        client.get(f"/documents/{document_id}/download")
        .headers["content-disposition"]
        .startswith("attachment;")
    )
    assert (
        client.get(
            f"/documents/{document_id}/download?inline=true", headers={"Authorization": ""}
        ).status_code
        == 401
    )


def test_relationship_resolution_updates_totals_persists_and_can_be_undone(api):
    client, factory, _ = api
    tid = trip(client)
    ids = [
        upload(client, tid, name).json()["id"]
        for name in ("hotel_invoice.pdf", "hotel_invoice_zh.pdf")
    ]
    job_id = client.post(f"/trips/{tid}/summaries").json()["id"]
    settings = Settings(_env_file=None)
    process_job(factory, settings, *claim_job(factory, settings), extractor=FakeExtractor())
    url = f"/summary-jobs/{job_id}/relationships"
    response = client.put(
        url, json={"document_ids": ids, "resolution": "same_expense", "primary_document_id": ids[0]}
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert len(result["expenses"]) == 2  # Accommodation and breakfast, once each.
    assert Decimal(result["totals"]["by_currency"][0]["confirmed"]) == Decimal("712.60")
    secondary = next(d for d in result["documents"] if d["document_id"] == ids[1])
    assert secondary["duplicate_of"] == ids[0] and secondary["status"] == "supporting"
    persisted = client.get(f"/summary-jobs/{job_id}/result").json()
    assert all(
        d["relationship_history"][-1]["resolution"] == "same_expense"
        for d in persisted["documents"]
    )
    separate = client.put(url, json={"document_ids": ids, "resolution": "separate"}).json()
    assert len(separate["expenses"]) == 4
    assert Decimal(separate["totals"]["by_currency"][0]["confirmed"]) == Decimal("1425.20")
    assert not separate["warnings"]
    reset = client.put(url, json={"document_ids": ids, "resolution": "pending"}).json()
    assert reset["coverage"]["needs_review"] == 2
    assert Decimal(reset["totals"]["by_currency"][0]["confirmed"]) == 0
    assert all(len(d["relationship_history"]) == 3 for d in reset["documents"])
    assert (
        client.put(
            url, json={"document_ids": [ids[0], ids[0]], "resolution": "separate"}
        ).status_code
        == 422
    )
    assert (
        client.put(url, json={"document_ids": ids, "resolution": "same_expense"}).status_code == 422
    )
    another_trip = trip(client)
    other = upload(client, another_trip).json()["id"]
    assert (
        client.put(
            url, json={"document_ids": [ids[0], other], "resolution": "separate"}
        ).status_code
        == 422
    )
