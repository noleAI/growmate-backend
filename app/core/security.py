"""JWT verification helpers for Supabase-issued tokens.

Supabase acts as the authentication provider.  Clients authenticate directly
with Supabase and receive a signed JWT.  This module verifies that JWT using
the project's JWT secret so that the backend never handles raw credentials.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import get_settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Supabase JWT verification ──────────────────────────────────────────────────


def decode_supabase_token(token: str) -> dict[str, Any]:
    """Decode and verify a Supabase-issued JWT.

    Args:
        token: The raw Bearer token from the ``Authorization`` header.

    Returns:
        The decoded JWT payload as a dictionary.

    Raises:
        JWTError: If the token is invalid, expired, or cannot be verified.

    Time complexity: O(1).
    """
    settings = get_settings()
    payload: dict[str, Any] = jwt.decode(
        token,
        settings.supabase_jwt_secret,
        algorithms=[settings.algorithm],
        options={"verify_aud": False},
    )
    return payload


def get_user_id_from_token(token: str) -> str:
    """Extract the Supabase user UUID (``sub`` claim) from a verified JWT.

    Args:
        token: A valid Supabase Bearer token.

    Returns:
        The UUID string of the authenticated user.

    Raises:
        JWTError: If the token is invalid or the ``sub`` claim is missing.
    """
    payload = decode_supabase_token(token)
    user_id: str | None = payload.get("sub")
    if user_id is None:
        raise JWTError("Token payload is missing 'sub' claim.")
    return user_id


# ── Internal service tokens (optional, for service-to-service calls) ──────────


def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Create a short-lived internal JWT (not a Supabase token).

    Args:
        data: Claims to embed in the token.
        expires_delta: Custom TTL; defaults to ``ACCESS_TOKEN_EXPIRE_MINUTES``.

    Returns:
        An encoded JWT string.
    """
    settings = get_settings()
    to_encode = data.copy()
    expire = datetime.now(UTC) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


# ── Password utilities (for future local-auth fallback if needed) ──────────────


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return ``True`` if *plain_password* matches *hashed_password*."""
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    """Return a bcrypt hash of *password*."""
    return pwd_context.hash(password)
