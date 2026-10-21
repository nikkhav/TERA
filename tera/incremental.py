"""Snapshot compatible document results when an updated report is queued."""

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from sqlalchemy import select

from tera.models import SummaryJob
from tera.prompts import PROMPT_VERSION


def processing_configuration(settings):
    return {
        name: getattr(settings, name)
        for name in (
            "ollama_url",
            "ollama_model",
            "ollama_think",
            "model_context_tokens",
            "model_output_tokens",
            "receipt_recheck_enabled",
        )
    }


def processing_fingerprint(settings):
    digest = hashlib.sha256(json.dumps(processing_configuration(settings), sort_keys=True).encode())
    # Invalidate cached results when processing, validation or translation code changes.
    for name in (
        "chunking",
        "pdf",
        "processing",
        "prompts",
        "llm",
        "schemas",
        "reconciliation",
        "reporting",
        "localization",
        "note_review",
        "exchange_rates",
        "currency_exchange",
        "labels",
        "corrections",
        "incremental",
        "transport",
        "document_links",
        "relationships",
    ):
        digest.update(Path(__file__).with_name(f"{name}.py").read_bytes())
    return digest.hexdigest()


def snapshot_inputs(session, trip_id, documents, settings, force=False):
    fingerprint = processing_fingerprint(settings)
    snapshot = {
        "fingerprint": fingerprint,
        "configuration": processing_configuration(settings),
        "hashes": {doc.id: doc.sha256 for doc in documents},
        "records": [],
    }
    if force:
        return snapshot
    previous = session.scalar(
        select(SummaryJob)
        .where(SummaryJob.trip_id == str(trip_id), SummaryJob.result.is_not(None))
        .order_by(SummaryJob.created_at.desc(), SummaryJob.id.desc())
        .limit(1)
    )
    if (
        previous is None
        or previous.model != settings.ollama_model
        or previous.prompt_version != PROMPT_VERSION
        or not previous.processing_snapshot
        or previous.processing_snapshot.get("fingerprint") != fingerprint
    ):
        return snapshot
    hashes = previous.processing_snapshot.get("hashes", {})
    snapshot["records"] = [
        deepcopy(record)
        for record in previous.result["documents"]
        if record["document_id"] in snapshot["hashes"]
        and hashes.get(record["document_id"]) == snapshot["hashes"][record["document_id"]]
        and not record.get("extraction_failed")
    ]
    return snapshot
