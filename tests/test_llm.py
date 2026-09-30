import json

import pytest

from tera.config import Settings
from tera.llm import OllamaExtractor


def run_extractor(monkeypatch, result, think=None):
    from tera import llm

    class Client:
        def __init__(self, **_):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def post(self, url, json):
            assert url.endswith("/api/generate")
            assert json["format"]["title"] == "ReceiptFacts"
            assert json["options"]["num_predict"] > 0
            assert json["model"] == "test-model"
            if think is None:
                assert "think" not in json
            else:
                assert json["think"] is think
            self.payload = json
            return self

        def raise_for_status(self):
            pass

        def json(self):
            return result

    monkeypatch.setattr(llm.httpx, "Client", Client)
    return OllamaExtractor(
        Settings(_env_file=None, ollama_model="test-model", ollama_think=think)
    ).extract("receipt", [{"page": 2, "text": "Hotel\nTotal EUR 712.60", "part": 1}])


def test_valid_model_response(monkeypatch):
    facts = run_extractor(
        monkeypatch,
        {
            "done": True,
            "done_reason": "stop",
            "response": json.dumps(
                {
                    "total": "712.60",
                    "currency": "EUR",
                    "evidence": [{"page": 2, "quote": "Total EUR 712.60"}],
                }
            ),
        },
    )
    assert str(facts.total) == "712.60"


@pytest.mark.parametrize("page,quote", [(1, "Hotel"), (2, "invented")])
def test_model_cannot_cite_unseen_text(monkeypatch, page, quote):
    facts = run_extractor(
        monkeypatch,
        {"done": True, "response": json.dumps({"evidence": [{"page": page, "quote": quote}]})},
    )
    assert not facts.evidence
    assert any("Keine überprüfbaren Textbelege" in note for note in facts.notes)


def test_truncated_model_output_is_rejected(monkeypatch):
    with pytest.raises(ValueError, match="truncated"):
        run_extractor(monkeypatch, {"done": True, "done_reason": "length", "response": "{}"})


def test_missing_evidence_requires_review(monkeypatch):
    assert run_extractor(monkeypatch, {"done": True, "response": "{}"}).notes


@pytest.mark.parametrize("think", [True, False])
def test_thinking_is_configured_without_model_name_rules(monkeypatch, think):
    run_extractor(monkeypatch, {"done": True, "response": "{}"}, think=think)


def test_item_evidence_paths_and_derived_tax_keep_valid_receipt_confirmed():
    from types import SimpleNamespace

    from tera.llm import verify_facts
    from tera.reporting import make_report, merge_fragments
    from tera.schemas import ReceiptFacts

    quote = "Room\nNet EUR 100.00\nVAT 7%\nGross EUR 107.00"
    facts = ReceiptFacts(
        merchant="Hotel",
        invoice_date="2026-09-14",
        category="Hotel",
        currency="EUR",
        total="107.00",
        evidence=[{"field": "total", "page": 1, "quote": "Total EUR 107.00"}],
        items=[
            {
                "description": "Unterkunft",
                "category": "Hotel",
                "net": "100",
                "tax": "7",
                "gross": "107",
                "evidence": [
                    {"field": f"items.0.{field}", "page": 1, "quote": quote}
                    for field in ("net", "tax", "gross")
                ],
            }
        ],
    )
    # Tax must cite an amount, never the percentage printed on the line.
    facts.items[0].evidence = [e for e in facts.items[0].evidence if e.field != "items.0.tax"]
    pages = [{"page": 1, "text": quote + "\nTotal EUR 107.00"}]
    checked = verify_facts(facts, pages)
    assert not checked.notes
    assert checked.items[0].tax is None
    document = SimpleNamespace(id="a", filename="hotel.pdf", sha256="a", page_count=1)
    record = merge_fragments(document, [checked], [], [pages])
    assert record["derived_fields"] == ["items.0.tax"]
    assert record["facts"]["items"][0]["tax"] == "7"
    report = make_report([record], "test", "test")
    assert not report["warnings"]
    assert report["totals"]["by_currency"][0]["confirmed"] == "107"
    assert all("items.0.items" not in (source["field"] or "") for source in record["sources"])


def test_wrong_item_path_and_invented_amount_still_require_review():
    from tera.llm import verify_facts
    from tera.schemas import ReceiptFacts

    facts = ReceiptFacts(
        items=[
            {
                "description": "Unterkunft",
                "gross": "100",
                "evidence": [{"field": "items.1.gross", "page": 1, "quote": "Total 100"}],
            }
        ]
    )
    result = verify_facts(facts, [{"page": 1, "text": "Total 100"}])
    assert any("Bruttobetrag" in note for note in result.notes)
    assert all("items." not in note for note in result.notes)
    facts = ReceiptFacts(
        items=[
            {
                "description": "Unterkunft",
                "gross": "200",
                "evidence": [{"field": "gross", "page": 1, "quote": "Total 100"}],
            }
        ]
    )
    assert verify_facts(facts, [{"page": 1, "text": "Total 100"}]).notes


def test_tax_rate_is_not_evidence_of_tax_amount():
    from decimal import Decimal

    from tera.llm import contains_amount

    assert not contains_amount("VAT 7%", Decimal(7))
    assert contains_amount("VAT 7% EUR 39.20", Decimal("39.20"))


def test_breakfast_tax_derived_from_verified_line_amounts_has_no_false_warning():
    from tera.llm import verify_facts
    from tera.reconciliation import reconcile
    from tera.schemas import ReceiptFacts

    quote = "Breakfast Net EUR 60.00 VAT 19% Gross EUR 71.40"
    facts = ReceiptFacts(
        breakfast_tax="11.40",
        items=[
            {
                "description": "Frühstück",
                "category": "Verpflegung",
                "is_breakfast": True,
                "net": "60",
                "gross": "71.40",
                "tax": "11.40",
                "evidence": [
                    {"field": field, "page": 1, "quote": quote} for field in ("net", "tax", "gross")
                ],
            }
        ],
    )
    checked = verify_facts(facts, [{"page": 1, "text": quote}])
    assert not checked.notes
    assert checked.breakfast_tax is None
    reconciled, _, derived, _ = reconcile(checked)
    assert str(reconciled.breakfast_tax) == "11.40"
    assert "breakfast_tax" in derived


def test_derived_gross_and_resolved_echo_do_not_create_false_warning():
    from tera.llm import verify_facts
    from tera.reconciliation import reconcile
    from tera.schemas import ReceiptFacts

    quote = "机票\n100.00\n6%\n6.00"
    facts = ReceiptFacts(
        merchant="Airline",
        invoice_date="2026-07-29",
        category="Flugreisen",
        currency="CNY",
        total="106",
        evidence=[{"page": 1, "field": "total", "quote": "总金额 106.00"}],
        items=[
            {
                "description": "Flug",
                "category": "Flugreisen",
                "net": "100",
                "tax": "6",
                "gross": "106",
                "evidence": [
                    {"page": 1, "field": field, "quote": quote} for field in ("net", "tax")
                ],
            }
        ],
        notes=["Position 1 (Flug): Bruttobetrag nicht eindeutig im Beleg nachgewiesen."],
    )
    checked = verify_facts(facts, [{"page": 1, "text": quote + "\n总金额 106.00"}])
    assert not checked.notes
    assert checked.items[0].gross is None
    result, issues, derived, _ = reconcile(checked)
    assert not issues
    assert result.items[0].gross == 106
    assert "items.0.gross" in derived


def test_supported_hotel_price_needs_no_tax_split():
    from tera.llm import verify_facts
    from tera.reconciliation import reconcile
    from tera.schemas import ReceiptFacts

    facts = ReceiptFacts(
        merchant="Hotel",
        invoice_date="2026-07-29",
        category="Hotel",
        currency="CNY",
        total="278.98",
        items=[
            {
                "description": "Zimmer",
                "category": "Hotel",
                "gross": "278.98",
                "evidence": [{"page": 1, "field": "gross", "quote": "房费\n1间\n278.98"}],
            }
        ],
        evidence=[{"page": 1, "field": "total", "quote": "总金额\n278.98"}],
    )
    checked = verify_facts(facts, [{"page": 1, "text": "房费\n1间\n278.98\n总金额\n278.98"}])
    assert not checked.notes
    assert not reconcile(checked)[1]
