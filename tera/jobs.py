from datetime import timedelta

from sqlalchemy import and_, or_, select, update

from tera.models import SummaryJob, new_id, now


class LostLease(RuntimeError):
    pass


def claim_job(factory, settings):
    """Postgres row locks let multiple workers safely claim different jobs."""
    with factory.begin() as session:
        job = session.scalar(
            select(SummaryJob)
            .where(
                or_(
                    SummaryJob.status == "queued",
                    and_(SummaryJob.status == "running", SummaryJob.lease_until < now()),
                )
            )
            .order_by(SummaryJob.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None
        if job.attempts >= 3:
            job.status, job.error, job.finished_at = "failed", "Worker stopped repeatedly", now()
            job.lease_token, job.lease_until = None, None
            return None
        job.status, job.lease_token = "running", new_id()
        job.model = settings.ollama_model
        job.lease_until = now() + timedelta(seconds=settings.job_lease_seconds)
        job.attempts += 1
        job.completed_chunks, job.total_chunks = 0, 0
        job.error, job.result = None, None
        session.flush()
        return job.id, job.lease_token


def update_job(factory, settings, job_id, token, **values):
    with factory.begin() as session:
        result = session.execute(
            update(SummaryJob)
            .where(
                SummaryJob.id == job_id,
                SummaryJob.lease_token == token,
                SummaryJob.status == "running",
            )
            .values(lease_until=now() + timedelta(seconds=settings.job_lease_seconds), **values)
        )
        if result.rowcount != 1:
            raise LostLease("Another worker owns this job")
