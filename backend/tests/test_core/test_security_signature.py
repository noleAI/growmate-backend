import hashlib
import hmac
from datetime import UTC, datetime

import pytest
from fastapi import HTTPException

from core.config import Settings
from core.security import verify_quiz_signature


class _URL:
    def __init__(self, path: str):
        self.path = path


class _RequestStub:
    def __init__(self, path: str, body_bytes: bytes, headers: dict[str, str]):
        self.method = "POST"
        self.url = _URL(path)
        self.headers = headers
        self._body = body_bytes

    async def body(self) -> bytes:
        return self._body


@pytest.mark.asyncio
async def test_require_quiz_signature_accepts_valid_signature() -> None:
    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_key="anon",
        quiz_hmac_secret="secret-key",
        quiz_signature_ttl_seconds=300,
    )

    timestamp = str(int(datetime.now(UTC).timestamp()))
    body = b'{"session_id":"sess-1"}'
    payload = "\n".join(
        [
            "POST",
            "/api/v1/quiz/submit",
            timestamp,
            hashlib.sha256(body).hexdigest(),
        ]
    )
    signature = hmac.new(
        settings.quiz_hmac_secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    request = _RequestStub(
        path="/api/v1/quiz/submit",
        body_bytes=body,
        headers={
            "X-Growmate-Timestamp": timestamp,
            "X-Growmate-Signature": signature,
        },
    )

    await verify_quiz_signature(
        request=request,
        secret=settings.quiz_hmac_secret,
        ttl_seconds=settings.quiz_signature_ttl_seconds,
    )


@pytest.mark.asyncio
async def test_require_quiz_signature_rejects_invalid_signature() -> None:
    settings = Settings(
        supabase_url="https://example.supabase.co",
        supabase_key="anon",
        quiz_hmac_secret="secret-key",
        quiz_signature_ttl_seconds=300,
    )

    timestamp = str(int(datetime.now(UTC).timestamp()))
    request = _RequestStub(
        path="/api/v1/quiz/submit",
        body_bytes=b'{"session_id":"sess-1"}',
        headers={
            "X-Growmate-Timestamp": timestamp,
            "X-Growmate-Signature": "invalid",
        },
    )

    with pytest.raises(HTTPException) as exc_info:
        await verify_quiz_signature(
            request=request,
            secret=settings.quiz_hmac_secret,
            ttl_seconds=settings.quiz_signature_ttl_seconds,
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "invalid_signature"
