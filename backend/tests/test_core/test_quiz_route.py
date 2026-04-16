import pytest
from fastapi import HTTPException

from api.routes import quiz as quiz_route
from core.quiz_service import quiz_service


class _RequestStub:
    method = "POST"

    class _URL:
        path = "/api/v1/quiz/submit"

    url = _URL()
    headers = {}

    async def body(self) -> bytes:
        return b"{}"


@pytest.mark.asyncio
async def test_get_next_question_hides_correct_answer() -> None:
    result = await quiz_route.get_next_question(
        request=_RequestStub(),
        session_id="sess-quiz-1",
        index=0,
        total_questions=5,
        mode="explore",
        user={"sub": "student-1"},
        access_token="token",
    )

    assert result["status"] == "ok"
    question = result["next_question"]
    assert question is not None
    assert "correct_option_id" not in question
    assert "payload" not in question


@pytest.mark.asyncio
async def test_get_next_question_exam_prep_rate_limited(monkeypatch) -> None:
    async def _daily_count_stub(**kwargs) -> int:
        del kwargs
        return 5

    monkeypatch.setattr(quiz_route, "count_daily_learning_sessions", _daily_count_stub)

    with pytest.raises(HTTPException) as exc_info:
        await quiz_route.get_next_question(
            request=_RequestStub(),
            session_id="sess-quiz-2",
            index=0,
            total_questions=5,
            mode="exam_prep",
            user={"sub": "student-1"},
            access_token="token",
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail == "quiz_rate_limit"


@pytest.mark.asyncio
async def test_submit_quiz_answer_returns_sanitized_payload() -> None:
    question = quiz_service._question_by_id["MATH_DERIV_1"]
    correct_option_id = str(question["payload"]["correct_option_id"]).strip()

    result = await quiz_route.submit_quiz_answer(
        request=_RequestStub(),
        payload=quiz_route.QuizSubmitRequest(
            session_id="sess-quiz-3",
            question_id="MATH_DERIV_1",
            selected_option=correct_option_id,
            mode="exam_prep",
        ),
        user={"sub": "student-1"},
        access_token="token",
    )

    assert result["is_correct"] is True
    assert "explanation" in result
    assert "correct_option_id" not in result
    assert "correct_answer" not in result


@pytest.mark.asyncio
async def test_submit_quiz_answer_rejects_invalid_mode() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await quiz_route.submit_quiz_answer(
            request=_RequestStub(),
            payload=quiz_route.QuizSubmitRequest(
                session_id="sess-quiz-4",
                question_id="MATH_DERIV_1",
                selected_option="A",
                mode="invalid",
            ),
            user={"sub": "student-1"},
            access_token="token",
        )

    assert exc_info.value.status_code == 400
