"""Translate presentation text separately; numeric facts and source quotes never change."""

import json
import logging
import re

import httpx

from tera.prompts import LOCALIZE_PROMPT

logger = logging.getLogger(__name__)
FOREIGN_SCRIPT = re.compile(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]")


def needs_translation(text):
    return bool(
        FOREIGN_SCRIPT.search(text)
        or re.search(
            r"\b(?:room|breakfast|fare|toll|fee|levy|surcharge|flight|fuel|transportation|"
            r"government|fictional|sample|draft|cancelled|thank|booking)\b",
            text,
            re.IGNORECASE,
        )
    )


def translate_texts(texts, settings, notice_indexes=(), protect_numbers=True):
    protected, numbers = [], []
    for text in texts:
        values = []

        def protect(match, values=values):
            values.append(match.group())
            return f"__TERA_NUM_{len(values) - 1}__"

        masked = re.sub(r"\d+(?:[.,]\d+)*", protect, text)
        protected.append(masked if protect_numbers else text)
        numbers.append(values)
    payload = {
        "model": settings.ollama_model,
        "prompt": LOCALIZE_PROMPT
        + json.dumps(
            [
                {"text": text, "is_notice": index in notice_indexes}
                for index, text in enumerate(protected)
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
    if not isinstance(values, list) or len(values) != len(texts):
        raise ValueError("Invalid German translation count")
    for index, value in enumerate(values):
        if not isinstance(value, str):
            raise TypeError("Invalid German translation text")
        for number_index, number in enumerate(numbers[index] if protect_numbers else []):
            marker = f"__TERA_NUM_{number_index}__"
            if value.count(marker) != 1:
                raise ValueError("Translation lost a protected number")
            value = value.replace(marker, number)
        if not protect_numbers and re.findall(r"\d+(?:[.,]\d+)*", value) != numbers[index]:
            raise ValueError("Translation changed source numbers")
        values[index] = value
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
        if facts.get(field) and FOREIGN_SCRIPT.search(facts[field]):
            targets.append((facts, field, "Anbieter" if field == "merchant" else "Reiseangabe"))
    for item in facts["items"]:
        if not needs_translation(item["description"]):
            continue
        targets.append((item, "description", item.get("category") or "Ausgabe"))
    for field in ("notices",):
        targets.extend(
            (record[field], i, "Beleghinweis" if field == "notices" else "Belegangabe bitte prüfen")
            for i in range(len(record[field]))
            if needs_translation(record[field][i])
        )
    source_groups = {}
    for source in record["sources"]:
        if FOREIGN_SCRIPT.search(source["quote"]):
            source_groups.setdefault(source["quote"], []).append(source)
    for quote, sources in source_groups.items():
        printed_date = re.fullmatch(
            r"\s*(?:开票日期[：:]?\s*)?(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*",
            quote,
        )
        printed_time = re.fullmatch(r"\s*(上午|下午)\s*(\d{1,2}:\d{2})\s*", quote)
        if printed_date:
            sources[0]["translation"] = "Datum: " + "-".join(printed_date.groups())
            continue
        if printed_time:
            period, clock = printed_time.groups()
            sources[0]["translation"] = (
                "Vormittags " if period == "上午" else "Nachmittags "
            ) + clock
            continue
        sources[0]["translation"] = quote
        targets.append((sources[0], "translation", ""))
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

    def assign(owner, key, value):
        if key == "translation" and re.findall(r"\d+(?:[.,]\d+)*", owner["quote"]) != re.findall(
            r"\d+(?:[.,]\d+)*", value
        ):
            raise ValueError("Translation changed source numbers")
        owner[key] = value

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
                assign(owner, key, value)
        except Exception:
            logger.exception("receipt_translation_failed document_id=%s", record["document_id"])
            for owner, key, _ in batch:
                try:
                    value = translate_texts(
                        [owner[key]], settings, [0] if owner is record["notices"] else [], False
                    )[0]
                    assign(owner, key, value)
                except Exception:
                    logger.exception(
                        "receipt_translation_retry_failed document_id=%s", record["document_id"]
                    )
                    failed = True
                    if key == "translation":
                        owner[key] = None
                    # Retain the readable source instead of replacing it with a placeholder.
                    logger.info(
                        "translation_retained_original document_id=%s field=%s",
                        record["document_id"],
                        key,
                    )
        progress()
    for sources in source_groups.values():
        for source in sources[1:]:
            source["translation"] = sources[0].get("translation")
    record["notices"] = [text for text in record["notices"] if text.strip()]
    if failed:
        record["warnings"].append("Übersetzung nicht vollständig. Originaltext im Beleg prüfen.")
