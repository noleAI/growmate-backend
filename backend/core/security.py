from functools import lru_cache
from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
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


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    settings: Settings = Depends(get_settings),
):
    token = credentials.credentials
    try:
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
    except (InvalidTokenError, PyJWKClientError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_bearer_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    return credentials.credentials
