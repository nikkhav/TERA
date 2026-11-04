import unittest
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from test_deletion import MemoryStore

from tera.api import app
from tera.auth import create_access_token
from tera.db import get_session
from tera.models import Base, Document, Employee, SummaryJob, Trip, User
from tera.reporting import make_report, merge_fragments
from tera.schemas import ReceiptFacts
from tera.storage import get_store


class AccountIsolationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(self.engine, expire_on_commit=False)
        self.store = MemoryStore()

        def sessions():
            with self.factory() as session:
                yield session

        app.dependency_overrides[get_session] = sessions
        app.dependency_overrides[get_store] = lambda: self.store
        self.client = TestClient(app)
        self.headers = []
        self.resources = []
        with self.factory() as session:
            for index in range(2):
                user = User(
                    email=f"owner{index}@example.org",
                    display_name=f"Owner {index}",
                    password_hash="unused",
                )
                session.add(user)
                session.flush()
                self.headers.append({"Authorization": f"Bearer {create_access_token(user)}"})
                employee = Employee(name=f"Employee {index}", user_id=user.id)
                session.add(employee)
                session.flush()
                trip = Trip(name="Trip", employee_id=employee.id)
                session.add(trip)
                session.flush()
                document = Document(
                    trip_id=trip.id,
                    filename="receipt.pdf",
                    object_key=f"{index}.pdf",
                    sha256=str(index) * 64,
                    size_bytes=3,
                    page_count=1,
                    pages=[],
                )
                session.add(document)
                session.flush()
                record = merge_fragments(
                    document,
                    [
                        ReceiptFacts(
                            category="Transport",
                            document_kind="receipt",
                            total="10",
                            currency="EUR",
                        )
                    ],
                    [],
                    [[{"page": 1, "text": ""}]],
                )
                job = SummaryJob(
                    trip_id=trip.id,
                    document_ids=[document.id],
                    status="completed",
                    model="test",
                    prompt_version="test",
                    result=make_report([record], "test", "test", tokens_used=123),
                )
                session.add(job)
                session.flush()
                self.resources.append((employee.id, trip.id, document.id, job.id))
                self.store.put(document.object_key, b"pdf")
            unassigned = Employee(name="Legacy")
            session.add(unassigned)
            session.flush()
            self.unassigned_id = unassigned.id
            session.commit()

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_lists_and_creation_are_scoped_to_authenticated_account(self):
        for index, headers in enumerate(self.headers):
            response = self.client.get("/employees", headers=headers)
            self.assertEqual([item["id"] for item in response.json()], [self.resources[index][0]])
            # A supplied owner field cannot change the server-selected owner.
            response = self.client.post(
                "/employees",
                headers=headers,
                json={"name": "New", "user_id": str(uuid4())},
            )
            self.assertEqual(response.status_code, 201, response.text)
            new_id = response.json()["id"]
            with self.factory() as session:
                owner = session.scalar(
                    select(User).where(User.email == f"owner{index}@example.org")
                )
                self.assertEqual(session.get(Employee, new_id).user_id, owner.id)
            other_headers = self.headers[1 - index]
            self.assertEqual(
                self.client.get(f"/employees/{new_id}", headers=other_headers).status_code, 404
            )

    def test_foreign_resources_are_inaccessible_on_every_route(self):
        for owner_index, (employee, trip, document, job) in enumerate(self.resources):
            headers = self.headers[1 - owner_index]
            requests = [
                ("GET", f"/employees/{employee}", {}),
                ("DELETE", f"/employees/{employee}", {}),
                ("GET", f"/employees/{employee}/trips", {}),
                ("POST", f"/employees/{employee}/trips", {"json": {"name": "Foreign"}}),
                ("GET", f"/trips/{trip}", {}),
                ("PUT", f"/trips/{trip}", {"json": {"name": "Foreign"}}),
                ("DELETE", f"/trips/{trip}", {}),
                ("GET", f"/trips/{trip}/documents", {}),
                (
                    "POST",
                    f"/trips/{trip}/documents",
                    {"files": {"file": ("foreign.pdf", b"pdf", "application/pdf")}},
                ),
                ("DELETE", f"/documents/{document}", {}),
                ("GET", f"/documents/{document}/download", {}),
                ("GET", f"/documents/{document}/download?inline=true", {}),
                ("POST", f"/trips/{trip}/summaries", {}),
                ("GET", f"/trips/{trip}/summaries", {}),
                ("GET", f"/summary-jobs/{job}", {}),
                ("GET", f"/summary-jobs/{job}/result", {}),
                (
                    "PUT",
                    f"/summary-jobs/{job}/documents/{document}/review",
                    {"json": {"decision": "rejected"}},
                ),
                (
                    "PUT",
                    f"/summary-jobs/{job}/documents/{document}/correction",
                    {"json": {"facts": {}}},
                ),
                (
                    "PUT",
                    f"/summary-jobs/{job}/relationships",
                    {"json": {"document_ids": [document, str(uuid4())], "resolution": "separate"}},
                ),
            ]
            for method, path, kwargs in requests:
                with self.subTest(method=method, path=path):
                    response = self.client.request(method, path, headers=headers, **kwargs)
                    self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(len(self.store.objects), 2)

    def test_owner_can_read_update_review_and_delete(self):
        employee, trip, document, job = self.resources[0]
        headers = self.headers[0]
        for path in (
            f"/employees/{employee}",
            f"/employees/{employee}/trips",
            f"/trips/{trip}",
            f"/trips/{trip}/documents",
            f"/trips/{trip}/summaries",
            f"/documents/{document}/download",
            f"/summary-jobs/{job}",
            f"/summary-jobs/{job}/result",
        ):
            self.assertEqual(self.client.get(path, headers=headers).status_code, 200, path)
        response = self.client.put(f"/trips/{trip}", headers=headers, json={"name": "Updated"})
        self.assertEqual(response.status_code, 200)
        response = self.client.put(
            f"/summary-jobs/{job}/documents/{document}/review",
            headers=headers,
            json={"decision": "approved"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["tokens_used"], 123)
        response = self.client.delete(f"/employees/{employee}", headers=headers)
        self.assertEqual(response.status_code, 204, response.text)
        self.assertEqual(len(self.store.objects), 1)

    def test_unassigned_legacy_data_is_hidden_from_all_accounts(self):
        for headers in self.headers:
            self.assertEqual(
                self.client.get(f"/employees/{self.unassigned_id}", headers=headers).status_code,
                404,
            )
        # An administrator can explicitly restore access after verifying ownership.
        with self.factory() as session:
            owner = session.scalar(select(User).where(User.email == "owner0@example.org"))
            session.get(Employee, self.unassigned_id).user_id = owner.id
            session.commit()
        self.assertEqual(
            self.client.get(
                f"/employees/{self.unassigned_id}", headers=self.headers[0]
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(
                f"/employees/{self.unassigned_id}", headers=self.headers[1]
            ).status_code,
            404,
        )
