import logging
import time

from tera.chunking import chunk_pages
from tera.config import get_settings
from tera.db import session_factory
from tera.jobs import LostLease, claim_job, update_job
from tera.llm import OllamaExtractor
from tera.models import Document, SummaryJob, now
from tera.prompts import PROMPT_VERSION
from tera.reporting import make_report, merge_fragments

logger = logging.getLogger(__name__)


def process_job(factory, settings, job_id, token, extractor=None):
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
        update_job(factory, settings, job_id, token, total_chunks=total)
        records, completed = [], 0
        for document, chunks in batches:
            fragments, errors = [], []
            for chunk in chunks:
                try:
                    fragments.append(extractor.extract(document.id, chunk))
                except Exception:
                    logger.exception("Extraction failed: job=%s document=%s", job_id, document.id)
                    pages = sorted({p["page"] for p in chunk})
                    errors.append(
                        f"Extraktion fehlgeschlagen, Seiten {pages}. Bitte erneut versuchen."
                    )
                completed += 1
                update_job(factory, settings, job_id, token, completed_chunks=completed)
            records.append(merge_fragments(document, fragments, errors, chunks))
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
            error="Extraction failed for all documents" if status == "failed" else None,
        )
    except LostLease:
        logger.warning("Lease lost: %s", job_id)
    except Exception:
        logger.exception("Job failed: %s", job_id)
        try:
            update_job(
                factory,
                settings,
                job_id,
                token,
                status="failed",
                finished_at=now(),
                error="Generation failed. Check worker logs and create a new job.",
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
