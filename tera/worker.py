import logging
import time

from tera.chunking import ContextBudgetError, chunk_pages
from tera.config import Settings, get_settings
from tera.db import session_factory
from tera.exchange_rates import attach_rate
from tera.incremental import processing_fingerprint
from tera.jobs import LostLease, claim_job, update_job
from tera.llm import OllamaExtractor
from tera.localization import localize_record
from tera.models import Document, SummaryJob, now
from tera.pdf import extract_pages
from tera.processing import process_document
from tera.prompts import PROMPT_VERSION
from tera.reporting import make_report
from tera.storage import LocalObjectStore, ObjectStore

logger = logging.getLogger(__name__)


class JobConfigurationError(ValueError):
    """A safe, actionable job setup error that can be shown in the UI."""


def settings_for_job(settings, job):
    configuration = (job.processing_snapshot or {}).get("configuration", {})
    # The queue records what was requested; worker defaults may change before pickup.
    configuration = {**configuration, "ollama_model": job.model}
    return Settings.model_validate({**settings.model_dump(), **configuration})


def process_job(factory, settings, job_id, token, extractor=None, store=None):
    started = time.monotonic()
    try:
        with factory() as session:
            job = session.get(SummaryJob, job_id)
            if job.prompt_version != PROMPT_VERSION:
                raise JobConfigurationError(
                    "API und Worker verwenden unterschiedliche Anweisungen. Beide Dienste "
                    "mit demselben Code neu erstellen und eine neue Auswertung starten."
                )
            settings = settings_for_job(settings, job)
            model, prompt_version = job.model, job.prompt_version
            documents = [session.get(Document, document_id) for document_id in job.document_ids]
            if any(document is None for document in documents):
                raise JobConfigurationError(
                    "Ein Dokument dieser Auswertung ist nicht mehr vorhanden. "
                    "Eine neue Auswertung mit den aktuellen Dokumenten starten."
                )
            snapshot = job.processing_snapshot
            if snapshot and snapshot["fingerprint"] != processing_fingerprint(settings):
                raise JobConfigurationError(
                    "Verarbeitungsversion oder Einstellungen von API und Worker stimmen "
                    "nicht mit dem Auftrag überein. Beide Dienste mit demselben Code "
                    "neu erstellen und eine neue Auswertung starten."
                )
            records = (snapshot or {}).get("records", [])
            reused_ids = {record["document_id"] for record in records}
            if snapshot and any(snapshot["hashes"].get(doc.id) != doc.sha256 for doc in documents):
                raise JobConfigurationError(
                    "Ein Dokument wurde seit dem Start geändert. Eine neue Auswertung starten."
                )
            documents = [doc for doc in documents if doc.id not in reused_ids]
        extractor = extractor or OllamaExtractor(settings)
        layout_errors = {}
        for document in documents:
            if all(page.get("layout_version") == 2 for page in document.pages):
                continue
            try:
                store = store or (
                    LocalObjectStore(settings)
                    if settings.storage_backend == "local"
                    else ObjectStore(settings)
                )
                document.pages = extract_pages(store.read(document.object_key), settings)
            except Exception:
                logger.exception("layout_refresh_failed document_id=%s", document.id)
                layout_errors[document.id] = (
                    "PDF-Text konnte nicht aktualisiert werden; gespeicherten Text bitte prüfen."
                )
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
        completed_count = 0
        rate_cache = {}

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

        if isinstance(extractor, OllamaExtractor):
            extractor.heartbeat = progress
            progress(added=len(batches))
        for document, chunks in batches:
            record = process_document(
                document, chunks, extractor, settings, progress, job_id=job_id
            )
            if document.id in layout_errors:
                record["warnings"].append(layout_errors[document.id])
            if isinstance(extractor, OllamaExtractor):
                localize_record(record, settings, progress)
            attach_rate(record, rate_cache)
            records.append(record)
            progress(completed=1 if isinstance(extractor, OllamaExtractor) else 0)
            update_job(factory, settings, job_id, token, completed_documents=len(records))
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
    except Exception as exc:
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
                error=str(exc)
                if isinstance(exc, (JobConfigurationError, ContextBudgetError))
                else "Die Auswertung ist fehlgeschlagen. Bitte erneut versuchen.",
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
