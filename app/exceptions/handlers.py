"""Custom domain exceptions and FastAPI exception handler registrations."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from jose import JWTError


# ── Domain exceptions ──────────────────────────────────────────────────────────


class NotFoundError(Exception):
    """Raised when a requested resource does not exist or is not accessible."""


class ForbiddenError(Exception):
    """Raised when the authenticated user is not authorised to perform an action."""


class ConflictError(Exception):
    """Raised when an operation would create a duplicate or conflicting resource."""


# ── FastAPI handler registration ───────────────────────────────────────────────


def register_exception_handlers(app: FastAPI) -> None:
    """Attach all domain-exception handlers to *app*.

    Centralising handlers here keeps route controllers free of error-mapping
    boilerplate and ensures consistent response shapes across the API.

    Args:
        app: The :class:`FastAPI` application instance.
    """

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ForbiddenError)
    async def forbidden_handler(request: Request, exc: ForbiddenError) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def conflict_handler(request: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(JWTError)
    async def jwt_error_handler(request: Request, exc: JWTError) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={"detail": "Could not validate credentials."},
            headers={"WWW-Authenticate": "Bearer"},
        )
