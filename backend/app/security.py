"""Minimal, dependency-free authentication helpers for AeroCast-NCR.

Uses only the Python standard library:

* Password hashing via ``hashlib.scrypt`` (salted, CPU/memory-hard).
* HS256 JWT-signed session tokens built with ``hmac`` + ``hashlib``.

Deliberately no new pip dependencies: the target deployment (and this repo's
test matrix) must not require PyJWT / bcrypt / passlib.

Security notes:
* ``SECRET_KEY`` must be overridden in any non-development environment.
* Tokens are short-lived (``ACCESS_TOKEN_EXPIRE_MINUTES``).
* ``equal_bytes`` performs a constant-time comparison for hashes.
"""
import base64
import hashlib
import hmac
import json
import logging
import time

logger = logging.getLogger("aerocast.security")

_SALT_BYTES = 16
_KEY_LEN = 32
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1

_JWT_ALG = "HS256"


# ---------------------------------------------------------------------------
# Password hashing (scrypt)
# ---------------------------------------------------------------------------
def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    """Return ``(hex_salt, hex_hash)`` for a plaintext password."""
    if salt is None:
        salt = hashlib.sha256((str(time.monotonic_ns()) + password).encode()).digest()[:_SALT_BYTES]
    dk = hashlib.scrypt(
        password.encode(),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_KEY_LEN,
    )
    return salt.hex(), dk.hex()


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    """Verify a plaintext password against a stored salt+hash pair."""
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, TypeError):
        return False
    dk = hashlib.scrypt(
        password.encode(),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_KEY_LEN,
    )
    return hmac.compare_digest(dk, expected)


# ---------------------------------------------------------------------------
# HS256 JWT (manual, stdlib-only)
# ---------------------------------------------------------------------------
def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(token: str) -> bytes:
    padding = "=" * (-len(token) % 4)
    return base64.urlsafe_b64decode(token + padding)


def create_access_token(
    user_id: int,
    email: str,
    secret: str,
    expires_minutes: int | None = None,
    name: str | None = None,
    role: str | None = None,
) -> str:
    """Create an HS256-signed JWT carrying the user identity.

    ``name``/``role`` are embedded so ``GET /api/auth/me`` can resolve the
    profile from the signed token alone, without a database round-trip (the
    hosted Postgres can take seconds to resume, which otherwise stalls every
    page behind the session check).
    """
    from .config import get_settings

    settings = get_settings()
    minutes = expires_minutes if expires_minutes is not None else settings.access_token_expire_minutes
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "email": email,
        "iat": now,
        "exp": now + max(1, int(minutes) * 60),
        "iss": "aerocast-ncr",
    }
    if name is not None:
        payload["name"] = name
    if role is not None:
        payload["role"] = role
    header = {"alg": _JWT_ALG, "typ": "JWT"}
    seg = _b64url(json.dumps(header, separators=(",", ":")).encode()) + "." + _b64url(
        json.dumps(payload, separators=(",", ":")).encode()
    )
    sig = hmac.new(secret.encode(), seg.encode(), hashlib.sha256).digest()
    return seg + "." + _b64url(sig)


def decode_access_token(token: str, secret: str) -> dict | None:
    """Verify a JWT signature + expiry and return its payload, or ``None``."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    header_b64, payload_b64, sig_b64 = parts
    try:
        expected = hmac.new(
            secret.encode(),
            f"{header_b64}.{payload_b64}".encode(),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(expected, _b64url_decode(sig_b64)):
            return None
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    if payload.get("iss") != "aerocast-ncr":
        return None
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)) or exp < time.time():
        return None
    return payload
