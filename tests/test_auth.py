from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tera.api import app
from tera.db import get_session
from tera.models import Base


def test_registration_login_and_protected_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)

    def sessions():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = sessions
    try:
        with TestClient(app) as client:
            assert client.get("/employees").status_code == 401
            registration = client.post(
                "/auth/register",
                json={
                    "email": " Person@Example.com ",
                    "display_name": "Person",
                    "password": "correct horse battery staple",
                },
            )
            assert registration.status_code == 201, registration.text
            assert registration.json()["user"]["email"] == "person@example.com"
            assert (
                client.post(
                    "/auth/register",
                    json={
                        "email": "person@example.com",
                        "display_name": "Duplicate",
                        "password": "correct horse battery staple",
                    },
                ).status_code
                == 409
            )
            assert (
                client.post(
                    "/auth/login",
                    json={"email": "person@example.com", "password": "wrong password"},
                ).status_code
                == 401
            )
            login = client.post(
                "/auth/login",
                json={
                    "email": "person@example.com",
                    "password": "correct horse battery staple",
                },
            )
            token = login.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            assert client.get("/auth/me", headers=headers).json()["display_name"] == "Person"
            assert client.get("/employees", headers=headers).status_code == 200
            assert (
                client.get("/employees", headers={"Authorization": "Bearer broken"}).status_code
                == 401
            )
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
