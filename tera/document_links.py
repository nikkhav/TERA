"""Relate evidence documents without automatically merging uncertain matches."""

import re
from collections import defaultdict
from decimal import Decimal


def link_documents(records):
    """Link complementary documents only with an evidenced shared service reference."""
    groups = defaultdict(list)
    for record in records:
        # Rebuild derived findings when a reviewer changes a role, amount or reference.
        record["warnings"] = [
            w
            for w in record["warnings"]
            if not w.startswith(
                (
                    "Möglicher Doppelbeleg;",
                    "Möglicherweise dieselbe Ausgabe",
                    "Zusammengehörige Belege mit",
                    "Gemeinsame Referenz, aber",
                )
            )
        ]
        record["notices"] = [
            n
            for n in record.get("notices", [])
            if not n.startswith("Zusätzlicher Nachweis derselben Ausgabe;")
        ]
        record["related_document_ids"] = []
        record["duplicate_of"] = None
        facts = record["facts"]
        reference = facts.get("service_reference")
        # An LLM-provided reference must also appear in a verified quotation.
        if not reference or len(re.sub(r"\W", "", reference)) < 6:
            continue
        normalized = re.sub(r"\W", "", reference).casefold()
        if not any(
            source.get("field") == "service_reference"
            and normalized in re.sub(r"\W", "", source["quote"]).casefold()
            for source in record["sources"]
        ):
            continue
        groups[normalized].append(record)
    for group in groups.values():
        if len(group) < 2:
            continue
        for record in group:
            record["related_document_ids"] = [r["document_id"] for r in group if r is not record]
        costs = [r for r in group if r["facts"].get("document_kind") in {"invoice", "receipt"}]
        if len(costs) < 2:
            continue
        kinds = {r["facts"].get("document_kind") for r in costs}
        dates = {r["facts"].get("service_start") for r in costs if r["facts"].get("service_start")}
        routes = {
            (r["facts"].get("origin"), r["facts"].get("destination"))
            for r in costs
            if r["facts"].get("origin") and r["facts"].get("destination")
        }
        if len(costs) != 2 or kinds != {"invoice", "receipt"} or len(dates) > 1 or len(routes) > 1:
            for record in costs:
                record["warnings"].append(
                    "Gemeinsame Referenz, aber keine eindeutige Zuordnung zu einer einzelnen Ausgabe; Belege gemeinsam prüfen."
                )
            continue
        currencies = {r["facts"].get("currency") for r in costs}
        amounts = {
            Decimal(r["facts"]["total"]) if r["facts"].get("total") is not None else None
            for r in costs
        }
        if (
            len(currencies) == 1
            and None not in currencies
            and len(amounts) == 1
            and None not in amounts
        ):
            primary = min(
                costs,
                key=lambda r: (
                    r["extraction_failed"],
                    bool(r["warnings"]),
                    r["facts"].get("document_kind") != "invoice",
                    r["document_id"],
                ),
            )
            for record in costs:
                if record is not primary:
                    record["duplicate_of"] = primary["document_id"]
                    record["notices"] = list(
                        dict.fromkeys(
                            record.get("notices", [])
                            + [
                                "Zusätzlicher Nachweis derselben Ausgabe; Betrag wird nur einmal berücksichtigt."
                            ]
                        )
                    )
        else:
            for record in costs:
                record["warnings"].append(
                    "Zusammengehörige Belege mit unterschiedlichen oder fehlenden Beträgen/Währungen; gemeinsam prüfen."
                )

    # Without a shared reference this is only a candidate, never an automatic merge.
    for index, left in enumerate(records):
        for right in records[index + 1 :]:
            a, b = left["facts"], right["facts"]
            if left.get("duplicate_of") or right.get("duplicate_of"):
                continue
            if {a.get("document_kind"), b.get("document_kind")} != {"invoice", "receipt"}:
                continue
            if not all(
                a.get(k) is not None and b.get(k) is not None for k in ("total", "currency")
            ):
                continue
            if (
                a.get("service_reference")
                and b.get("service_reference")
                and a["service_reference"] != b["service_reference"]
            ):
                continue
            day_a = a.get("service_start") or a.get("invoice_date")
            day_b = b.get("service_start") or b.get("invoice_date")
            if (
                not day_a
                or day_a != day_b
                or a["currency"] != b["currency"]
                or Decimal(a["total"]) != Decimal(b["total"])
            ):
                continue
            merchant_a = (
                left.get("original_texts", {}).get("merchant") or a.get("merchant") or ""
            ).casefold()
            merchant_b = (
                right.get("original_texts", {}).get("merchant") or b.get("merchant") or ""
            ).casefold()
            same_provider = merchant_a and merchant_a == merchant_b
            uber_pair = all(
                any(name in merchant for name in ("uber", "rasier"))
                for merchant in (merchant_a, merchant_b)
            )
            same_route = all(a.get(k) and a.get(k) == b.get(k) for k in ("origin", "destination"))
            same_time = a.get("service_time") and a.get("service_time") == b.get("service_time")
            if (same_provider or uber_pair) and (same_route or same_time or uber_pair):
                for record, other in ((left, right), (right, left)):
                    record["related_document_ids"] = list(
                        dict.fromkeys(record["related_document_ids"] + [other["document_id"]])
                    )
                    record["warnings"].append(
                        "Möglicherweise dieselbe Ausgabe wie ein weiterer Beleg; beide Nachweise gemeinsam prüfen, bevor der Betrag bestätigt wird."
                    )
