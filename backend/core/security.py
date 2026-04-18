import hashlib
import hmac
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, WebSocket, WebSocketException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWKClient
from jwt.exceptions import PyJWKClientError

from core.config import Settings, get_settings

security = HTTPBearer()


def _resolve_supabase_issuer(settings: Settings) -> str:
    if settings.supabase_jwt_issuer:
        return settings.supabase_jwt_issuer.rstrip("/")
    return f"{settings.supabase_url.rstrip('/')}/auth/v1"


def _resolve_supabase_jwks_url(settings: Settings) -> str:
    if settings.supabase_jwks_url:
        return settings.supabase_jwks_url
    return f"{_resolve_supabase_issuer(settings)}/.well-known/jwks.json"

@lru_cache(maxsize=1)
def _get_jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url)


def _decode_bearer_token(token: str, settings: Settings) -> dict[str, Any]:
    issuer = _resolve_supabase_issuer(settings)
    decode_kwargs: dict[str, Any] = {
        "algorithms": ["RS256", "ES256"],
        "issuer": issuer,
    }
    if settings.supabase_jwt_audience:
        decode_kwargs["audience"] = settings.supabase_jwt_audience

    jwks_client = _get_jwks_client(_resolve_supabase_jwks_url(settings))
    signing_key = jwks_client.get_signing_key_from_jwt(token)
    return jwt.decode(token, signing_key.key, **decode_kwargs)


def _normalize_bearer_value(value: str | None) -> str:
    token = str(value or "").strip()
    if token.lower().startswith("bearer "):
        token = token.split(" ", 1)[1].strip()
    return token


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    settings: Settings = Depends(get_settings),
):
    token = credentials.credentials
    try:
        return _decode_bearer_token(token, settings)
    except (InvalidTokenError, PyJWKClientError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user_ws(
    websocket: WebSocket,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    header_token = _normalize_bearer_value(websocket.headers.get("authorization"))
    query_token = _normalize_bearer_value(
        websocket.query_params.get("access_token") or websocket.query_params.get("token")
    )
    token = header_token or query_token

    if not token:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Missing bearer token",
        )

    try:
        return _decode_bearer_token(token, settings)
    except (InvalidTokenError, PyJWKClientError) as exc:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Could not validate credentials",
        ) from exc


def get_bearer_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    return credentials.credentials


def _parse_signature_header(raw_signature: str) -> str:
    normalized = str(raw_signature or "").strip()
    if normalized.lower().startswith("sha256="):
        normalized = normalized.split("=", 1)[1].strip()
    return normalized


def _build_signature_payload(
    request: Request,
    body: bytes,
    timestamp: str,
) -> str:
    method = request.method.upper()
    path = request.url.path
    body_hash = hashlib.sha256(body).hexdigest()
    return "\n".join([method, path, timestamp, body_hash])


async def require_quiz_signature(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    await verify_quiz_signature(
        request=request,
        secret=settings.quiz_hmac_secret,
        ttl_seconds=settings.quiz_signature_ttl_seconds,
    )


async def verify_quiz_signature(
    request: Request,
    secret: str | None,
    ttl_seconds: int = 300,
) -> None:
    normalized_secret = str(secret or "").strip()
    if not normalized_secret:
        return

    timestamp = request.headers.get("X-Growmate-Timestamp")
    signature = request.headers.get("X-Growmate-Signature")
    if not timestamp or not signature:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing_signature_headers",
        )

    try:
        unix_seconds = int(timestamp)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_signature_timestamp",
        ) from exc

    now_seconds = int(datetime.now(UTC).timestamp())
    if abs(now_seconds - unix_seconds) > int(max(1, ttl_seconds)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="signature_expired",
        )

    body = await request.body()
    payload = _build_signature_payload(request, body, timestamp)
    expected = hmac.new(
        normalized_secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    normalized_signature = _parse_signature_header(signature)

    if not hmac.compare_digest(normalized_signature, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_signature",
        )
