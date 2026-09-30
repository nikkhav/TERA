"""Validate monetary relationships without asking the model to do arithmetic."""

from decimal import Decimal

from tera.labels import FIELD_LABELS
from tera.schemas import Category, ReceiptFacts, ValidationIssue


def reconcile(facts: ReceiptFacts):
    facts = facts.model_copy(deep=True)
    issues, derived = [], []
    all_pages = sorted(
        {e.page for e in facts.evidence + [e for i in facts.items for e in i.evidence]}
    )

    def issue(code, message, fields, pages=None):
        issues.append(
            ValidationIssue(
                code=code,
                message=message,
                fields=fields,
                pages=all_pages if pages is None else sorted(set(pages)),
            )
        )

    for field in ("merchant", "invoice_date", "category", "currency", "total"):
        if getattr(facts, field) is None:
            issue("missing_field", f"Fehlende oder unklare Angabe: {FIELD_LABELS[field]}.", [field])
    if facts.service_start and facts.service_end and facts.service_start > facts.service_end:
        issue(
            "invalid_period",
            "Leistungszeitraum ist widersprüchlich.",
            ["service_start", "service_end"],
        )
    if (
        facts.category == Category.HOTEL
        and facts.service_start
        and facts.service_end
        and facts.overnight_count is not None
        and (facts.service_end - facts.service_start).days != facts.overnight_count
    ):
        issue(
            "overnight_mismatch",
            "Anzahl der Übernachtungen stimmt nicht mit An- und Abreise überein.",
            ["overnight_count", "service_start", "service_end"],
        )
    if facts.multiple_receipts:
        issue(
            "multiple_receipts", "Mehrere Belege in einer PDF; bitte getrennte PDFs verwenden.", []
        )

    if facts.net_total is not None and facts.tax_total is not None and facts.total is not None:
        calculated = facts.net_total + facts.tax_total
        if calculated != facts.total:
            issue(
                "invoice_tax_mismatch",
                f"Nettosumme + Steuer ({calculated}) stimmt nicht mit Gesamtbetrag ({facts.total}) überein.",
                ["net_total", "tax_total", "total"],
            )

    for index, item in enumerate(facts.items):
        prefix = f"items.{index}"
        pages = [e.page for e in item.evidence]
        if item.tax is None and item.net is not None and item.gross is not None:
            item.tax = item.gross - item.net
            derived.append(prefix + ".tax")
        if item.net is not None and item.tax is not None:
            calculated = item.net + item.tax
            if item.gross is None:
                item.gross = calculated
                derived.append(prefix + ".gross")
            elif calculated != item.gross:
                issue(
                    "line_tax_mismatch",
                    f"Position {index + 1}: Netto + Steuer ({calculated}) weicht von Brutto ({item.gross}) ab.",
                    [prefix + ".net", prefix + ".tax", prefix + ".gross"],
                    pages,
                )
        if item.gross is None:
            issue(
                "missing_line_gross",
                f"Position {index + 1}: Bruttobetrag nicht bestimmbar.",
                [prefix + ".gross"],
                pages,
            )
        if item.category is None:
            issue(
                "missing_line_category",
                f"Position {index + 1}: Kategorie fehlt.",
                [prefix + ".category"],
                pages,
            )
        if item.is_breakfast and item.category != Category.MEALS:
            issue(
                "breakfast_category",
                "Frühstück muss Verpflegung zugeordnet sein.",
                [prefix + ".category"],
                pages,
            )

    if not facts.items:
        issue(
            "missing_items",
            "Keine Einzelpositionen für den Abgleich mit dem Gesamtbetrag verfügbar.",
            ["items"],
        )
    elif all(item.gross is not None for item in facts.items) and facts.total is not None:
        calculated = sum((item.gross for item in facts.items), Decimal(0))
        if calculated != facts.total:
            issue(
                "line_sum_mismatch",
                f"Summe der Positionen ({calculated}) weicht vom Gesamtbetrag ({facts.total}) ab; Differenz {facts.total - calculated}.",
                ["items", "total"],
            )

    for field, invoice_field in (("net", "net_total"), ("tax", "tax_total")):
        expected = getattr(facts, invoice_field)
        if (
            facts.items
            and expected is not None
            and all(getattr(item, field) is not None for item in facts.items)
        ):
            calculated = sum((getattr(item, field) for item in facts.items), Decimal(0))
            if calculated != expected:
                issue(
                    "line_component_mismatch",
                    f"Positionssumme für {FIELD_LABELS[field]} ({calculated}) weicht von {FIELD_LABELS[invoice_field]} ({expected}) ab.",
                    ["items", invoice_field],
                )

    breakfast_values = []
    if facts.breakfast_total is not None:
        breakfast_values.append(facts.breakfast_total)
    if facts.breakfast_net is not None and facts.breakfast_tax is not None:
        breakfast_values.append(facts.breakfast_net + facts.breakfast_tax)
    breakfast_items = [item for item in facts.items if item.is_breakfast]
    for item_field, field in (("net", "breakfast_net"), ("tax", "breakfast_tax")):
        if (
            getattr(facts, field) is None
            and breakfast_items
            and all(getattr(item, item_field) is not None for item in breakfast_items)
        ):
            setattr(
                facts,
                field,
                sum((getattr(item, item_field) for item in breakfast_items), Decimal(0)),
            )
            derived.append(field)
    if breakfast_items and all(item.gross is not None for item in breakfast_items):
        breakfast_values.append(sum((item.gross for item in breakfast_items), Decimal(0)))
    if len(set(breakfast_values)) > 1:
        issue(
            "breakfast_mismatch",
            "Frühstückssummen aus Positionen, Netto/Steuer und Brutto widersprechen sich.",
            ["items", "breakfast_total", "breakfast_net", "breakfast_tax"],
        )
        facts.breakfast_total = None
    elif breakfast_values:
        if facts.breakfast_total is None:
            derived.append("breakfast_total")
        facts.breakfast_total = breakfast_values[0]
    if (
        facts.total is not None
        and facts.breakfast_total is not None
        and (
            abs(facts.breakfast_total) > abs(facts.total) or facts.breakfast_total * facts.total < 0
        )
    ):
        issue(
            "breakfast_out_of_range",
            "Frühstücksbetrag ist nicht mit dem Gesamtbetrag vereinbar.",
            ["breakfast_total", "total"],
        )
        facts.breakfast_total = None
    if (
        facts.category == Category.HOTEL
        and facts.breakfast_total is not None
        and facts.items
        and not breakfast_items
        and facts.breakfast_total != 0
    ):
        issue(
            "breakfast_not_itemized",
            "Frühstück ist in den Positionen nicht getrennt ausgewiesen.",
            ["items", "breakfast_total"],
        )

    items_reconciled = bool(facts.items) and not issues
    return facts, issues, derived, items_reconciled
