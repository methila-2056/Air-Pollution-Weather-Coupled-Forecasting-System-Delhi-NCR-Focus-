"""Tests for the SIH26082 portal authentication layer.

Covers the stdlib-only password hashing + HS256 JWT helpers in
``app.security`` and the additive ``/api/auth/*`` endpoints. The existing data
API is intentionally left public — those endpoints are covered elsewhere.
"""
import time

from app.api.auth import ensure_demo_user
from app.config import get_settings
from app.models.db_models import User
from app.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


# ---------------------------------------------------------------------------
# Unit: password hashing (scrypt)
# ---------------------------------------------------------------------------
def test_hash_password_roundtrip():
    salt, pwhash = hash_password("S3cret-Pass")
    assert salt and pwhash
    assert verify_password("S3cret-Pass", salt, pwhash)


def test_hash_password_rejects_wrong_password():
    salt, pwhash = hash_password("right-password")
    assert not verify_password("wrong-password", salt, pwhash)


def test_hash_is_salted_per_call():
    salt1, h1 = hash_password("same-pass")
    salt2, h2 = hash_password("same-pass")
    assert (salt1, h1) != (salt2, h2)


def test_verify_password_bad_format():
    assert not verify_password("x", "not-hex", "still-not-hex")


# ---------------------------------------------------------------------------
# Unit: HS256 JWT
# ---------------------------------------------------------------------------
def test_access_token_roundtrip():
    secret = "test-secret"
    token = create_access_token(7, "u@test.in", secret, expires_minutes=60)
    payload = decode_access_token(token, secret)
    assert payload is not None
    assert payload["sub"] == "7"
    assert payload["email"] == "u@test.in"
    assert payload["iss"] == "aerocast-ncr"
    assert "name" not in payload
    assert "role" not in payload


def test_access_token_embeds_profile_claims_only_when_given():
    secret = "test-secret"
    token = create_access_token(
        7, "u@test.in", secret, expires_minutes=60, name="Test User", role="admin"
    )
    payload = decode_access_token(token, secret)
    assert payload is not None
    assert payload["name"] == "Test User"
    assert payload["role"] == "admin"


def test_access_token_wrong_secret():
    token = create_access_token(7, "u@test.in", "secret-a", expires_minutes=60)
    assert decode_access_token(token, "secret-b") is None


def test_access_token_tampered():
    token = create_access_token(7, "u@test.in", "secret", expires_minutes=60)
    tampered = token[:-4] + "AAAA"
    assert decode_access_token(tampered, "secret") is None


def test_access_token_expired():
    token = create_access_token(7, "u@test.in", "secret", expires_minutes=0)
    time.sleep(1.05)
    assert decode_access_token(token, "secret") is None


def test_garbage_token_returns_none():
    assert decode_access_token("not-a-jwt", "secret") is None


# ---------------------------------------------------------------------------
# API: login / me / logout
# ---------------------------------------------------------------------------
def test_login_success(client, db_session):
    ensure_demo_user(db_session)
    settings = get_settings()
    response = client.post(
        "/api/auth/login",
        json={"email": settings.demo_user_email, "password": settings.demo_user_password},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == settings.demo_user_email
    assert body["user"]["role"] == settings.demo_user_role
    assert body["expires_in"] > 0


def test_login_invalid_password(client, db_session):
    ensure_demo_user(db_session)
    settings = get_settings()
    response = client.post(
        "/api/auth/login",
        json={"email": settings.demo_user_email, "password": "definitely-wrong"},
    )
    assert response.status_code == 401


def test_login_unknown_email(client):
    response = client.post(
        "/api/auth/login",
        json={"email": "nobody@example.com", "password": "whatever"},
    )
    assert response.status_code == 401


def test_me_with_valid_token(client, db_session):
    ensure_demo_user(db_session)
    user = db_session.query(User).filter(User.email == get_settings().demo_user_email).first()
    assert user is not None
    token = create_access_token(user.id, user.email, get_settings().secret_key)
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == user.email


def test_me_without_token(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_me_resolves_profile_from_token_claims_without_db_roundtrip(client, db_session):
    """The sign-in fix: /auth/me must answer from the signed JWT claims alone.

    A valid token carrying name/role/email must return the profile even when the
    user row no longer exists — proving no database lookup blocks the session
    check (the hosted Postgres can take 16-30s to resume).
    """
    secret = get_settings().secret_key
    token = create_access_token(999999, "ghost@test.in", secret, expires_minutes=60, name="Ghost User", role="viewer")
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "ghost@test.in"
    assert body["name"] == "Ghost User"
    assert body["role"] == "viewer"
    assert body["id"] == 999999


def test_me_falls_back_to_db_for_legacy_token_without_claims(client, db_session):
    """Pre-fix tokens lack the profile claims and must still resolve via the DB.

    For an unknown user id the DB fallback must 401 (and must not silently mint
    a profile out of thin air).
    """
    token = create_access_token(999999, "ghost@test.in", get_settings().secret_key, expires_minutes=60)
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_me_with_garbage_token(client):
    response = client.get("/api/auth/me", headers={"Authorization": "Bearer garbage"})
    assert response.status_code == 401


def test_logout_returns_user(client, db_session):
    ensure_demo_user(db_session)
    user = db_session.query(User).filter(User.email == get_settings().demo_user_email).first()
    token = create_access_token(user.id, user.email, get_settings().secret_key)
    response = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["email"] == user.email


def test_demo_credentials_endpoint(client):
    response = client.get("/api/auth/demo")
    assert response.status_code == 200
    settings = get_settings()
    assert response.json()["email"] == settings.demo_user_email
    assert response.json()["password"] == settings.demo_user_password


def test_public_data_api_still_open(client):
    """Guard: the auth layer must NOT lock down the forecasting API."""
    response = client.get("/api/stations")
    assert response.status_code == 200
