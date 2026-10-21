import logging
import re
import time
from decimal import Decimal

import httpx

from tera.chunking import prompt_budget
from tera.labels import FIELD_LABELS
from tera.note_review import review_model_notes
from tera.prompts import build_prompt
from tera.schemas import Evidence, ReceiptFacts
from tera.transport import attach_flight_route

logger = logging.getLogger(__name__)


class NonRetryableExtractionError(ValueError):
    """The same model request should not be repeated without changing its limits."""


def contains_amount(quote: str, amount: Decimal) -> bool:
    text = quote.replace("\u2212", "-")
    numbers = re.finditer(r"[+-]?(?:\d{1,3}(?:[ .,\u00a0]\d{3})+|\d+)(?:[.,]\d+)?", text)
    for match in numbers:
        if re.match(r"\s*[%％]", text[match.end() :]):
            continue
        number = match.group()
        number = number.replace(" ", "").replace("\u00a0", "")
        # Both 1,234.50 and 1.234,50 occur in multilingual receipts.
        candidates = {number.replace(",", ""), number.replace(".", "").replace(",", ".")}
        for candidate in candidates:
            if candidate.count(".") <= 1 and Decimal(candidate) == amount:
                return True
    return False


def contains_date(quote, value):
    year, month, day = value.year, value.month, value.day
    pattern = (
        rf"(?<!\d)(?:{year}[-/.年]0?{month}[-/.月]0?{day}日?|"
        rf"0?{day}[-/.]0?{month}[-/.]{year}|"
        rf"0?{month}[-/.]0?{day}[-/.]{year})(?!\d)"
    )
    if re.search(pattern, re.sub(r"\s+", "", quote)):
        return True
    month_names = (
        "January Januar",
        "February Februar",
        "March März",
        "April",
        "May Mai",
        "June Juni",
        "July Juli",
        "August",
        "September",
        "October Oktober",
        "November",
        "December Dezember",
    )[month - 1].split()
    names = "|".join(re.escape(name) for full in month_names for name in (full, full[:3]))
    return bool(
        re.search(rf"(?<!\d)0?{day}(?!\d)", quote)
        and re.search(rf"(?<!\d){year}(?!\d)", quote)
        and re.search(rf"\b(?:{names})\b", quote, re.IGNORECASE)
    )


def recover_invoice_date(facts, pages):
    """Locate a labeled issue date, or an unambiguous date heading on a ride receipt."""
    if facts.invoice_date is None:
        return None, False
    rows = []
    for page in pages:
        offset = page.get("text_start", 0)
        for index, block in enumerate(page.get("blocks", [])):
            raw = page["text"][max(0, block["start"] - offset) : block["end"] - offset]
            quote = raw.strip()
            if len(quote) <= 1000 and contains_date(quote, facts.invoice_date):
                start = block["start"] + len(raw) - len(raw.lstrip())
                evidence = Evidence(
                    page=page["page"],
                    field="invoice_date",
                    quote=quote,
                    block_id=block["id"],
                    start=start,
                    end=start + len(quote),
                )
                rows.append((page["page"], index, evidence))
    labeled = [
        e
        for _, _, e in rows
        if re.search(
            r"invoice\s+date|date\s+issued|Rechnungsdatum|开票日期", e.quote, re.IGNORECASE
        )
    ]
    if labeled:
        return (labeled[0], False) if len(labeled) == 1 else (None, False)
    ride = re.search(
        r"uber|rasier|taxi|cab|rideshare|出租车",
        " ".join(filter(None, [facts.merchant, facts.transport_mode])),
        re.IGNORECASE,
    )
    if facts.document_kind != "receipt" or not ride:
        return None, False
    # A ride receipt's standalone heading is usable only when other numeric dates agree.
    dates = re.findall(
        r"(?<!\d)20\d{2}\s*[-/.年]\s*\d{1,2}\s*[-/.月]\s*\d{1,2}日?"
        r"|(?<!\d)\d{1,2}\s*[-/.]\s*\d{1,2}\s*[-/.]\s*20\d{2}(?!\d)",
        "\n".join(p["text"] for p in pages),
    )
    if any(not contains_date(printed, facts.invoice_date) for printed in dates):
        return None, False
    headings = [
        e
        for page, index, e in rows
        if page == 1
        and index < 12
        and re.fullmatch(
            r"(?:20\d{2}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日"
            r"|20\d{2}[-/.]\d{1,2}[-/.]\d{1,2})",
            e.quote,
        )
    ]
    return (headings[0], True) if len(headings) == 1 else (None, False)


def refresh_saved_date_source(record, pages):
    """Repair a missing date quotation without changing facts or reviewer decisions."""
    warning = "Rechnungsdatum nicht eindeutig im Beleg nachgewiesen."
    if (
        warning not in record["warnings"]
        or record.get("correction_history")
        or record.get("extraction_failed")
    ):
        return False
    facts = ReceiptFacts.model_validate(record["facts"])
    evidence, inferred = recover_invoice_date(facts, pages)
    if evidence is None:
        return False
    source = dict(document_id=record["document_id"], **evidence.model_dump())
    if re.search(r"[\u3400-\u9fff]", evidence.quote):
        source["translation"] = f"Belegdatum: {facts.invoice_date.isoformat()}"
    record["sources"] = [s for s in record["sources"] if s.get("field") != "invoice_date"] + [
        source
    ]
    record["warnings"] = [w for w in record["warnings"] if w != warning]
    record["validation_issues"] = [
        i for i in record.get("validation_issues", []) if i["message"] != warning
    ]
    if inferred:
        notice = "Belegdatum aus der Datumszeile im Kopf der Quittung übernommen."
        record["notices"] = list(dict.fromkeys(record.get("notices", []) + [notice]))
    return True


class OllamaExtractor:
    def __init__(self, settings):
        self.settings = settings
        self.model = settings.ollama_model
        self.heartbeat = lambda: None

    def extract(
        self, document_id: str, pages: list[dict], feedback: str | None = None
    ) -> ReceiptFacts:
        prompt = build_prompt(document_id, pages, feedback)
        if len(prompt.encode()) > prompt_budget(self.settings):
            raise NonRetryableExtractionError("Input exceeds the configured context budget")
        schema = ReceiptFacts.model_json_schema()
        for field, limit in (("notes", 2), ("notices", 3)):
            schema["properties"][field]["maxItems"] = limit
            schema["properties"][field]["items"] = {"type": "string", "maxLength": 300}
        schema["properties"]["evidence"]["maxItems"] = 12
        text = " ".join(page["text"] for page in pages)
        # Single-category receipts need a total, not a transcription of every fee.
        # Keep item extraction for explicit breakfast splits across expense categories.
        if not re.search(
            r"breakfast|frühstück|fruehstueck|早餐|早饭|petit.déjeuner|desayuno|colazione",
            text,
            re.IGNORECASE,
        ):
            schema["properties"]["items"]["maxItems"] = 0
        for object_schema in [schema, *schema.get("$defs", {}).values()]:
            if "properties" in object_schema:
                properties = object_schema["properties"]
                object_schema["required"] = list(properties)
                if "block_id" in properties:
                    block_ids = list(
                        dict.fromkeys(
                            block["id"] for page in pages for block in page.get("blocks", [])
                        )
                    )
                    properties["block_id"]["enum"] = block_ids or [None]
                    if block_ids:
                        properties["block_id"]["type"] = "string"
                        properties["block_id"].pop("anyOf", None)
                    properties["page"]["enum"] = sorted({page["page"] for page in pages})
                    if object_schema.get("title") == "Evidence":
                        properties["field"]["enum"] = [
                            "total",
                            "net_total",
                            "tax_total",
                            "breakfast_total",
                            "breakfast_net",
                            "breakfast_tax",
                            "currency",
                            "invoice_date",
                            "service_start",
                            "service_end",
                            "service_reference",
                        ]
        payload = {
            "model": self.model,
            "prompt": prompt,
            "format": schema,
            "stream": False,
            "options": {
                "temperature": 0,
                "num_ctx": self.settings.model_context_tokens,
                "num_predict": self.settings.model_output_tokens,
            },
        }
        if self.settings.ollama_think is not None:
            payload["think"] = self.settings.ollama_think
        started = time.monotonic()
        try:
            with httpx.Client(timeout=self.settings.model_timeout_seconds) as client:
                response = client.post(
                    self.settings.ollama_url.rstrip("/") + "/api/generate", json=payload
                )
                response.raise_for_status()
                result = response.json()
        except Exception:
            logger.exception(
                "llm_request_failed document_id=%s pages=%s correction=%s duration_seconds=%.2f",
                document_id,
                sorted({page["page"] for page in pages}),
                feedback is not None,
                time.monotonic() - started,
            )
            raise
        logger.info(
            "llm_request_finished document_id=%s pages=%s correction=%s "
            "duration_seconds=%.2f done=%s done_reason=%s prompt_tokens=%s output_tokens=%s "
            "response_bytes=%s",
            document_id,
            sorted({page["page"] for page in pages}),
            feedback is not None,
            time.monotonic() - started,
            result.get("done"),
            result.get("done_reason"),
            result.get("prompt_eval_count"),
            result.get("eval_count"),
            len(result.get("response", "").encode()),
        )
        if not result.get("done") or result.get("done_reason") == "length":
            raise NonRetryableExtractionError(
                "Model response was truncated; document requires review"
            )
        if result.get("prompt_eval_count", 0) > (
            self.settings.model_context_tokens - self.settings.model_output_tokens
        ):
            raise ValueError("Model reports insufficient remaining context")
        try:
            facts = ReceiptFacts.model_validate_json(result["response"])
        except Exception:
            logger.exception(
                "llm_response_invalid document_id=%s pages=%s correction=%s response_bytes=%s",
                document_id,
                sorted({page["page"] for page in pages}),
                feedback is not None,
                len(result.get("response", "").encode()),
            )
            raise
        if schema["properties"]["items"].get("maxItems") == 0:
            facts.items = []
        self.heartbeat()
        facts = review_model_notes(facts, self.settings)
        return verify_facts(facts, pages, validate_values=False)


def verify_facts(facts: ReceiptFacts, pages: list[dict], validate_values=True) -> ReceiptFacts:
    """Verify exact quotations and monetary evidence within their owning item."""

    def verify(evidence, index=None):
        verified = []
        for evidence_item in evidence:
            item = evidence_item.model_copy()
            if index is not None and item.field:
                prefix = f"items.{index}."
                item.field = item.field.removeprefix(prefix)
            if item.block_id:
                item.block_id = item.block_id.strip("[] ")
                owner = facts if index is None else facts.items[index]
                amount = getattr(owner, item.field or "", None)
                for page in pages:
                    if page["page"] != item.page:
                        continue
                    offset = page.get("text_start", 0)
                    for block in page.get("blocks", []):
                        if block["id"] != item.block_id:
                            continue
                        row_text = page["text"][
                            max(0, block["start"] - offset) : block["end"] - offset
                        ].strip()
                        row_text = row_text[:1000]
                        translated_quote = bool(
                            re.search(r"[\u3400-\u9fff]", row_text)
                            and not re.search(r"[\u3400-\u9fff]", item.quote)
                        )
                        if (not item.quote.strip() or translated_quote) and (
                            not isinstance(amount, Decimal) or contains_amount(row_text, amount)
                        ):
                            item.quote = row_text
            words = item.quote.split()
            if not words:
                continue
            pattern = r"\s+".join(re.escape(word) for word in words)
            matches = []
            for page in pages:
                if page["page"] != item.page:
                    continue
                offset = page.get("text_start", 0)
                for match in re.finditer(pattern, page["text"]):
                    start, end = offset + match.start(), offset + match.end()
                    blocks = [
                        block
                        for block in page.get("blocks", [])
                        if block["start"] <= start and end <= block["end"]
                    ]
                    if item.block_id and not any(b["id"] == item.block_id for b in blocks):
                        continue
                    if item.start is not None and item.start != start:
                        continue
                    if item.end is not None and item.end != end:
                        continue
                    matches.append((start, end, blocks))
            if not matches:
                continue
            # Never invent an occurrence for repeated text without a unique anchor.
            item.start = item.end = None
            if len(matches) == 1:
                item.start, item.end, blocks = matches[0]
                item.block_id = blocks[0]["id"] if len(blocks) == 1 else None
            verified.append(item)
        return verified

    def evidence_context(evidence):
        # A short amount quote can be anchored to a row that also contains its label.
        for page in pages:
            if page["page"] != evidence.page:
                continue
            offset = page.get("text_start", 0)
            for block in page.get("blocks", []):
                if evidence.block_id == block["id"]:
                    return page["text"][max(0, block["start"] - offset) : block["end"] - offset]
        return evidence.quote

    def supported(owner, field):
        value = getattr(owner, field)
        return value is not None and any(
            e.field == field
            and contains_amount(e.quote, value)
            and (
                field != "total"
                or not re.search(
                    r"deposit|prepayment|advance|balance due|subtotal|anzahlung|vorauszahlung|"
                    r"restbetrag|zwischensumme|предоплат|аванс|预付|押金",
                    evidence_context(e),
                    re.IGNORECASE,
                )
            )
            and (
                field != "total"
                or not any("blocks" in p for p in pages)
                or re.search(r"[^\d\s.,+\-€$£¥]", re.sub(r"\b[A-Z]{3}\b", "", evidence_context(e)))
            )
            for e in owner.evidence
        )

    if not validate_values or facts.document_kind in {"payment", "booking", "supporting"}:
        facts.evidence = verify(facts.evidence)
        for index, item in enumerate(facts.items):
            item.evidence = verify(item.evidence, index)
        facts._evidence_checked = True
        return facts

    # Recheck responses sometimes echo our previous evidence messages verbatim.
    # Remove only messages whose specific monetary claims are now verified below.
    echoed = []
    for note in facts.notes:
        match = re.fullmatch(
            r"Position (\d+) \(.+\): (.+) nicht eindeutig im Beleg nachgewiesen\.", note
        )
        if match and 0 < int(match[1]) <= len(facts.items):
            echoed.append((note, int(match[1]) - 1, match[2].split(", ")))
    for index, item in enumerate(facts.items):
        item.evidence = verify(item.evidence, index)
        # A model-calculated tax has no literal quote. Derive it later from verified amounts.
        if (
            item.tax is not None
            and not supported(item, "tax")
            and supported(item, "net")
            and supported(item, "gross")
            and item.tax == item.gross - item.net
        ):
            item.tax = None
            item.evidence = [e for e in item.evidence if e.field != "tax"]
        if (
            item.gross is not None
            and not supported(item, "gross")
            and supported(item, "net")
            and supported(item, "tax")
            and item.gross == item.net + item.tax
        ):
            item.gross = None
            item.evidence = [e for e in item.evidence if e.field != "gross"]
        resolved = {
            FIELD_LABELS[field] for field in ("net", "tax", "gross") if supported(item, field)
        }
        if supported(item, "net") and supported(item, "tax"):
            resolved.add(FIELD_LABELS["gross"])
        if supported(item, "net") and supported(item, "gross"):
            resolved.add(FIELD_LABELS["tax"])
        for note, item_index, labels in echoed:
            if item_index == index and set(labels) <= resolved and note in facts.notes:
                facts.notes.remove(note)
        missing = [
            FIELD_LABELS[field]
            for field in ("net", "tax", "gross")
            if getattr(item, field) is not None and not supported(item, field)
        ]
        if missing:
            facts.notes.append(
                f"Position {index + 1} ({item.description}): "
                + ", ".join(missing)
                + " nicht eindeutig im Beleg nachgewiesen."
            )

    facts.evidence = verify(facts.evidence)
    # Explicitly labeled totals can be located deterministically when the model omitted a citation.
    total_labels = {
        "total": r"\btotal\b|gesamtbetrag|gesamtsumme|gesamtpreis|价税合计|总金额|总计",
        "net_total": r"\bnet\b|\bnetto\b|nettobetrag|净额|未税",
        "tax_total": r"\bGST\b|\bVAT\b|\btax\b|steuerbetrag|税额|增值税",
    }
    for field, label in total_labels.items():
        amount = getattr(facts, field)
        if amount is None or any(e.field == field for e in facts.evidence):
            continue
        candidates = []
        for page in pages:
            offset = page.get("text_start", 0)
            for block in page.get("blocks", []):
                quote = page["text"][
                    max(0, block["start"] - offset) : block["end"] - offset
                ].strip()
                if (
                    len(quote) > 1000
                    or not contains_amount(quote, amount)
                    or not re.search(label, quote, re.IGNORECASE)
                ):
                    continue
                if field == "total" and re.search(
                    r"\bnet\b|\bGST\b|\bVAT\b|\btax\b|netto|subtotal|deposit|prepayment|anzahlung|zwischensumme|税额|净额",
                    quote,
                    re.IGNORECASE,
                ):
                    continue
                candidates.append(
                    Evidence(page=page["page"], field=field, quote=quote, block_id=block["id"])
                )
        if len(candidates) == 1:
            facts.evidence.extend(verify(candidates))
    if any("blocks" in page for page in pages):
        # Literal evidence is required; semantic interpretation remains a review task.
        for field in ("currency", "invoice_date"):
            value = getattr(facts, field)
            if value is None:
                continue
            quotes = [e.quote for e in facts.evidence if e.field == field]
            if field == "currency":
                pattern = rf"(?<![A-Z]){re.escape(value)}(?![A-Z])"
                symbol = {"EUR": "€", "GBP": "£", "AUD": "A$", "CNY": "CN¥", "USD": "US$"}.get(
                    value
                )
                currency_texts = quotes + [page["text"] for page in pages]
                found = any(
                    re.search(pattern, quote, re.IGNORECASE)
                    or (symbol and symbol in quote)
                    or (value == "AUD" and "AU$" in quote)
                    or (value == "CNY" and re.search(r"人民币|RMB|元", quote))
                    for quote in currency_texts
                )
                if not found and value == "AUD":
                    document_text = " ".join(page["text"] for page in pages)
                    # Australian domestic tax invoices often print '$' without an ISO code.
                    found = bool(
                        "$" in document_text
                        and re.search(r"\bABN\b", document_text)
                        and re.search(r"Australia", document_text, re.IGNORECASE)
                        and re.search(r"\bGST\b", document_text)
                        and not re.search(r"\b(?:USD|CAD|NZD|SGD|HKD)\b", document_text)
                    )
                    if found:
                        facts.notices.append(
                            "Währung AUD aus australischen Rechnungsangaben ($, ABN und GST) abgeleitet."
                        )
                if not found and value == "CNY":
                    document_text = " ".join(page["text"] for page in pages)
                    found = bool(
                        "¥" in document_text
                        and re.search(r"电子发票|增值税.*发票", document_text)
                        and "价税合计" in document_text
                        and not re.search(r"\bJPY\b|日本円", document_text)
                    )
                    if found:
                        facts.notices.append(
                            "Währung CNY aus chinesischer Steuerrechnung mit ¥-Beträgen abgeleitet."
                        )
            else:
                if not quotes:
                    evidence, inferred = recover_invoice_date(facts, pages)
                    if evidence is not None:
                        recovered = verify([evidence])
                        facts.evidence.extend(recovered)
                        quotes = [e.quote for e in recovered]
                        if recovered and inferred:
                            facts.notices.append(
                                "Belegdatum aus der Datumszeile im Kopf der Quittung übernommen."
                            )
                found = any(contains_date(quote, value) for quote in quotes)
            if not found:
                facts.notes.append(
                    f"{FIELD_LABELS.get(field, field)} nicht eindeutig im Beleg nachgewiesen."
                )
    # A verified gross-only receipt does not need a model-invented VAT breakdown.
    if not facts.items and supported(facts, "total"):
        for field in ("net_total", "tax_total"):
            if getattr(facts, field) is None:
                continue
            evidence = [e for e in facts.evidence if e.field == field]
            mislabeled_levy = field == "tax_total" and any(
                re.search(r"levy|government|政府|state.*tax", e.quote, re.IGNORECASE)
                and not re.search(r"\bGST\b|\bVAT\b|增值税", e.quote, re.IGNORECASE)
                for e in evidence
            )
            if not supported(facts, field) or mislabeled_levy:
                setattr(facts, field, None)
                facts.evidence = [e for e in facts.evidence if e.field != field]
                facts.notices.append(
                    "Nicht belegte Netto-/Steueraufteilung wurde nicht übernommen."
                )
    breakfast = [item for item in facts.items if item.is_breakfast]
    for field in (
        "total",
        "net_total",
        "tax_total",
        "breakfast_total",
        "breakfast_net",
        "breakfast_tax",
    ):
        value = getattr(facts, field)
        if value is None or supported(facts, field):
            continue
        item_field = {
            "breakfast_total": "gross",
            "breakfast_net": "net",
            "breakfast_tax": "tax",
        }.get(field)
        if (
            field == "breakfast_tax"
            and breakfast
            and all(supported(item, "net") and supported(item, "gross") for item in breakfast)
            and sum(item.gross - item.net for item in breakfast) == value
        ):
            facts.breakfast_tax = None
            facts.evidence = [e for e in facts.evidence if e.field != field]
            continue
        if (
            item_field
            and breakfast
            and all(supported(item, item_field) for item in breakfast)
            and sum(getattr(item, item_field) for item in breakfast) == value
        ):
            # Reconciliation records the aggregate as derived from the verified item amounts.
            setattr(facts, field, None)
            facts.evidence = [e for e in facts.evidence if e.field != field]
            continue
        facts.notes.append(f"{FIELD_LABELS[field]} nicht eindeutig im Beleg nachgewiesen.")
    attach_flight_route(facts, pages)
    if not facts.evidence and not any(item.evidence for item in facts.items):
        facts.notes.append("Keine überprüfbaren Textbelege vom Modell geliefert.")
    return facts
