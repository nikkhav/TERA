"""Merge fragments conservatively; calculate and render reports without an LLM."""

from collections import defaultdict
from copy import deepcopy
from decimal import Decimal

from tera.labels import FIELD_LABELS
from tera.reconciliation import reconcile
from tera.schemas import Category, ReceiptFacts, ValidationIssue

CATEGORIES = [item.value for item in Category]


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
    for fragment in fragments:
        warnings.extend(fragment.notes)
        for item in fragment.items:
            anchor = tuple(sorted((e.page, " ".join(e.quote.split())) for e in item.evidence))
            if anchor and anchor in anchors:
                prior = anchors[anchor]
                if item.model_dump(exclude={"evidence"}) != prior.model_dump(exclude={"evidence"}):
                    warnings.append("Widersprüchliche Positionen mit identischem Textbeleg.")
                continue
            items.append(item)
            if anchor:
                anchors[anchor] = item
    facts = ReceiptFacts(
        **values,
        items=items,
        multiple_receipts=any(f.multiple_receipts for f in fragments),
        evidence=[e for f in fragments for e in f.evidence],
    )
    facts, issues, derived, items_reconciled = reconcile(facts)
    pages = sorted({p["page"] for chunk in chunks for p in chunk})
    issues.extend(
        ValidationIssue(code="extraction_review", message=w, pages=pages) for w in warnings
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
        "notices": list(dict.fromkeys(note for fragment in fragments for note in fragment.notices)),
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
        if all(f[key] is not None for key in ("merchant", "invoice_number", "currency", "total")):
            key = (
                f["merchant"].casefold().strip(),
                f["invoice_number"].casefold().strip(),
                f["currency"],
                Decimal(f["total"]),
            )
            groups[key].append(record)
    for group in groups.values():
        if len(group) > 1:
            for record in group:
                record["warnings"].append(
                    "Möglicher Doppelbeleg; nicht in bestätigten Summen enthalten."
                )


def make_report(records, model, prompt_version):
    records = deepcopy(records)
    mark_duplicates(records)
    expenses, accommodation, warnings = [], [], []
    for record in records:
        f = record["facts"]
        total = Decimal(f["total"]) if f["total"] is not None else None
        breakfast = Decimal(f["breakfast_total"]) if f["breakfast_total"] is not None else None
        category = f["category"] or "Sonstige Ausgaben"
        decision = (record.get("review_history") or [{}])[-1].get("decision")
        record["status"] = (
            decision
            if decision in {"approved", "rejected"}
            else "needs_review"
            if record["warnings"]
            else "extracted"
        )
        base = {
            "document_id": record["document_id"],
            "filename": record["filename"],
            "date": f["invoice_date"],
            "service_start": f["service_start"],
            "service_end": f["service_end"],
            "merchant": f["merchant"],
            "currency": f["currency"],
            "status": record["status"],
            "pages": sorted({source["page"] for source in record["sources"]}),
        }
        if record.get("items_reconciled"):
            expenses.extend(
                dict(
                    base,
                    category=item["category"],
                    description=item["description"],
                    amount=item["gross"],
                    pages=sorted({e["page"] for e in item["evidence"]}),
                )
                for item in f["items"]
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
                    description=category,
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
    expenses.sort(
        key=lambda e: (e["date"] or "9999", e["document_id"], CATEGORIES.index(e["category"]))
    )

    def aggregate(keys):
        groups = {}
        for expense in expenses:
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
        "schema_version": 2,
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
