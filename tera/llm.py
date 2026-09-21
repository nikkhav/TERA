import httpx

from tera.chunking import prompt_budget
from tera.prompts import build_prompt
from tera.schemas import ReceiptFacts


class OllamaExtractor:
    def __init__(self, settings):
        self.settings = settings
        self.model = settings.ollama_model

    def extract(self, document_id: str, pages: list[dict]) -> ReceiptFacts:
        prompt = build_prompt(document_id, pages)
        if len(prompt.encode()) > prompt_budget(self.settings):
            raise ValueError("Input exceeds the configured context budget")
        payload = {
            "model": self.model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0,
                "num_ctx": self.settings.model_context_tokens,
                "num_predict": self.settings.model_output_tokens,
            },
        }
        if self.settings.ollama_think is not None:
            payload["think"] = self.settings.ollama_think
        with httpx.Client(timeout=self.settings.model_timeout_seconds) as client:
            response = client.post(
                self.settings.ollama_url.rstrip("/") + "/api/generate", json=payload
            )
            response.raise_for_status()
            result = response.json()
        if not result.get("done") or result.get("done_reason") == "length":
            raise ValueError("Model response was truncated; document requires review")
        if result.get("prompt_eval_count", 0) > (
            self.settings.model_context_tokens - self.settings.model_output_tokens
        ):
            raise ValueError("Model reports insufficient remaining context")
        facts = ReceiptFacts.model_validate_json(result["response"])
        page_text = {}
        for page in pages:
            page_text.setdefault(page["page"], []).append(page["text"])
        verified_evidence = []
        for item in facts.evidence:
            quote = " ".join(item.quote.split())
            if any(quote in " ".join(t.split()) for t in page_text.get(item.page, [])):
                verified_evidence.append(item)
            else:
                facts.notes.append(f"Textbeleg für Seite {item.page} nicht im Dokument gefunden.")
        facts.evidence = verified_evidence
        if not facts.evidence:
            facts.notes.append("Keine überprüfbaren Textbelege vom Modell geliefert.")
        return facts
