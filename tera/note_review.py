"""Review model-written observations before deterministic validation adds its findings."""

import json
import logging
import re
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from tera.prompts import NOTE_REVIEW_PROMPT

logger = logging.getLogger(__name__)


class NoteDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index: int = Field(ge=0)
    kind: Literal["information", "potential_problem"]
    text: str = Field(min_length=1, max_length=1000)
    problem: str | None = Field(max_length=1000)


class NoteDecisions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decisions: list[NoteDecision]


def review_notes(notes, settings):
    if not notes:
        return []
    protected, numbers = [], []
    for index, text in enumerate(notes):
        values = []

        def protect(match, values=values, index=index):
            values.append(match.group())
            return f"__NOTE_{index}_NUM_{len(values) - 1}__"

        protected.append(re.sub(r"[-+]?\d+(?:[.,]\d+)*", protect, text))
        numbers.append(values)
    payload = {
        "model": settings.ollama_model,
        "prompt": NOTE_REVIEW_PROMPT
        + json.dumps(
            [{"index": i, "text": text} for i, text in enumerate(protected)], ensure_ascii=False
        ),
        "format": NoteDecisions.model_json_schema(),
        "stream": False,
        "options": {
            "temperature": 0,
            "num_ctx": settings.model_context_tokens,
            "num_predict": min(settings.model_output_tokens, 2048),
        },
    }
    if settings.ollama_think is not None:
        payload["think"] = settings.ollama_think
    with httpx.Client(timeout=settings.model_timeout_seconds) as client:
        response = client.post(settings.ollama_url.rstrip("/") + "/api/generate", json=payload)
        response.raise_for_status()
        data = response.json()
    if not data.get("done") or data.get("done_reason") == "length":
        raise ValueError("Incomplete note review")
    decisions = NoteDecisions.model_validate_json(data["response"]).decisions
    if sorted(d.index for d in decisions) != list(range(len(notes))):
        raise ValueError("Note review did not cover each observation exactly once")
    decisions.sort(key=lambda d: d.index)
    for decision, original in zip(decisions, notes, strict=True):
        for number_index, number in enumerate(numbers[decision.index]):
            marker = f"__NOTE_{decision.index}_NUM_{number_index}__"
            if decision.text.count(marker) != 1:
                raise ValueError("Note review lost a protected number")
            decision.text = decision.text.replace(marker, number)
            if decision.problem:
                decision.problem = decision.problem.replace(marker, number)
        if not decision.text.strip() or re.findall(r"[-+]?\d+(?:[.,]\d+)*", original) != re.findall(
            r"[-+]?\d+(?:[.,]\d+)*", decision.text
        ):
            raise ValueError("Note review changed printed numbers or removed text")
        if decision.kind == "potential_problem" and not (decision.problem or "").strip():
            raise ValueError("Potential problem lacks an explanation")
        if decision.kind == "information" and (decision.problem or "").strip():
            raise ValueError("Informational observation still alleges a problem")
    return decisions


def review_model_notes(facts, settings):
    """Only raw model observations are eligible; Python findings do not enter this pass."""
    if not facts.notes:
        return facts
    originals = list(facts.notes)
    try:
        decisions = review_notes(originals, settings)
    except Exception:
        logger.exception("model_note_review_failed; retaining original observations")
        return facts
    facts.notes = [d.text for d in decisions if d.kind == "potential_problem"]
    facts.notices.extend(d.text for d in decisions if d.kind == "information")
    return facts
