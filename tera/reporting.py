"""Merge fragments conservatively; calculate and render reports without an LLM."""

from collections import defaultdict
from decimal import Decimal
from html import escape

from tera.schemas import Category, ReceiptFacts

CATEGORIES = [item.value for item in Category]


def merge_fragments(document, fragments, errors, chunks):
    values, warnings = {}, list(errors)
    for field in ReceiptFacts.model_fields:
        if field in {"evidence", "notes", "multiple_receipts"}:
            continue
        unique = []
        for fragment in fragments:
            value = getattr(fragment, field)
            if value is not None and value not in unique:
                unique.append(value)
        values[field] = unique[0] if len(unique) == 1 else None
        if len(unique) > 1:
            warnings.append(f"Widersprüchliche Werte für {field}; manuelle Prüfung erforderlich.")
    for fragment in fragments:
        warnings.extend(fragment.notes)
    if any(f.multiple_receipts for f in fragments):
        warnings.append("Mehrere Belege in einer PDF; bitte getrennte PDFs verwenden.")
    if any(part["part"] > 1 for chunk in chunks for part in chunk):
        warnings.append("Lange Seite aufgeteilt; Zusammenführung der Textfragmente prüfen.")
    for field in ("merchant", "invoice_date", "category", "currency", "total"):
        if values[field] is None:
            warnings.append(f"Fehlende oder unklare Angabe: {field}.")
    start, end = values["service_start"], values["service_end"]
    if start and end and start > end:
        warnings.append("Leistungszeitraum ist widersprüchlich.")
    total, breakfast = values["total"], values["breakfast_total"]
    if (
        total is not None
        and breakfast is not None
        and (abs(breakfast) > abs(total) or breakfast * total < 0)
    ):
        warnings.append("Frühstücksbetrag ist nicht mit dem Gesamtbetrag vereinbar.")
        values["breakfast_total"] = None
    facts = ReceiptFacts(**values)
    return {
        "document_id": document.id,
        "filename": document.filename,
        "sha256": document.sha256,
        "page_count": document.page_count,
        "facts": facts.model_dump(mode="json", exclude={"notes", "evidence", "multiple_receipts"}),
        "sources": [
            dict(document_id=document.id, **e.model_dump()) for f in fragments for e in f.evidence
        ],
        "warnings": list(dict.fromkeys(warnings)),
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
    mark_duplicates(records)
    expenses, accommodation, warnings = [], [], []
    for record in records:
        f = record["facts"]
        total = Decimal(f["total"]) if f["total"] is not None else None
        breakfast = Decimal(f["breakfast_total"]) if f["breakfast_total"] is not None else None
        category = f["category"] or "Sonstige Ausgaben"
        record["status"] = "needs_review" if record["warnings"] else "extracted"
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
        if category == "Hotel" and total is not None and breakfast is not None:
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
        warnings.extend(
            {"document_id": record["document_id"], "message": message}
            for message in record["warnings"]
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
                    "unknown_amounts": 0,
                },
            )
            if expense["amount"] is None:
                group["unknown_amounts"] += 1
            else:
                target = "confirmed" if expense["status"] == "extracted" else "in_review"
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
                        "unknown_amounts": 0,
                    }
                )
    by_category.sort(key=lambda g: (g["currency"] or "~", CATEGORIES.index(g["category"])))
    failed = sum(record["extraction_failed"] for record in records)
    report = {
        "schema_version": 1,
        "language": "de",
        "model": model,
        "prompt_version": prompt_version,
        "coverage": {
            "supplied": len(records),
            "processed": len(records) - failed,
            "failed": failed,
            "needs_review": sum(bool(r["warnings"]) for r in records),
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
    }
    report["markdown"] = render_markdown(report)
    return report


def cell(value):
    if value is None:
        return "Unbekannt"
    # Keep PDF/model content as text, not HTML, links, or new Markdown rows.
    value = escape(str(value), quote=False).replace("\n", " ").replace("\r", " ")
    for character in ("\\", "|", "[", "]", "*", "_", "`", "#"):
        value = value.replace(character, "\\" + character)
    return value


def money(value):
    return "Unbekannt" if value is None else format(Decimal(value), "f").replace(".", ",")


def render_markdown(report):
    lines = ["# Reisekostenübersicht", "", "## Belegübersicht", ""]
    coverage = report["coverage"]
    lines.extend(
        [
            f"- Bereitgestellt: {coverage['supplied']}",
            f"- Verarbeitet: {coverage['processed']}",
            f"- Fehlgeschlagen: {coverage['failed']}",
            f"- Zu prüfen: {coverage['needs_review']}",
            "",
            "Nur bereitgestellte Dokumente berücksichtigt. Summen sind vorläufig.",
            "Fehlende Beträge sind nicht als Null zu verstehen.",
            "",
        ]
    )

    def table(title, headers, rows):
        lines.extend(
            [
                f"## {title}",
                "",
                "| " + " | ".join(headers) + " |",
                "| " + " | ".join("---" for _ in headers) + " |",
            ]
        )
        lines.extend("| " + " | ".join(cell(v) for v in row) + " |" for row in rows)
        if not rows:
            lines.append("Keine Einträge.")
        lines.append("")

    def period(e):
        return f"{e['service_start'] or 'Unbekannt'} bis {e['service_end'] or 'Unbekannt'}"

    def source(e):
        return f"{e['filename']} ({e['document_id']}) / {', '.join(map(str, e['pages'])) or 'Unbekannt'}"

    table(
        "Ausgaben nach Datum",
        [
            "Datum",
            "Leistungszeitraum",
            "Anbieter",
            "Kategorie",
            "Beschreibung",
            "Betrag",
            "Währung",
            "Beleg / Seite",
        ],
        [
            [
                e["date"],
                period(e),
                e["merchant"],
                e["category"],
                e["description"] + (" (zu prüfen)" if e["status"] == "needs_review" else ""),
                money(e["amount"]),
                e["currency"],
                source(e),
            ]
            for e in report["expenses"]
        ],
    )
    for title, key, columns in [
        ("Tagessummen", "by_date", [("Datum", "date"), ("Währung", "currency")]),
        (
            "Summen nach Kategorie",
            "by_category",
            [("Kategorie", "category"), ("Währung", "currency")],
        ),
        ("Gesamtsummen", "by_currency", [("Währung", "currency")]),
    ]:
        table(
            title,
            [label for label, _ in columns] + ["Bestätigt", "In Prüfung", "Fehlende Beträge"],
            [
                [g[field] for _, field in columns]
                + [money(g["confirmed"]), money(g["in_review"]), g["unknown_amounts"]]
                for g in report["totals"][key]
            ],
        )
    table(
        "Unterkunft und Frühstück",
        [
            "Beleg / Seite",
            "Zeitraum",
            "Währung",
            "Gesamtbetrag",
            "Frühstück",
            "Ohne Frühstück",
            "Berechnung / Hinweise",
        ],
        [
            [
                source(e),
                period(e),
                e["currency"],
                money(e["total"]),
                money(e["breakfast"]),
                money(e["without_breakfast"]),
                f"{money(e['total'])} − {money(e['breakfast'])}; übrige Steuern bleiben enthalten."
                if e["without_breakfast"] is not None
                else "Keine eindeutige Frühstückssumme verfügbar.",
            ]
            for e in report["accommodation"]
        ],
    )
    lines.extend(["## Prüfhinweise", ""])
    lines.extend(f"- {cell(w['document_id'])}: {cell(w['message'])}" for w in report["warnings"])
    if not report["warnings"]:
        lines.append("- Keine automatisch erkannten Unstimmigkeiten. Belege bitte prüfen.")
    return "\n".join(lines) + "\n"
