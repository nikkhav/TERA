"""Extract a document and perform one bounded correction pass when needed."""

import logging
import time

from tera.llm import NonRetryableExtractionError
from tera.prompts import RECHECK_PROMPT, RECHECK_RESERVE
from tera.reporting import merge_fragments

logger = logging.getLogger(__name__)


def correction_feedback(issues):
    limit = RECHECK_RESERVE - len(RECHECK_PROMPT.encode()) - 2
    lines = []
    for issue in issues:
        fields = ", ".join(issue.get("fields", []))
        line = (
            f"{issue['code']}: {fields or 'verify all monetary quotations and uncertain readings'}"
        )
        candidate = "\n".join(lines + [line])
        if len(candidate.encode()) <= limit:
            lines.append(line)
    return "\n".join(lines) or "Recheck missing facts and their exact evidence."


def process_document(document, chunks, extractor, settings, progress, job_id=None):
    fragments, errors, non_retryable = {}, {}, set()

    def extract(index, feedback=None):
        pages = sorted({page["page"] for page in chunks[index]})
        started = time.monotonic()
        logger.info(
            "extraction_started job_id=%s document_id=%s filename=%s chunk=%s pages=%s correction=%s",
            job_id,
            document.id,
            document.filename,
            index + 1,
            pages,
            feedback is not None,
        )
        try:
            if feedback is None:
                value = extractor.extract(document.id, chunks[index])
            else:
                value = extractor.extract(document.id, chunks[index], feedback=feedback)
            fragments[index] = value
            errors.pop(index, None)
            logger.info(
                "extraction_finished job_id=%s document_id=%s chunk=%s correction=%s "
                "duration_seconds=%.2f",
                job_id,
                document.id,
                index + 1,
                feedback is not None,
                time.monotonic() - started,
            )
        except NonRetryableExtractionError:
            non_retryable.add(index)
            logger.exception(
                "extraction_stopped job_id=%s document_id=%s chunk=%s pages=%s "
                "duration_seconds=%.2f",
                job_id,
                document.id,
                index + 1,
                pages,
                time.monotonic() - started,
            )
            errors[index] = f"Extraktion fehlgeschlagen, Seiten {pages}. Bitte erneut versuchen."
        except Exception:
            logger.exception(
                "extraction_failed job_id=%s document_id=%s chunk=%s pages=%s "
                "duration_seconds=%.2f",
                job_id,
                document.id,
                index + 1,
                pages,
                time.monotonic() - started,
            )
            errors[index] = f"Extraktion fehlgeschlagen, Seiten {pages}. Bitte erneut versuchen."
        progress(completed=1)

    for index in range(len(chunks)):
        extract(index)
    record = merge_fragments(document, list(fragments.values()), list(errors.values()), chunks)
    if not settings.receipt_recheck_enabled or not record["validation_issues"]:
        return record

    initial = record["validation_issues"]
    # Arithmetic involving multiple parts needs all implicated source pages.
    affected = {page for issue in initial for page in issue["pages"]}
    indexes = [
        index
        for index, chunk in enumerate(chunks)
        if index not in non_retryable
        and (index in errors or not affected or any(p["page"] in affected for p in chunk))
    ]
    if not indexes:
        return record
    progress(added=len(indexes))
    for index in indexes:
        pages = {p["page"] for p in chunks[index]}
        relevant = [i for i in initial if not i["pages"] or pages.intersection(i["pages"])]
        extract(index, correction_feedback(relevant))
    record = merge_fragments(document, list(fragments.values()), list(errors.values()), chunks)
    record["recheck_attempted"] = True
    record["initial_issues"] = initial
    record["extraction_failed"] = len(fragments) < len(chunks)
    return record
