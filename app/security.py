"""Password hashing and signed session cookies.

Standard library only. This is sized for a local, single-person tool: it is
honest about being that, not a hardened multi-tenant auth system. When the
Supabase backend is switched on, Supabase Auth replaces this entirely.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from .config import settings

PBKDF2_ROUNDS = 240_000
SALT_BYTES = 16


# --------------------------------------------------------------------------
# passwords
# --------------------------------------------------------------------------
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${PBKDF2_ROUNDS}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, rounds, salt_b64, digest_b64 = stored.split("$")
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    try:
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), _unb64(salt_b64), int(rounds)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, _unb64(digest_b64))


# --------------------------------------------------------------------------
# sessions
# --------------------------------------------------------------------------
def make_session(user_id: str) -> str:
    payload = {
        "uid": user_id,
        "exp": int(time.time()) + settings.session_days * 86400,
    }
    body = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{body}.{_sign(body)}"


def read_session(token: str | None) -> str | None:
    """Return the user id, or None if the token is missing, bad or expired."""
    if not token or "." not in token:
        return None
    body, _, signature = token.rpartition(".")
    if not hmac.compare_digest(signature, _sign(body)):
        return None
    try:
        payload = json.loads(_unb64(body))
    except (ValueError, TypeError):
        return None
    if int(payload.get("exp", 0)) < time.time():
        return None
    uid = payload.get("uid")
    return uid if isinstance(uid, str) else None


def _sign(body: str) -> str:
    mac = hmac.new(settings.secret_key.encode("utf-8"), body.encode("utf-8"), hashlib.sha256)
    return _b64(mac.digest())


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
