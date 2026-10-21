"""Regression cases for repeated amounts, layout and source occurrences."""

from types import SimpleNamespace

import pymupdf

from tera.chunking import chunk_pages, prompt_budget
from tera.config import Settings
from tera.llm import verify_facts
from tera.pdf import extract_pages
from tera.prompts import build_prompt
from tera.reporting import merge_fragments
from tera.schemas import ReceiptFacts


def document():
    return SimpleNamespace(id="receipt", filename="test.pdf", sha256="test", page_count=1)


def test_layout_keeps_table_columns_on_the_same_row():
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((50, 70), "Room")
        page.insert_text((250, 70), "20.00")
        page.insert_text((50, 90), "Meal")
        page.insert_text((250, 90), "20.00")
        pages = extract_pages(pdf.tobytes(), Settings(_env_file=None))
    page = pages[0]
    assert page["text"].splitlines() == ["Room  20.00", "Meal  20.00"]
    assert len(page["blocks"]) == 2
    assert page["blocks"][0]["bbox"][0] == 50
    for block in page["blocks"]:
        assert page["text"][block["start"] : block["end"]].endswith("20.00\n")


def source_page():
    return {
        "page": 1,
        "text": "Room 20.00\nMeal 20.00\n",
        "blocks": [
            {"id": "p1-r1", "start": 0, "end": 11},
            {"id": "p1-r2", "start": 11, "end": 22},
        ],
    }


def item_facts(block_id=None):
    return ReceiptFacts(
        items=[
            {
                "description": "Ausgabe",
                "gross": "20",
                "evidence": [{"page": 1, "field": "gross", "quote": "20.00", "block_id": block_id}],
            }
        ]
    )


def test_identical_amounts_resolve_to_distinct_source_occurrences():
    page = source_page()
    first = verify_facts(item_facts("p1-r1"), [page])
    second = verify_facts(item_facts("p1-r2"), [page])
    assert first.items[0].evidence[0].start == 5
    assert second.items[0].evidence[0].start == 16
    record = merge_fragments(document(), [first, second], [], [[page]])
    assert len(record["facts"]["items"]) == 2
    repeated = merge_fragments(document(), [first, first.model_copy(deep=True)], [], [[page]])
    assert len(repeated["facts"]["items"]) == 1


def test_unanchored_repeated_quotes_never_remove_an_item():
    page = source_page()
    facts = verify_facts(item_facts(), [page])
    assert facts.items[0].evidence[0].start is None
    assert not facts.notes
    record = merge_fragments(document(), [facts, facts.model_copy(deep=True)], [], [[page]])
    assert len(record["facts"]["items"]) == 2


def test_wrong_block_and_forged_offsets_do_not_verify():
    page = source_page()
    for evidence in (
        {"page": 1, "field": "gross", "quote": "Meal 20.00", "block_id": "p1-r1"},
        {"page": 1, "field": "gross", "quote": "20.00", "start": 999, "end": 1004},
    ):
        facts = ReceiptFacts(items=[{"description": "Meal", "gross": "20", "evidence": [evidence]}])
        checked = verify_facts(facts, [page])
        assert checked.notes
        assert not checked.items[0].evidence


def test_payment_is_not_invoice_total_evidence():
    facts = ReceiptFacts(
        total="100",
        evidence=[
            {
                "page": 1,
                "field": "total",
                "quote": "Prepayment: 100 EUR",
            }
        ],
    )
    checked = verify_facts(facts, [{"page": 1, "text": "Prepayment: 100 EUR\nTotal: 200 EUR"}])
    assert checked.total == 100
    assert any("Gesamtbetrag" in note for note in checked.notes)


def test_chunking_retains_layout_offsets_and_rows_within_budget():
    text = "Hotel EUR\n" + "Room  20.00\n" * 300
    blocks, offset = [], 0
    for index, line in enumerate(text.splitlines(keepends=True)):
        blocks.append({"id": f"p1-r{index}", "start": offset, "end": offset + len(line)})
        offset += len(line)
    settings = Settings(_env_file=None, model_context_tokens=8192, model_output_tokens=2048)
    chunks = chunk_pages("receipt", [{"page": 1, "text": text, "blocks": blocks}], settings)
    assert len(chunks) > 1
    assert "".join(p["text"] for c in chunks for p in c) == text
    for chunk in chunks:
        assert len(build_prompt("receipt", chunk, "Recheck.").encode()) <= prompt_budget(settings)
        for part in chunk:
            assert part["text"].endswith("\n")
            assert part["blocks"][0]["start"] == part["text_start"]


def test_date_and_currency_quotes_must_contain_the_claimed_values():
    page = {"page": 1, "text": "Date 2026-10-20 Currency EUR", "blocks": []}
    for day, currency, expected_warning in (
        ("2026-10-20", "EUR", False),
        ("2026-10-21", "EUR", True),
        ("2026-10-20", "USD", True),
    ):
        facts = ReceiptFacts(
            invoice_date=day,
            currency=currency,
            evidence=[
                {"page": 1, "field": "invoice_date", "quote": "Date 2026-10-20"},
                {"page": 1, "field": "currency", "quote": "Currency EUR"},
            ],
        )
        assert bool(verify_facts(facts, [page]).notes) is expected_warning


def test_row_reference_supplies_original_quote_without_model_transcription():
    facts = ReceiptFacts(
        items=[
            {
                "description": "Ausgabe",
                "gross": "20",
                "evidence": [{"page": 1, "field": "gross", "quote": "", "block_id": "p1-r2"}],
            }
        ]
    )
    checked = verify_facts(facts, [source_page()])
    evidence = checked.items[0].evidence[0]
    assert evidence.quote == "Meal 20.00"
    assert evidence.start == 11
    assert not checked.notes


def test_layout_joins_different_font_sizes_without_merging_next_line():
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((50, 70), "Total", fontsize=9)
        page.insert_text((250, 70), "11600.00", fontsize=12)
        page.insert_text((50, 88), "Tax", fontsize=9)
        page.insert_text((250, 88), "0.00", fontsize=12)
        pages = extract_pages(pdf.tobytes(), Settings(_env_file=None))
    assert pages[0]["text"].splitlines() == ["Total  11600.00", "Tax  0.00"]
    assert pages[0]["layout_version"] == 2


def test_chinese_invoice_context_supports_cny_but_not_yen_alone():
    for text, supported in [
        ("电子发票（普通发票）\n价税合计 ¥11600.00\n", True),
        ("Total ¥11600.00\n", False),
        ("电子发票 JPY\n价税合计 ¥11600.00\n", False),
    ]:
        page = {"page": 1, "text": text, "blocks": []}
        facts = verify_facts(ReceiptFacts(currency="CNY"), [page])
        assert ("Währung nicht eindeutig im Beleg nachgewiesen." not in facts.notes) == supported
        if supported:
            assert any("abgeleitet" in notice for notice in facts.notices)


def test_gross_receipt_drops_invented_net_and_government_levy_as_vat():
    page = {"page": 1, "text": "Total 53.46\n政府税 1.32\n2026 年 5 月 12 日\n", "blocks": []}
    facts = verify_facts(
        ReceiptFacts(
            total="53.46",
            net_total="52.14",
            tax_total="1.32",
            invoice_date="2026-05-12",
            evidence=[
                {"page": 1, "quote": "Total 53.46", "field": "total"},
                {"page": 1, "quote": "政府税 1.32", "field": "tax_total"},
                {"page": 1, "quote": "2026 年 5 月 12 日", "field": "invoice_date"},
            ],
        ),
        [page],
    )
    assert facts.net_total is None and facts.tax_total is None
    assert str(facts.total) == "53.46"
    assert not facts.notes
    assert facts.notices


def test_invoice_date_recovery_requires_an_explicit_issue_date_label():
    for label, supported in [
        ("开票日期：", True),
        ("Rechnungsdatum:", True),
        ("Reisedatum:", False),
    ]:
        text = f"{label} 2026年06月01日\n"
        page = {"page": 1, "text": text, "blocks": [{"id": "p1-r1", "start": 0, "end": len(text)}]}
        facts = verify_facts(ReceiptFacts(invoice_date="2026-06-01"), [page])
        assert bool(facts.evidence) == supported
        assert (
            "Rechnungsdatum nicht eindeutig im Beleg nachgewiesen." not in facts.notes
        ) == supported


def test_ticket_total_is_recovered_from_explicit_gesamtpreis_row():
    text = "Gesamtpreis 43,49 €. Gebucht am 17.03.2026 um 13:49 Uhr.\n"
    page = {"page": 1, "text": text, "blocks": [{"id": "p1-r1", "start": 0, "end": len(text)}]}
    facts = verify_facts(ReceiptFacts(total="43.49", currency="EUR"), [page])
    assert facts.evidence[0].block_id == "p1-r1"
    assert not facts.notes


def test_invoice_date_recovery_handles_spacing_and_named_months():
    text = "Invoice  date:  4  May  2026\n"
    page = {"page": 1, "text": text, "blocks": [{"id": "p1-r1", "start": 0, "end": len(text)}]}
    facts = verify_facts(ReceiptFacts(invoice_date="2026-05-04"), [page])
    assert len(facts.evidence) == 1
    assert not facts.notes


def ride_pages(other_date="2026/5/12"):
    text, blocks = "", []
    for index, line in enumerate(
        ["UberX", "2026 年 5 月 12 日", "Total AU$59.32", f"{other_date} 下午12:43"]
    ):
        quote = line + "\n"
        blocks.append({"id": f"p1-r{index + 1}", "start": len(text), "end": len(text) + len(quote)})
        text += quote
    return [{"page": 1, "text": text, "blocks": blocks}]


def test_ride_receipt_date_heading_supplies_missing_date_citation():
    facts = verify_facts(
        ReceiptFacts(
            document_kind="receipt",
            merchant="Uber",
            transport_mode="Taxi",
            total="59.32",
            currency="AUD",
            invoice_date="2026-05-12",
        ),
        ride_pages(),
    )
    date_source = next(e for e in facts.evidence if e.field == "invoice_date")
    assert date_source.quote == "2026 年 5 月 12 日"
    assert date_source.block_id == "p1-r2"
    assert "Rechnungsdatum nicht eindeutig im Beleg nachgewiesen." not in facts.notes
    assert any("Datumszeile" in notice for notice in facts.notices)


def test_unlabeled_date_fallback_does_not_resolve_conflicting_dates_or_invoice_dates():
    for kind, pages in [("invoice", ride_pages()), ("receipt", ride_pages("2026/5/13"))]:
        facts = verify_facts(
            ReceiptFacts(
                document_kind=kind,
                merchant="Uber",
                transport_mode="Taxi",
                invoice_date="2026-05-12",
            ),
            pages,
        )
        assert not facts.evidence
        assert "Rechnungsdatum nicht eindeutig im Beleg nachgewiesen." in facts.notes


def test_saved_date_repair_preserves_facts_other_issues_and_review_history():
    from copy import deepcopy

    from tera.llm import refresh_saved_date_source

    record = {
        "document_id": "ride",
        "facts": ReceiptFacts(
            document_kind="receipt",
            merchant="Uber",
            invoice_date="2026-05-12",
            total="59.32",
            currency="AUD",
        ).model_dump(mode="json"),
        "warnings": [
            "Rechnungsdatum nicht eindeutig im Beleg nachgewiesen.",
            "Gesamtbetrag bitte prüfen.",
        ],
        "validation_issues": [
            {"message": "Rechnungsdatum nicht eindeutig im Beleg nachgewiesen."},
            {"message": "Gesamtbetrag bitte prüfen."},
        ],
        "sources": [],
        "review_history": [{"decision": "pending"}],
    }
    before = deepcopy(record)
    assert refresh_saved_date_source(record, ride_pages())
    assert record["facts"] == before["facts"]
    assert record["review_history"] == before["review_history"]
    assert record["warnings"] == ["Gesamtbetrag bitte prüfen."]
    assert len(record["validation_issues"]) == 1
    assert record["sources"][0]["translation"] == "Belegdatum: 2026-05-12"
    assert not refresh_saved_date_source(record, ride_pages())
