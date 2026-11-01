"""Issue recovery links through server access; redeem them once through the API."""

import argparse
import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from sqlalchemy import select, update

from tera.auth import hash_password
from tera.db import session_factory
from tera.models import User, now


def token_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def issue_reset(session, email, minutes=30):
    if not 5 <= minutes <= 1440:
        raise ValueError("Link lifetime must be between 5 and 1440 minutes.")
    user = session.scalar(
        select(User).where(User.email == email.strip().casefold()).with_for_update()
    )
    if user is None or not user.is_active:
        raise ValueError("Active user not found.")
    token = secrets.token_urlsafe(32)
    user.reset_token_hash = token_digest(token)
    user.reset_expires_at = now() + timedelta(minutes=minutes)
    session.commit()
    return token


def redeem_reset(session, token, password):
    # One conditional UPDATE makes redemption single-use even for concurrent requests.
    # Check the token before spending time hashing a password for an invalid request.
    digest = token_digest(token)
    eligible = (
        User.reset_token_hash == digest,
        User.reset_expires_at > now(),
        User.is_active.is_(True),
    )
    if session.scalar(select(User.id).where(*eligible)) is None:
        return False
    encoded = hash_password(password)
    result = session.execute(
        update(User)
        .where(
            User.reset_token_hash == digest,
            User.reset_expires_at > now(),
            User.is_active.is_(True),
        )
        .values(
            password_hash=encoded,
            auth_version=User.auth_version + 1,
            reset_token_hash=None,
            reset_expires_at=None,
        )
    )
    session.commit()
    return result.rowcount == 1


def recovery_url(base_url, token):
    parts = urlsplit(base_url)
    local = parts.hostname in {"localhost", "127.0.0.1", "::1"}
    if (
        not parts.netloc
        or not (parts.scheme == "https" or (parts.scheme == "http" and local))
        or parts.username is not None
        or parts.password is not None
        or parts.query
        or parts.fragment
    ):
        raise ValueError("Use the application's HTTPS base URL (HTTP only for localhost).")
    # Fragments are not sent to the web server or its access logs.
    return f"{base_url.rstrip('/')}/reset-password#token={token}"


def main():
    parser = argparse.ArgumentParser(description="Create a one-time password recovery link.")
    parser.add_argument("email", help="Existing account email")
    parser.add_argument("--base-url", required=True, help="Public application URL")
    parser.add_argument("--expires-minutes", type=int, default=30)
    args = parser.parse_args()
    try:
        recovery_url(args.base_url, "validation")
        with session_factory()() as session:
            token = issue_reset(session, args.email, args.expires_minutes)
    except ValueError as exc:
        parser.exit(1, f"{exc}\n")
    print(f"One-time link; expires in {args.expires_minutes} minutes:")
    print(recovery_url(args.base_url, token))
    print("Share privately with the verified account owner. Previous recovery links are invalid.")


if __name__ == "__main__":
    main()
