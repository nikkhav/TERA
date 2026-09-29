import logging
import re
import time
from decimal import Decimal

import httpx

from tera.chunking import prompt_budget
from tera.labels import FIELD_LABELS
from tera.prompts import build_prompt
from tera.schemas import ReceiptFacts

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


class OllamaExtractor:
    def __init__(self, settings):
        self.settings = settings
        self.model = settings.ollama_model

    def extract(
        self, document_id: str, pages: list[dict], feedback: str | None = None
    ) -> ReceiptFacts:
        prompt = build_prompt(document_id, pages, feedback)
        if len(prompt.encode()) > prompt_budget(self.settings):
            raise NonRetryableExtractionError("Input exceeds the configured context budget")
        payload = {
            "model": self.model,
            "prompt": prompt,
            "format": ReceiptFacts.model_json_schema(),
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
        return verify_facts(facts, pages)


def verify_facts(facts: ReceiptFacts, pages: list[dict]) -> ReceiptFacts:
    """Verify exact quotations and monetary evidence within their owning item."""
    page_text = {}
    for page in pages:
        page_text.setdefault(page["page"], []).append(" ".join(page["text"].split()))

    def verify(evidence, index=None):
        verified = []
        for evidence_item in evidence:
            item = evidence_item.model_copy()
            if index is not None and item.field:
                prefix = f"items.{index}."
                item.field = item.field.removeprefix(prefix)
            if any(" ".join(item.quote.split()) in text for text in page_text.get(item.page, [])):
                verified.append(item)
        return verified

    def supported(owner, field):
        value = getattr(owner, field)
        return value is not None and any(
            e.field == field and contains_amount(e.quote, value) for e in owner.evidence
        )

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
    if not facts.evidence and not any(item.evidence for item in facts.items):
        facts.notes.append("Keine überprüfbaren Textbelege vom Modell geliefert.")
    return facts
