"""Merge fragments conservatively; calculate and render reports without an LLM."""

import re
from collections import defaultdict
from copy import deepcopy
from decimal import Decimal

from tera.document_links import link_documents
from tera.exchange_rates import euro_amount
from tera.labels import FIELD_LABELS
from tera.reconciliation import reconcile
from tera.relationships import apply_relationship_decisions, explicitly_separate
from tera.schemas import Category, ReceiptFacts, ValidationIssue
from tera.transport import attach_flight_route, route_label

CATEGORIES = [item.value for item in Category]
VALIDITY_NOTICE = re.compile(
    r"Gültigkeitszeitraum (?:endet|beginnt) am \d{1,2}\.\d{1,2}\.\d{4}"
    r"(?: um \d{1,2}:\d{2} Uhr)?\.?"
)


def merge_fragments(document, fragments, errors, chunks):
    values, warnings = {}, list(errors)
    for field in ReceiptFacts.model_fields:
        if field in {"evidence", "notes", "notices", "multiple_receipts", "items"}:
            continue
        unique = []
        for fragment in fragments:
            value = getattr(fragment, field)
            if value is not None and value not in unique:
                unique.append(value)
        values[field] = unique[0] if len(unique) == 1 else None
        if len(unique) > 1:
            warnings.append(
                f"Widersprüchliche Werte für {FIELD_LABELS.get(field, 'Belegangaben')}; manuelle Prüfung erforderlich."
            )
    items, anchors = [], {}
    for fragment_index, fragment in enumerate(fragments):
        warnings.extend(
            note
            for note in fragment.notes
            if not re.match(r"^[a-z_]+:\s", note)
            and not VALIDITY_NOTICE.fullmatch(note)
            and not note.startswith("Check ")
            and not re.search(r"nicht eindeutig im Beleg nachgewiesen\.?$", note)
            and not note.startswith(
                (
                    "Keine überprüfbaren Textbelege",
                    "Summe der Positionen",
                    "Fehlende oder unklare Angabe:",
                )
            )
        )
        for item in fragment.items:
            # Only verified offsets identify a source occurrence. A quote alone can repeat.
            anchor = tuple(
                sorted(
                    {
                        (e.page, e.start, e.end)
                        for e in item.evidence
                        if e.start is not None and e.end is not None
                    }
                )
            )
            if anchor and anchor in anchors:
                prior_index, prior = anchors[anchor]
                if prior_index == fragment_index:
                    items.append(item)
                    continue
                if item.model_dump(exclude={"evidence"}) != prior.model_dump(exclude={"evidence"}):
                    warnings.append("Widersprüchliche Positionen mit identischem Textbeleg.")
                    items.append(item)
                continue
            items.append(item)
            if anchor:
                anchors[anchor] = (fragment_index, item)
    facts = ReceiptFacts(
        **values,
        items=items,
        multiple_receipts=any(f.multiple_receipts for f in fragments),
        evidence=[e for f in fragments for e in f.evidence],
    )
    if any(fragment._evidence_checked for fragment in fragments):
        from tera.llm import verify_facts

        full_pages = getattr(document, "pages", None) or [p for chunk in chunks for p in chunk]
        facts = verify_facts(facts, full_pages)
        warnings.extend(facts.notes)
    attach_flight_route(
        facts, getattr(document, "pages", None) or [p for chunk in chunks for p in chunk]
    )
    facts, issues, derived, items_reconciled = reconcile(facts)
    pages = sorted({p["page"] for chunk in chunks for p in chunk})
    issues.extend(
        ValidationIssue(code="extraction_review", message=w, pages=pages) for w in warnings
    )
    notices = list(
        dict.fromkeys([note for fragment in fragments for note in fragment.notices] + facts.notices)
    )
    notices.extend(
        note for fragment in fragments for note in fragment.notes if VALIDITY_NOTICE.fullmatch(note)
    )
    if facts.document_kind in {"payment", "booking", "supporting"}:
        notices.append(
            {
                "payment": "Zahlungsnachweis; nicht als zusätzliche Ausgabe summiert.",
                "booking": "Buchungsbestätigung; nicht als zusätzliche Ausgabe summiert.",
                "supporting": "Ergänzende Unterlage; nicht als zusätzliche Ausgabe summiert.",
            }[facts.document_kind]
        )
    return {
        "document_id": document.id,
        "filename": document.filename,
        "sha256": document.sha256,
        "page_count": document.page_count,
        "facts": facts.model_dump(
            mode="json", exclude={"notes", "notices", "evidence", "multiple_receipts"}
        ),
        "sources": [dict(document_id=document.id, **e.model_dump()) for e in facts.evidence]
        + [
            dict(
                document_id=document.id,
                **dict(e.model_dump(), field=f"items.{i}.{e.field or 'description'}"),
            )
            for i, item in enumerate(facts.items)
            for e in item.evidence
        ],
        "warnings": list(dict.fromkeys(issue.message for issue in issues)),
        "notices": notices,
        "validation_issues": [issue.model_dump() for issue in issues],
        "derived_fields": derived,
        "items_reconciled": items_reconciled,
        "recheck_attempted": False,
        "initial_issues": [],
        "extraction_failed": bool(errors),
    }


def mark_duplicates(records):
    groups = defaultdict(list)
    for record in records:
        f = record["facts"]
        if f.get("category") != "Hotel":
            f["overnight_count"] = None
            f["room_count"] = None
        if record.get("duplicate_of") or f.get("document_kind") in {
            "payment",
            "booking",
            "supporting",
        }:
            continue
        if all(f[key] is not None for key in ("merchant", "invoice_number", "currency", "total")):
            key = (
                (
                    f["merchant"]
                    if record.get("correction_history")
                    else record.get("original_texts", {}).get("merchant") or f["merchant"]
                )
                .casefold()
                .strip(),
                f["invoice_number"].casefold().strip(),
                f["currency"],
                Decimal(f["total"]),
            )
            groups[key].append(record)
    for group in groups.values():
        if len(group) > 1:
            for record in group:
                record["related_document_ids"] = list(
                    dict.fromkeys(
                        record.get("related_document_ids", [])
                        + [other["document_id"] for other in group if other is not record]
                    )
                )
                if all(other is record or explicitly_separate(record, other) for other in group):
                    continue
                record["warnings"].append(
                    "Möglicher Doppelbeleg; nicht in bestätigten Summen enthalten."
                )


def make_report(records, model, prompt_version):
    records = deepcopy(records)
    link_documents(records)
    apply_relationship_decisions(records)
    mark_duplicates(records)
    expenses, accommodation, warnings = [], [], []
    for record in records:
        f = record["facts"]
        total = Decimal(f["total"]) if f["total"] is not None else None
        breakfast = Decimal(f["breakfast_total"]) if f["breakfast_total"] is not None else None
        category = f["category"] or "Sonstige Ausgaben"
        decision = (record.get("review_history") or [{}])[-1].get("decision")
        if record.get("correction_history") and decision == "pending":
            record["warnings"].append("Manuell geänderte Angaben müssen bestätigt werden.")
        record["status"] = (
            decision
            if decision in {"approved", "rejected"}
            else "needs_review"
            if record["warnings"]
            else "extracted"
        )
        if record.get("duplicate_of") or f.get("document_kind") in {
            "payment",
            "booking",
            "supporting",
        }:
            record["status"] = "needs_review" if record.get("extraction_failed") else "supporting"
            if record["status"] == "needs_review":
                warnings.extend(
                    {
                        "document_id": record["document_id"],
                        "filename": record["filename"],
                        "message": message,
                    }
                    for message in dict.fromkeys(record["warnings"])
                )
            continue
        base = {
            "document_id": record["document_id"],
            "filename": record["filename"],
            "date": f.get("service_start") or f["invoice_date"],
            "service_start": f["service_start"],
            "service_end": f["service_end"],
            "merchant": f["merchant"],
            "currency": f["currency"],
            "status": record["status"],
            "pages": sorted({source["page"] for source in record["sources"]}),
        }
        if record.get("items_reconciled"):
            grouped = defaultdict(list)
            for item in f["items"]:
                grouped[item["category"] or category].append(item)
            for item_category, items in grouped.items():
                label = item_category
                merchant = (f.get("merchant") or "").casefold()
                if item_category in {"Sonstige Ausgaben", "Transport"} and any(
                    name in merchant for name in ("uber", "rasier")
                ):
                    label = "Taxifahrt einschließlich Gebühren"
                if len(items) == 1:
                    label = items[0]["description"]
                elif item_category == "Hotel":
                    label = "Unterkunft einschließlich Gebühren"
                elif item_category == "Verpflegung" and all(i["is_breakfast"] for i in items):
                    label = "Frühstück"
                elif route_label(f):
                    label = route_label(f)
                elif f.get("transport_mode"):
                    label = f["transport_mode"]
                expenses.append(
                    dict(
                        base,
                        category=item_category,
                        description=label,
                        amount=str(sum(Decimal(item["gross"]) for item in items)),
                        pages=sorted({e["page"] for item in items for e in item["evidence"]}),
                    )
                )
        elif category == "Hotel" and total is not None and breakfast is not None:
            expenses.extend(
                [
                    dict(
                        base,
                        category="Hotel",
                        description="Unterkunft einschließlich Beherbergungssteuern",
                        amount=str(total - breakfast),
                    ),
                    dict(
                        base, category="Verpflegung", description="Frühstück", amount=str(breakfast)
                    ),
                ]
            )
        else:
            expenses.append(
                dict(
                    base,
                    category=category,
                    description=(
                        route_label(f)
                        if route_label(f)
                        else "Taxifahrt"
                        if category == "Transport"
                        and any(
                            name in (f.get("merchant") or "").casefold()
                            for name in ("uber", "rasier")
                        )
                        else f.get("transport_mode")
                        if category == "Transport" and f.get("transport_mode")
                        else "Fahrt"
                        if category == "Transport"
                        else category
                    ),
                    amount=str(total) if total is not None else None,
                )
            )
        if category == "Hotel":
            accommodation.append(
                dict(
                    base,
                    total=f["total"],
                    breakfast=f["breakfast_total"],
                    without_breakfast=str(total - breakfast)
                    if total is not None and breakfast is not None
                    else None,
                )
            )
        if record["status"] == "needs_review":
            warnings.extend(
                {
                    "document_id": record["document_id"],
                    "filename": record["filename"],
                    "message": message,
                }
                for message in dict.fromkeys(record["warnings"])
            )
    for expense in expenses:
        record = next(r for r in records if r["document_id"] == expense["document_id"])
        expense["exchange_rate"] = record.get("exchange_rate")
        expense["amount_eur"] = euro_amount(
            expense["amount"], expense["currency"], record.get("exchange_rate")
        )
    expenses.sort(
        key=lambda e: (e["date"] or "9999", e["document_id"], CATEGORIES.index(e["category"]))
    )

    def aggregate(keys, euro=False):
        groups = {}
        for expense in expenses:
            if euro:
                expense = dict(expense, amount=expense["amount_eur"], currency="EUR")
            key = tuple(expense[k] for k in keys)
            group = groups.setdefault(
                key,
                {
                    **dict(zip(keys, key)),
                    "confirmed": Decimal(0),
                    "in_review": Decimal(0),
                    "excluded": Decimal(0),
                    "unknown_amounts": 0,
                },
            )
            if expense["amount"] is None:
                group["unknown_amounts"] += 1
            else:
                target = (
                    "excluded"
                    if expense["status"] == "rejected"
                    else "confirmed"
                    if expense["status"] in {"extracted", "approved"}
                    else "in_review"
                )
                group[target] += Decimal(expense["amount"])
        return [
            {k: str(v) if isinstance(v, Decimal) else v for k, v in group.items()}
            for _, group in sorted(
                groups.items(), key=lambda item: tuple(v or "~" for v in item[0])
            )
        ]

    by_currency = aggregate(["currency"])
    by_category = aggregate(["currency", "category"])
    for currency in [group["currency"] for group in by_currency]:
        for category in CATEGORIES:
            if not any(
                g["currency"] == currency and g["category"] == category for g in by_category
            ):
                by_category.append(
                    {
                        "currency": currency,
                        "category": category,
                        "confirmed": "0",
                        "in_review": "0",
                        "excluded": "0",
                        "unknown_amounts": 0,
                    }
                )
    by_category.sort(key=lambda g: (g["currency"] or "~", CATEGORIES.index(g["category"])))
    failed = sum(record["extraction_failed"] for record in records)
    report = {
        "schema_version": 3,
        "language": "de",
        "model": model,
        "prompt_version": prompt_version,
        "coverage": {
            "supplied": len(records),
            "processed": len(records) - failed,
            "failed": failed,
            "needs_review": sum(r["status"] == "needs_review" for r in records),
        },
        "documents": records,
        "expenses": expenses,
        "accommodation": accommodation,
        "totals": {
            "eur": aggregate(["currency"], euro=True),
            "by_category_eur": aggregate(["currency", "category"], euro=True),
            "by_date": aggregate(["date", "currency"]),
            "by_category": by_category,
            "by_currency": by_currency,
        },
        "warnings": warnings,
        "notices": [
            {
                "document_id": record["document_id"],
                "filename": record["filename"],
                "message": message,
            }
            for record in records
            for message in record.get("notices", [])
        ],
    }
    return report
