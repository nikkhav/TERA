"""Translate presentation text separately; numeric facts and source quotes never change."""

import json
import logging
import re

import httpx

from tera.prompts import LOCALIZE_PROMPT

logger = logging.getLogger(__name__)
FOREIGN_SCRIPT = re.compile(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]")


def translate_texts(texts, settings, notice_indexes=()):
    payload = {
        "model": settings.ollama_model,
        "prompt": LOCALIZE_PROMPT
        + json.dumps(
            [
                {"text": text, "is_notice": index in notice_indexes}
                for index, text in enumerate(texts)
            ],
            ensure_ascii=False,
        ),
        "format": {
            "type": "object",
            "properties": {
                "texts": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": len(texts),
                    "maxItems": len(texts),
                }
            },
            "required": ["texts"],
        },
        "stream": False,
        "options": {
            "temperature": 0,
            "num_ctx": settings.model_context_tokens,
            "num_predict": settings.model_output_tokens,
        },
    }
    if settings.ollama_think is not None:
        payload["think"] = settings.ollama_think
    with httpx.Client(timeout=settings.model_timeout_seconds) as client:
        response = client.post(settings.ollama_url.rstrip("/") + "/api/generate", json=payload)
        response.raise_for_status()
        data = response.json()
    if not data.get("done") or data.get("done_reason") == "length":
        raise ValueError("Incomplete translation")
    values = json.loads(data["response"])["texts"]
    if len(values) != len(texts) or any(
        not isinstance(v, str)
        or (not v.strip() and i not in notice_indexes)
        or FOREIGN_SCRIPT.search(v)
        for i, v in enumerate(values)
    ):
        raise ValueError("Invalid German translation")
    return values


def localize_record(record, settings, progress=lambda: None):
    facts = record["facts"]
    targets = []
    for field in ("merchant", "transport_mode", "origin", "destination"):
        if facts.get(field):
            targets.append((facts, field, "Anbieter" if field == "merchant" else "Reiseangabe"))
    for item in facts["items"]:
        targets.append((item, "description", item.get("category") or "Ausgabe"))
    for field in ("warnings", "notices"):
        targets.extend(
            (record[field], i, "Beleghinweis" if field == "notices" else "Belegangabe bitte prüfen")
            for i in range(len(record[field]))
        )
    record["original_texts"] = {
        "merchant": facts.get("merchant"),
        "items": [i["description"] for i in facts["items"]],
        "warnings": list(record["warnings"]),
        "notices": list(record["notices"]),
    }
    # Small batches leave room for longer German translations and prevent truncation.
    batch, size = [], 0
    batches = []
    for target in targets:
        length = len(target[0][target[1]].encode())
        if batch and size + length > 2000:
            batches.append(batch)
            batch, size = [], 0
        batch.append(target)
        size += length
    if batch:
        batches.append(batch)
    failed = False
    for batch in batches:
        originals = [owner[key] for owner, key, _ in batch]
        try:
            translated = translate_texts(
                originals,
                settings,
                [i for i, (owner, _, _) in enumerate(batch) if owner is record["notices"]],
            )
            for (owner, key, _), value in zip(batch, translated, strict=True):
                owner[key] = value
        except Exception:
            logger.exception("receipt_translation_failed document_id=%s", record["document_id"])
            failed = True
            for owner, key, fallback in batch:
                owner[key] = fallback + " (Übersetzung nicht verfügbar)"
        progress()
    record["notices"] = [text for text in record["notices"] if text.strip()]
    if failed:
        record["warnings"].append("Übersetzung nicht vollständig. Originaltext im Beleg prüfen.")
