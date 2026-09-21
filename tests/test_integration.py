"""Opt-in tests against the local Compose Postgres and S3 services."""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from tera.api import app
from tera.config import Settings
from tera.db import get_session
from tera.jobs import claim_job
from tera.models import Base
from tera.schemas import ReceiptFacts
from tera.storage import ObjectStore, get_store
from tera.worker import process_job

pytestmark = pytest.mark.skipif(
    os.environ.get("TERA_INTEGRATION") != "1",
    reason="Set TERA_INTEGRATION=1 after starting Compose",
)


def test_postgres_s3_pipeline():
    settings = Settings()
    suffix = uuid4().hex
    schema = f"tera_test_{suffix}"
    settings.s3_bucket = f"tera-test-{suffix}"
    admin = create_engine(settings.database_url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(
        settings.database_url, connect_args={"options": f"-csearch_path={schema}"}
    )
    factory = sessionmaker(engine, expire_on_commit=False)
    store = ObjectStore(settings)
    store.ensure_bucket()
    Base.metadata.create_all(engine)

    def sessions():
        with factory() as session:
            yield session

    class Extractor:
        def extract(self, *_):
            return ReceiptFacts(
                merchant="NORTHSTAR HOTEL BERLIN",
                invoice_number="NSB-2026-0914-1042",
                invoice_date="2026-09-14",
                category="Hotel",
                currency="EUR",
                total="712.60",
                breakfast_total="71.40",
                evidence=[{"page": 1, "quote": "NORTHSTAR HOTEL BERLIN"}],
            )

    app.dependency_overrides[get_session] = sessions
    app.dependency_overrides[get_store] = lambda: store
    try:
        with TestClient(app) as client:
            assert client.get("/ready").status_code == 200
            employee = client.post("/employees", json={"name": "Integration test"}).json()
            trip = client.post(
                f"/employees/{employee['id']}/trips", json={"name": "Test trip"}
            ).json()
            pdf = (
                Path(__file__).resolve().parents[1] / "research/data/hotel_invoice.pdf"
            ).read_bytes()
            response = client.post(
                f"/trips/{trip['id']}/documents", files={"file": ("hotel.pdf", pdf)}
            )
            assert response.status_code == 201, response.text
            assert client.get(f"/documents/{response.json()['id']}/download").content == pdf
            job = client.post(f"/trips/{trip['id']}/summaries").json()
            # Postgres SKIP LOCKED must give this job to only one worker.
            with ThreadPoolExecutor(max_workers=2) as pool:
                claims = list(pool.map(lambda _: claim_job(factory, settings), range(2)))
            claim = [c for c in claims if c is not None]
            assert len(claim) == 1
            process_job(factory, settings, *claim[0], extractor=Extractor())
            result = client.get(f"/summary-jobs/{job['id']}/result")
            assert result.status_code == 200, result.text
            assert result.json()["status"] == "completed"
            assert result.json()["totals"]["by_currency"][0]["confirmed"] == "712.60"
    finally:
        app.dependency_overrides.clear()
        objects = store.client.list_objects_v2(Bucket=store.bucket).get("Contents", [])
        for obj in objects:
            store.delete(obj["Key"])
        store.client.delete_bucket(Bucket=store.bucket)
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
