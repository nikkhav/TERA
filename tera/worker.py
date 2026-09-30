import logging
import time

from tera.chunking import chunk_pages
from tera.config import get_settings
from tera.db import session_factory
from tera.exchange_rates import attach_rate
from tera.jobs import LostLease, claim_job, update_job
from tera.llm import OllamaExtractor
from tera.localization import localize_record
from tera.models import Document, SummaryJob, now
from tera.processing import process_document
from tera.prompts import PROMPT_VERSION
from tera.reporting import make_report

logger = logging.getLogger(__name__)


def process_job(factory, settings, job_id, token, extractor=None):
    started = time.monotonic()
    try:
        with factory() as session:
            job = session.get(SummaryJob, job_id)
            if job.prompt_version != PROMPT_VERSION:
                raise ValueError("Prompt changed since queueing; create a new summary job")
            model, prompt_version = job.model, job.prompt_version
            documents = [session.get(Document, document_id) for document_id in job.document_ids]
            if any(document is None for document in documents):
                raise ValueError("A document from the job snapshot is missing")
        extractor = extractor or OllamaExtractor(settings)
        batches = [(doc, chunk_pages(doc.id, doc.pages, settings)) for doc in documents]
        total = sum(len(chunks) for _, chunks in batches)
        logger.info(
            "job_started job_id=%s trip_id=%s documents=%s chunks=%s model=%s",
            job_id,
            job.trip_id,
            len(documents),
            total,
            model,
        )
        update_job(factory, settings, job_id, token, total_chunks=total)
        records, completed_count = [], 0

        def progress(completed=0, added=0):
            nonlocal total, completed_count
            total += added
            completed_count += completed
            update_job(
                factory,
                settings,
                job_id,
                token,
                completed_chunks=completed_count,
                total_chunks=total,
            )

        for document, chunks in batches:
            records.append(
                process_document(document, chunks, extractor, settings, progress, job_id=job_id)
            )
        if isinstance(extractor, OllamaExtractor):
            progress(added=len(records))
        for record in records:
            if isinstance(extractor, OllamaExtractor):
                localize_record(record, settings, progress)
            attach_rate(record)
            progress(completed=1 if isinstance(extractor, OllamaExtractor) else 0)
        report = make_report(records, model, prompt_version)
        status = "needs_review" if report["coverage"]["needs_review"] else "completed"
        if report["coverage"]["failed"] == report["coverage"]["supplied"]:
            status = "failed"
        update_job(
            factory,
            settings,
            job_id,
            token,
            status=status,
            result=report,
            finished_at=now(),
            error="Alle Dokumente konnten nicht verarbeitet werden."
            if status == "failed"
            else None,
        )
        logger.info(
            "job_finished job_id=%s status=%s duration_seconds=%.2f supplied=%s processed=%s "
            "needs_review=%s",
            job_id,
            status,
            time.monotonic() - started,
            report["coverage"]["supplied"],
            report["coverage"]["processed"],
            report["coverage"]["needs_review"],
        )
    except LostLease:
        logger.warning("Lease lost: %s", job_id)
    except Exception:
        logger.exception(
            "job_failed job_id=%s duration_seconds=%.2f", job_id, time.monotonic() - started
        )
        try:
            update_job(
                factory,
                settings,
                job_id,
                token,
                status="failed",
                finished_at=now(),
                error="Die Auswertung ist fehlgeschlagen. Bitte erneut versuchen.",
            )
        except LostLease:
            pass


def main():
    logging.basicConfig(level=logging.INFO)
    settings, factory = get_settings(), session_factory()
    logger.info("Worker ready; model=%s", settings.ollama_model)
    while True:
        try:
            claim = claim_job(factory, settings)
            if claim:
                process_job(factory, settings, *claim)
            else:
                time.sleep(settings.worker_poll_seconds)
        except KeyboardInterrupt:
            break
        except Exception:
            logger.exception("Worker queue unavailable; retrying")
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()
