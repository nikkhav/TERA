import unittest
from datetime import timedelta
from unittest.mock import patch

import jwt
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from tera.api import app
from tera.auth import create_access_token, hash_password
from tera.config import get_settings
from tera.db import get_session
from tera.models import Base, User, now
from tera.password_reset import issue_reset, main, recovery_url, token_digest


class PasswordResetTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(self.engine)
        self.factory = sessionmaker(self.engine, expire_on_commit=False)

        def sessions():
            with self.factory() as session:
                yield session

        app.dependency_overrides[get_session] = sessions
        self.client = TestClient(app)
        with self.factory() as session:
            user = User(
                email="person@example.org",
                display_name="Test Person",
                password_hash=hash_password("original-password"),
            )
            other = User(
                email="other@example.org",
                display_name="Other Person",
                password_hash=hash_password("other-password"),
            )
            session.add_all([user, other])
            session.commit()
            self.user_id = user.id
            self.other_id = other.id
            self.access_token = create_access_token(user)
            self.other_token = create_access_token(other)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.clear()
        self.engine.dispose()

    def issue(self):
        with self.factory() as session:
            return issue_reset(session, " PERSON@EXAMPLE.ORG ")

    def reset(self, token, password="replacement-password"):
        return self.client.post("/auth/reset-password", json={"token": token, "password": password})

    def me(self, token):
        return self.client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    def login(self, password):
        return self.client.post(
            "/auth/login", json={"email": "person@example.org", "password": password}
        )

    def test_reset_is_single_use_revokes_sessions_and_allows_new_login(self):
        token = self.issue()
        self.assertEqual(self.me(self.access_token).status_code, 200)
        self.assertEqual(self.login("original-password").status_code, 200)
        response = self.reset(token)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertEqual(self.reset(token).status_code, 400)
        self.assertEqual(self.login("original-password").status_code, 401)
        self.assertEqual(self.me(self.access_token).status_code, 401)
        self.assertEqual(self.me(self.other_token).status_code, 200)
        login = self.login("replacement-password")
        self.assertEqual(login.status_code, 200)
        self.assertEqual(self.me(login.json()["access_token"]).status_code, 200)
        with self.factory() as session:
            user = session.get(User, self.user_id)
            self.assertIsNone(user.reset_token_hash)
            self.assertIsNone(user.reset_expires_at)
            self.assertEqual(user.auth_version, 1)

    def test_tokens_are_hashed_and_new_link_invalidates_previous_link(self):
        old = self.issue()
        token = self.issue()
        self.assertNotEqual(old, token)
        with self.factory() as session:
            user = session.get(User, self.user_id)
            self.assertEqual(user.reset_token_hash, token_digest(token))
            self.assertNotEqual(user.reset_token_hash, token)
        self.assertEqual(self.reset(old).status_code, 400)
        self.assertEqual(self.reset("x" * 43).status_code, 400)
        self.assertEqual(self.reset(token).status_code, 204)

    def test_expired_and_disabled_accounts_cannot_reset(self):
        token = self.issue()
        with self.factory() as session:
            session.get(User, self.user_id).reset_expires_at = now() - timedelta(seconds=1)
            session.commit()
        self.assertEqual(self.reset(token).status_code, 400)
        token = self.issue()
        with self.factory() as session:
            session.get(User, self.user_id).is_active = False
            session.commit()
        self.assertEqual(self.reset(token).status_code, 400)
        with self.factory() as session, self.assertRaises(ValueError):
            issue_reset(session, "person@example.org")

    def test_password_policy_and_invalid_token_do_not_consume_valid_link(self):
        token = self.issue()
        for password in ("short", "x" * 129):
            response = self.reset(token, password)
            self.assertEqual(response.status_code, 422)
            self.assertNotIn(token, response.text)
            self.assertNotIn(password, response.text)
        self.assertEqual(self.reset("short-token").status_code, 422)
        self.assertEqual(self.reset(token).status_code, 204)

    def test_legacy_access_tokens_are_revoked_by_reset(self):
        payload = jwt.decode(
            self.access_token, get_settings().auth_secret_key, algorithms=["HS256"]
        )
        payload.pop("ver")
        legacy = jwt.encode(payload, get_settings().auth_secret_key, algorithm="HS256")
        self.assertEqual(self.me(legacy).status_code, 200)
        token = self.issue()
        # A reset token is never a login credential.
        self.assertEqual(self.me(token).status_code, 401)
        self.assertEqual(self.reset(token).status_code, 204)
        self.assertEqual(self.me(legacy).status_code, 401)

    def test_registration_disabled_does_not_block_recovery(self):
        token = self.issue()
        with patch.object(get_settings(), "auth_allow_registration", False):
            self.assertEqual(self.reset(token).status_code, 204)

    def test_cli_outputs_link_only_for_existing_active_account(self):
        args = [
            "tera.password_reset",
            "person@example.org",
            "--base-url",
            "https://tera.example.org",
        ]
        with (
            patch("sys.argv", args),
            patch("tera.password_reset.session_factory", return_value=self.factory),
            patch("builtins.print") as output,
        ):
            main()
        link = output.call_args_list[1].args[0]
        self.assertTrue(link.startswith("https://tera.example.org/reset-password#token="))
        self.assertEqual(self.reset(link.split("#token=")[1]).status_code, 204)
        with self.factory() as session, self.assertRaises(ValueError):
            issue_reset(session, "missing@example.org")

    def test_only_trusted_explicit_urls_and_bounded_lifetimes(self):
        self.assertEqual(
            recovery_url("http://localhost:3000/", "token"),
            "http://localhost:3000/reset-password#token=token",
        )
        for url in (
            "http://example.org",
            "javascript:alert(1)",
            "https://example.org/?x=1",
            "https://example.org/#x",
            "https://user:pass@example.org",
        ):
            with self.assertRaises(ValueError):
                recovery_url(url, "token")
        with self.factory() as session:
            for minutes in (0, 1441):
                with self.assertRaises(ValueError):
                    issue_reset(session, "person@example.org", minutes)
            self.assertIsNone(
                session.scalar(select(User.reset_token_hash).where(User.id == self.user_id))
            )


if __name__ == "__main__":
    unittest.main()
