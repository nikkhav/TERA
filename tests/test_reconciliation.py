from decimal import Decimal
from types import SimpleNamespace

import pytest

from tera.chunking import chunk_pages, prompt_budget
from tera.config import Settings
from tera.llm import NonRetryableExtractionError
from tera.processing import correction_feedback, process_document
from tera.prompts import build_prompt
from tera.reconciliation import reconcile
from tera.reporting import make_report, merge_fragments
from tera.schemas import ReceiptFacts


def hotel(**changes):
    data = {
        "merchant": "Hotel",
        "invoice_number": "INV-1",
        "invoice_date": "2026-09-14",
        "category": "Hotel",
        "currency": "EUR",
        "total": "712.60",
        "net_total": "662",
        "tax_total": "50.60",
        "breakfast_net": "60",
        "breakfast_tax": "11.40",
        "evidence": [{"field": "total", "page": 2, "quote": "Total 712.60"}],
        "items": [
            {
                "description": "Übernachtung",
                "category": "Hotel",
                "net": "560",
                "tax": "39.20",
                "evidence": [{"field": "net", "page": 1, "quote": "Room 560"}],
            },
            {
                "description": "Frühstück",
                "category": "Verpflegung",
                "net": "60",
                "tax": "11.40",
                "is_breakfast": True,
                "evidence": [{"field": "net", "page": 1, "quote": "Breakfast 60"}],
            },
            {
                "description": "Beherbergungssteuer",
                "category": "Hotel",
                "net": "42",
                "tax": "0",
                "evidence": [{"field": "net", "page": 2, "quote": "City tax 42"}],
            },
        ],
    }
    data.update(changes)
    return ReceiptFacts(**data)


def doc():
    return SimpleNamespace(id="receipt", filename="receipt.pdf", sha256="hash", page_count=2)


def test_two_tax_rates_and_exempt_city_tax_reconcile():
    facts, issues, derived, valid = reconcile(hotel())
    assert valid and not issues
    assert facts.breakfast_total == Decimal("71.40")
    assert [i.gross for i in facts.items] == [Decimal("599.20"), Decimal("71.40"), Decimal(42)]
    assert set(derived) == {"items.0.gross", "items.1.gross", "items.2.gross", "breakfast_total"}
    report = make_report([merge_fragments(doc(), [hotel()], [], [])], "test", "test")
    totals = {r["category"]: r["confirmed"] for r in report["totals"]["by_category"]}
    assert totals == {
        "Hotel": "641.20",
        "Verpflegung": "71.40",
        "Flugreisen": "0",
        "Sonstige Ausgaben": "0",
    }
    assert report["accommodation"][0]["without_breakfast"] == "641.20"
    assert report["schema_version"] == 2


@pytest.mark.parametrize(
    "change,code",
    [
        ({"total": "670.60"}, "line_sum_mismatch"),
        ({"total": "673.40"}, "invoice_tax_mismatch"),
        ({"breakfast_total": "60"}, "breakfast_mismatch"),
        ({"net_total": "660", "tax_total": "52.60"}, "line_component_mismatch"),
        ({"items": []}, "missing_items"),
    ],
)
def test_known_model_errors_require_review(change, code):
    _, issues, _, valid = reconcile(hotel(**change))
    assert not valid and code in {i.code for i in issues}
    record = merge_fragments(doc(), [hotel(**change)], [], [])
    report = make_report([record], "test", "test")
    assert report["totals"]["by_currency"][0]["confirmed"] == "0"


def test_missing_tax_never_turns_net_into_gross():
    facts = hotel()
    facts.items[0].tax = None
    result, issues, _, valid = reconcile(facts)
    assert not valid and result.items[0].gross is None
    assert "missing_line_gross" in {i.code for i in issues}


@pytest.mark.parametrize(
    "total,items",
    [
        ("90", [{"gross": "100"}, {"gross": "-10"}]),
        ("-120", [{"net": "-100", "tax": "-20"}]),
        ("2220", [{"gross": "2040"}, {"gross": "180"}]),
        ("1000", [{"gross": "1000"}]),
    ],
)
def test_discounts_refunds_and_different_currencies(total, items):
    facts = ReceiptFacts(
        merchant="上海晨星酒店",
        invoice_date="2026-09-14",
        category="Sonstige Ausgaben",
        currency="CNY",
        total=total,
        items=[dict(description="Ausgabe", category="Sonstige Ausgaben", **i) for i in items],
    )
    result, issues, _, valid = reconcile(facts)
    assert valid and not issues
    assert sum(i.gross for i in result.items) == Decimal(total)


def test_included_unpriced_breakfast_stays_unknown():
    facts = hotel(
        total="200",
        net_total=None,
        tax_total=None,
        breakfast_net=None,
        breakfast_tax=None,
        items=[
            {"description": "Unterkunft inklusive Frühstück", "category": "Hotel", "gross": "200"}
        ],
    )
    result, issues, _, valid = reconcile(facts)
    assert valid and not issues and result.breakfast_total is None


def test_double_counted_breakfast_is_caught():
    facts = hotel(
        total="2220",
        net_total=None,
        tax_total=None,
        breakfast_net=None,
        breakfast_tax=None,
        items=[
            {"description": "Hotel", "category": "Hotel", "gross": "2220"},
            {
                "description": "Frühstück",
                "category": "Verpflegung",
                "gross": "180",
                "is_breakfast": True,
            },
        ],
    )
    assert "line_sum_mismatch" in {i.code for i in reconcile(facts)[1]}


def test_merge_pages_before_reconciling():
    full = hotel()
    first = ReceiptFacts(items=full.items[:2])
    second = full.model_copy(update={"items": full.items[2:]})
    result = merge_fragments(doc(), [first, second], [], [])
    assert not result["warnings"] and result["items_reconciled"]
    assert len(result["facts"]["items"]) == 3


def test_targeted_correction_preserves_other_pages_and_tracks_progress():
    full = hotel()
    incorrect = full.model_copy(deep=True)
    incorrect.items[0].gross = Decimal(560)
    chunks = [
        [{"page": 1, "part": 1, "text": "Room and breakfast"}],
        [{"page": 2, "part": 1, "text": "City tax and total"}],
    ]
    calls, progress = [], []

    class Extractor:
        def extract(self, document_id, pages, feedback=None):
            page = pages[0]["page"]
            calls.append((page, feedback))
            if page == 1:
                return ReceiptFacts(items=(full if feedback else incorrect).items[:2])
            return full.model_copy(update={"items": full.items[2:]})

    result = process_document(
        doc(), chunks, Extractor(), Settings(_env_file=None), lambda **v: progress.append(v)
    )
    assert result["recheck_attempted"] and not result["warnings"]
    assert result["initial_issues"]
    assert len(calls) == 4  # The cross-page sum requires both source pages.
    assert all("line_" in feedback for _, feedback in calls[2:])
    assert sum(v.get("completed", 0) for v in progress) == 4
    assert sum(v.get("added", 0) for v in progress) == 2


def test_category_correction_only_rereads_affected_page():
    full = hotel()
    chunks = [[{"page": n, "part": 1, "text": "Text"}] for n in (1, 2)]
    calls = []

    class Extractor:
        def extract(self, document_id, pages, feedback=None):
            page = pages[0]["page"]
            calls.append(page)
            if page == 2:
                return full.model_copy(update={"items": full.items[2:]})
            first = ReceiptFacts(items=full.items[:2]).model_copy(deep=True)
            if feedback is None:
                first.items[0].category = None
            return first

    result = process_document(
        doc(), chunks, Extractor(), Settings(_env_file=None), lambda **_: None
    )
    assert calls == [1, 2, 1]
    assert not result["warnings"]


@pytest.mark.parametrize("fails", [False, True])
def test_unresolved_correction_is_bounded_and_keeps_review(fails):
    calls = []

    class Extractor:
        def extract(self, document_id, pages, feedback=None):
            calls.append(feedback)
            if feedback and fails:
                raise TimeoutError("offline")
            return hotel(total="670.60")

    result = process_document(
        doc(),
        [[{"page": 1, "part": 1, "text": "Text"}]],
        Extractor(),
        Settings(_env_file=None),
        lambda **_: None,
    )
    assert len(calls) == 2 and result["warnings"]
    assert not result["extraction_failed"]
    assert make_report([result], "test", "test")["totals"]["by_currency"][0]["confirmed"] == "0"


def test_retry_can_be_disabled():
    class Extractor:
        def extract(self, *_):
            return hotel(total="670.60")

    result = process_document(
        doc(),
        [[{"page": 1, "part": 1, "text": "Text"}]],
        Extractor(),
        Settings(_env_file=None, receipt_recheck_enabled=False),
        lambda **_: None,
    )
    assert not result["recheck_attempted"] and result["warnings"]


def test_truncated_response_is_not_sent_again_unchanged():
    calls = []

    class Extractor:
        def extract(self, *_, **kwargs):
            calls.append(kwargs.get("feedback"))
            raise NonRetryableExtractionError("Model response was truncated")

    result = process_document(
        doc(),
        [[{"page": 1, "part": 1, "text": "Text"}]],
        Extractor(),
        Settings(_env_file=None),
        lambda **_: None,
    )
    assert calls == [None]
    assert result["extraction_failed"]
    assert not result["recheck_attempted"]


def test_correction_prompt_always_fits_for_long_multilingual_pages():
    settings = Settings(_env_file=None)
    chunks = chunk_pages("receipt", [{"page": 1, "text": "早餐 123.40\n" * 2000}], settings)
    feedback = correction_feedback([i.model_dump() for i in reconcile(hotel(total="670.60"))[1]])
    assert feedback
    for chunk in chunks:
        assert len(build_prompt("receipt", chunk, feedback).encode()) <= prompt_budget(settings)


def test_document_notices_do_not_trigger_correction_or_block_totals():
    calls = []
    notice = "Dieser Beleg ist ausdrücklich als fiktive Testrechnung gekennzeichnet."

    class Extractor:
        def extract(self, *args, **kwargs):
            calls.append(kwargs)
            return hotel(notices=[notice, notice])

    record = process_document(
        doc(),
        [[{"page": 1, "text": "Text"}]],
        Extractor(),
        Settings(_env_file=None),
        lambda **_: None,
    )
    assert len(calls) == 1 and not record["recheck_attempted"]
    report = make_report([record], "test", "test")
    assert report["coverage"]["needs_review"] == 0
    assert report["totals"]["by_currency"][0]["confirmed"] == "712.60"
    assert not report["warnings"]
    assert report["notices"] == [
        {"document_id": "receipt", "filename": "receipt.pdf", "message": notice}
    ]
    record["review_history"] = [
        {"decision": "approved", "user_name": "Test", "reviewed_at": "2026-09-29", "comment": ""}
    ]
    assert make_report([record], "test", "test")["notices"] == report["notices"]
    record["warnings"] = ["Gesamtbetrag nicht eindeutig im Beleg nachgewiesen."]
    record["review_history"] = []
    assert make_report([record], "test", "test")["coverage"]["needs_review"] == 1
