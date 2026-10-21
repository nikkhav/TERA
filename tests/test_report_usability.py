"""User-facing regressions for multi-document travel reports."""

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from tera.chunking import chunk_pages
from tera.config import Settings
from tera.llm import verify_facts
from tera.pdf import extract_pages
from tera.reporting import make_report, merge_fragments
from tera.schemas import ReceiptFacts


def record(identifier="a", **changes):
    values = {
        "document_kind": "invoice",
        "merchant": "Uber",
        "invoice_date": "2026-05-04",
        "category": "Sonstige Ausgaben",
        "currency": "AUD",
        "total": "53.69",
        "items": [
            {"description": "Fahrt", "gross": "40.33"},
            {"description": "Gebühren", "gross": "13.36"},
        ],
    }
    values.update(changes)
    facts = ReceiptFacts(**values)
    return merge_fragments(
        SimpleNamespace(
            id=identifier, filename=f"{identifier}.pdf", sha256=identifier, page_count=1
        ),
        [facts],
        [],
        [],
    )


def test_taxi_components_form_one_expense_without_losing_details():
    result = make_report([record()], "test", "test")
    assert len(result["expenses"]) == 1
    assert Decimal(result["expenses"][0]["amount"]) == Decimal("53.69")
    assert len(result["documents"][0]["facts"]["items"]) == 2
    assert result["expenses"][0]["description"] == "Taxifahrt einschließlich Gebühren"


def test_total_only_receipt_does_not_require_nonexistent_line_items():
    result = make_report([record(items=[])], "test", "test")
    assert not result["warnings"]
    assert result["totals"]["by_currency"][0]["confirmed"] == "53.69"


def test_bank_debit_and_explanation_are_not_additional_expenses():
    result = make_report(
        [
            record(),
            record("bank", document_kind="payment", total="-53.69", items=[]),
            record(
                "note",
                document_kind="supporting",
                total=None,
                items=[],
                currency=None,
                merchant=None,
            ),
        ],
        "test",
        "test",
    )
    assert len(result["documents"]) == 3
    assert len(result["expenses"]) == 1
    assert result["totals"]["by_currency"][0]["confirmed"] == "53.69"
    assert not result["warnings"]


def linked_pair(**second_changes):
    first = record(service_reference="trip-123456")
    second = record(
        "b",
        document_kind="receipt",
        merchant="Rasier Pacific Pty Ltd",
        service_reference="trip-123456",
        **second_changes,
    )
    for value in (first, second):
        value["sources"].append(
            {
                "document_id": value["document_id"],
                "page": 1,
                "field": "service_reference",
                "quote": "Ride trip-123456",
            }
        )
    return first, second


def test_invoice_and_receipt_with_verified_reference_count_once():
    first, second = linked_pair()
    result = make_report([first, second], "test", "test")
    assert len(result["expenses"]) == 1
    assert result["totals"]["by_currency"][0]["confirmed"] == "53.69"
    assert result["documents"][1]["duplicate_of"] == "a"
    assert result["documents"][0]["related_document_ids"] == ["b"]


def test_conflicting_related_amounts_are_not_silently_merged():
    result = make_report(list(linked_pair(total="60", items=[])), "test", "test")
    assert len(result["expenses"]) == 2
    assert not any(d["duplicate_of"] for d in result["documents"])
    assert result["totals"]["by_currency"][0]["confirmed"] == "0"
    assert all(d["warnings"] for d in result["documents"])


def test_unevidenced_shared_reference_is_only_a_candidate():
    first, second = linked_pair()
    first["sources"] = second["sources"] = []
    result = make_report([first, second], "test", "test")
    assert len(result["expenses"]) == 2
    assert not any(d["duplicate_of"] for d in result["documents"])
    assert result["totals"]["by_currency"][0]["confirmed"] == "0"


def test_same_day_taxis_with_distinct_references_are_not_merged():
    first, second = linked_pair()
    second["facts"]["service_reference"] = "different-654321"
    second["sources"][0]["quote"] = "Ride different-654321"
    result = make_report([first, second], "test", "test")
    assert len(result["expenses"]) == 2
    assert not any(d["duplicate_of"] for d in result["documents"])


def test_validation_uses_headers_from_the_whole_document():
    pages = [
        {"page": 1, "text": "Invoice 2026-05-04 AUD\n", "blocks": []},
        {"page": 2, "text": "Total 53.69\n", "blocks": []},
    ]
    first = verify_facts(
        ReceiptFacts(
            currency="AUD",
            invoice_date="2026-05-04",
            evidence=[
                {"page": 1, "field": "invoice_date", "quote": "Invoice 2026-05-04"},
                {"page": 1, "field": "currency", "quote": "AUD"},
            ],
        ),
        pages[:1],
        validate_values=False,
    )
    second = verify_facts(
        ReceiptFacts(
            category="Sonstige Ausgaben",
            total="53.69",
            evidence=[
                {"page": 2, "field": "total", "quote": "Total 53.69"},
            ],
        ),
        pages[1:],
        validate_values=False,
    )
    merged = merge_fragments(
        SimpleNamespace(id="a", filename="a.pdf", sha256="a", page_count=2, pages=pages),
        [first, second],
        [],
        [[pages[0]], [pages[1]]],
    )
    assert not merged["warnings"]


def test_short_digital_invoice_stays_in_one_request():
    settings = Settings(_env_file=None)
    pages = extract_pages(
        (Path(__file__).parents[1] / "research/data/hotel_invoice.pdf").read_bytes(), settings
    )
    assert len(chunk_pages("receipt", pages, settings)) == 1


def test_two_invoices_or_different_services_are_not_automatically_combined():
    for changes in (
        {"document_kind": "invoice"},
        {"service_start": "2026-05-05"},
        {"origin": "Other", "destination": "City"},
    ):
        first, second = linked_pair()
        first["facts"].update(service_start="2026-05-04", origin="Airport", destination="Hotel")
        second["facts"].update(changes)
        report = make_report([first, second], "test", "test")
        assert len(report["expenses"]) == 2
        assert not any(d["duplicate_of"] for d in report["documents"])
        assert report["totals"]["by_currency"][0]["confirmed"] == "0"


def test_recheck_does_not_keep_resolved_machine_evidence_messages():
    pages = [{"page": 1, "text": "Net 10.00 Tax 1.00 Total 11.00 EUR", "blocks": []}]
    facts = verify_facts(
        ReceiptFacts(
            category="Sonstige Ausgaben",
            currency="EUR",
            total="11",
            net_total="10",
            tax_total="1",
            evidence=[
                {"page": 1, "field": field, "quote": quote}
                for field, quote in (
                    ("total", "Total 11.00 EUR"),
                    ("net_total", "Net 10.00"),
                    ("tax_total", "Tax 1.00"),
                )
            ],
            notes=["Nettosumme nicht eindeutig im Beleg nachgewiesen.", "missing_field: merchant"],
        ),
        pages,
        validate_values=False,
    )
    result = merge_fragments(
        SimpleNamespace(id="a", filename="a.pdf", sha256="a", page_count=1, pages=pages),
        [facts],
        [],
        [pages],
    )
    assert not result["warnings"]


def test_aud_context_rule_requires_domestic_tax_identifiers():
    base = "Australia ABN 123 GST Total $53.69"
    for text, expected in ((base, False), (base.replace("ABN", ""), True), (base + " USD", True)):
        facts = ReceiptFacts(
            currency="AUD", evidence=[{"page": 1, "field": "description", "quote": text}]
        )
        checked = verify_facts(facts, [{"page": 1, "text": text, "blocks": []}])
        assert any("Währung" in note for note in checked.notes) is expected
        if not expected:
            assert any("AUD" in note for note in checked.notices)


def test_resolving_a_possible_duplicate_removes_derived_warning():
    first = record()
    second = record("b", document_kind="receipt", merchant="Rasier Pacific Pty Ltd")
    initial = make_report([first, second], "test", "test")
    assert initial["warnings"]
    initial["documents"][1]["facts"]["document_kind"] = "supporting"
    updated = make_report(initial["documents"], "test", "test")
    assert not updated["warnings"]
    assert updated["totals"]["by_currency"][0]["confirmed"] == "53.69"


def test_supporting_document_notes_do_not_require_expense_confirmation():
    bank = record("bank", document_kind="payment", total="-53.69", items=[])
    bank["warnings"] = ["Druckansicht ist nicht rechtsverbindlich."]
    report = make_report([bank], "test", "test")
    assert report["documents"][0]["warnings"]
    assert report["documents"][0]["status"] == "supporting"
    assert not report["warnings"]
    assert not report["expenses"]


def test_plain_validity_date_is_a_notice_but_conflict_is_still_a_warning():
    note = "Gültigkeitszeitraum endet am 17.05.2026 um 10:00 Uhr."
    plain = record(notes=[note])
    assert note in plain["notices"]
    assert note not in plain["warnings"]
    conflict = note + " Das widerspricht dem Reisedatum."
    uncertain = record(notes=[conflict])
    assert conflict in uncertain["warnings"]


def test_manual_separate_overrides_verified_reference_link_and_preserves_findings():
    records = linked_pair()
    assert len(make_report(records, "test", "test")["expenses"]) == 1
    event = {
        "id": "review-1",
        "document_ids": [r["document_id"] for r in records],
        "resolution": "separate",
        "primary_document_id": None,
    }
    for r in records:
        r["relationship_history"] = [event]
    records[0]["warnings"].append("Steuerbetrag bitte prüfen.")
    report = make_report(records, "test", "test")
    assert len(report["expenses"]) == 2
    assert report["documents"][0]["warnings"] == ["Steuerbetrag bitte prüfen."]
    assert not report["documents"][1]["duplicate_of"]


def test_manual_same_expense_uses_chosen_primary_and_keeps_other_warnings():
    left, right = record(), record("b", document_kind="receipt", total="54.69")
    left["warnings"].append("Gesamtbetrag bitte prüfen.")
    event = {
        "id": "review-1",
        "document_ids": ["a", "b"],
        "resolution": "same_expense",
        "primary_document_id": "a",
    }
    for r in [left, right]:
        r["relationship_history"] = [event]
    report = make_report([left, right], "test", "test")
    assert len(report["expenses"]) == 1
    assert report["expenses"][0]["amount"] == "53.69"
    assert report["documents"][0]["warnings"] == ["Gesamtbetrag bitte prüfen."]
    assert report["documents"][1]["status"] == "supporting"
