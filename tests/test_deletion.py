import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from tera.api import app
from tera.auth import get_current_user
from tera.db import get_session
from tera.models import Base, Document, Employee, SummaryJob, Trip
from tera.storage import StorageError, get_store


class MemoryStore:
    def __init__(self):
        self.objects = {}
        self.fail_delete = False

    def read(self, key):
        return self.objects[key]

    def put(self, key, data):
        self.objects[key] = data

    def delete(self, key):
        self.objects.pop(key)
        if self.fail_delete:
            raise StorageError("Simulated storage failure")


class DeletionTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )

        @event.listens_for(self.engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(self.engine)
        self.store = MemoryStore()

        def session_dependency():
            with Session(self.engine) as session:
                yield session

        app.dependency_overrides[get_session] = session_dependency
        app.dependency_overrides[get_store] = lambda: self.store
        app.dependency_overrides[get_current_user] = lambda: object()
        self.client = TestClient(app)
        with Session(self.engine) as session:
            employee = Employee(name="Test Person")
            session.add(employee)
            session.flush()
            self.employee_id = employee.id
            self.trip_ids = []
            for index in range(2):
                trip = Trip(employee_id=employee.id, name=f"Trip {index}")
                session.add(trip)
                session.flush()
                self.trip_ids.append(trip.id)
                document = Document(
                    trip_id=trip.id, filename="receipt.pdf", object_key=f"{index}.pdf",
                    sha256=str(index) * 64, size_bytes=3, page_count=1, pages=[],
                )
                session.add(document)
                session.flush()
                session.add(SummaryJob(
                    trip_id=trip.id, status="completed", document_ids=[document.id],
                    model="test", prompt_version="test", result={"documents": []},
                ))
                self.store.put(document.object_key, b"pdf")
            session.commit()

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def counts(self):
        with Session(self.engine) as session:
            return [session.scalar(select(func.count()).select_from(model))
                    for model in (Employee, Trip, Document, SummaryJob)]

    def test_trip_removes_children_but_preserves_other_trip(self):
        response = self.client.delete(f"/trips/{self.trip_ids[0]}")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.counts(), [1, 1, 1, 1])
        self.assertEqual(self.store.objects, {"1.pdf": b"pdf"})
        self.assertEqual(self.client.delete(f"/trips/{self.trip_ids[0]}").status_code, 404)

    def test_employee_removes_all_children(self):
        response = self.client.delete(f"/employees/{self.employee_id}")
        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.counts(), [0, 0, 0, 0])
        self.assertEqual(self.store.objects, {})

    def test_active_job_blocks_employee_and_trip_deletion(self):
        for status in ("queued", "running"):
            with Session(self.engine) as session:
                job = session.scalar(select(SummaryJob).where(
                    SummaryJob.trip_id == self.trip_ids[1]
                ))
                job.status = status
                session.commit()
            for path in (f"/employees/{self.employee_id}", f"/trips/{self.trip_ids[1]}"):
                self.assertEqual(self.client.delete(path).status_code, 409)
                self.assertEqual(self.counts(), [1, 2, 2, 2])
                self.assertEqual(len(self.store.objects), 2)

    def test_storage_failure_restores_database_and_files(self):
        self.store.fail_delete = True
        self.assertEqual(self.client.delete(f"/employees/{self.employee_id}").status_code, 503)
        self.assertEqual(self.counts(), [1, 2, 2, 2])
        self.assertEqual(self.store.objects, {"0.pdf": b"pdf", "1.pdf": b"pdf"})

    def test_missing_employee_and_empty_employee(self):
        self.assertEqual(self.client.delete(f"/employees/{uuid4()}").status_code, 404)
        with Session(self.engine) as session:
            employee = Employee(name="Empty")
            session.add(employee)
            session.commit()
            employee_id = employee.id
        self.assertEqual(self.client.delete(f"/employees/{employee_id}").status_code, 204)
        self.assertEqual(self.counts(), [1, 2, 2, 2])

    def test_authentication_required(self):
        del app.dependency_overrides[get_current_user]
        self.assertEqual(self.client.delete(f"/employees/{self.employee_id}").status_code, 401)
        self.assertEqual(self.client.delete(f"/trips/{self.trip_ids[0]}").status_code, 401)
        self.assertEqual(self.counts(), [1, 2, 2, 2])


if __name__ == "__main__":
    unittest.main()
