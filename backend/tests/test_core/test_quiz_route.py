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
    async def _session_stub(**kwargs):
        return {
            "id": kwargs["session_id"],
            "status": "active",
            "last_question_index": 0,
            "total_questions": 10,
            "progress_percent": 0,
            "state_snapshot": {},
        }

    async def _progress_stub(**kwargs):
        del kwargs
        return {"data": [], "count": 1}

    async def _attempt_stub(**kwargs):
        del kwargs
        return {"data": [], "count": 1}

    quiz_route.get_learning_session_by_id = _session_stub
    quiz_route.update_learning_session_progress = _progress_stub
    quiz_route.insert_quiz_question_attempt = _attempt_stub

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
    assert "score" in result
    assert "quiz_summary" in result
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


@pytest.mark.asyncio
async def test_get_quiz_result_uses_snapshot_data() -> None:
    async def _session_stub(**kwargs):
        del kwargs
        return {
            "id": "sess-result-1",
            "status": "completed",
            "last_question_index": 3,
            "total_questions": 5,
            "progress_percent": 60,
            "start_time": "2026-04-17T10:00:00+00:00",
            "end_time": "2026-04-17T10:10:00+00:00",
            "state_snapshot": {
                "quiz_state": {
                    "summary": {
                        "answered_count": 3,
                        "correct_count": 2,
                        "total_score": 2.0,
                        "max_score": 3.0,
                        "accuracy_percent": 67,
                    },
                    "attempts": [
                        {
                            "question_id": "MATH_DERIV_1",
                            "question_template_id": "template-1",
                            "question_type": "MULTIPLE_CHOICE",
                            "is_correct": True,
                            "score": 1.0,
                            "max_score": 1.0,
                            "evaluation": {"explanation": "ok"},
                            "user_answer": {"selected_option": "A"},
                            "submitted_at": "2026-04-17T10:02:00+00:00",
                        }
                    ],
                }
            },
        }

    quiz_route.get_learning_session_by_id = _session_stub

    result = await quiz_route.get_quiz_result(
        session_id="sess-result-1",
        user={"sub": "student-1"},
        access_token="token",
    )

    assert result["status"] == "ok"
    assert result["session_status"] == "completed"
    assert result["summary"]["answered_count"] == 3
    assert len(result["attempts"]) == 1


@pytest.mark.asyncio
async def test_get_quiz_history_returns_session_summaries() -> None:
    async def _history_stub(**kwargs):
        assert kwargs["student_id"] == "student-1"
        return [
            {
                "id": "sess-hist-1",
                "status": "completed",
                "start_time": "2026-04-17T09:00:00+00:00",
                "end_time": "2026-04-17T09:12:00+00:00",
                "last_question_index": 10,
                "total_questions": 10,
                "progress_percent": 100,
                "state_snapshot": {
                    "quiz_state": {
                        "summary": {
                            "answered_count": 10,
                            "correct_count": 8,
                            "total_score": 8.0,
                            "max_score": 10.0,
                            "accuracy_percent": 80,
                        }
                    }
                },
            }
        ]

    quiz_route.list_learning_sessions = _history_stub

    result = await quiz_route.get_quiz_history(
        limit=20,
        offset=0,
        user={"sub": "student-1"},
        access_token="token",
    )

    assert result["status"] == "ok"
    assert result["total"] == 1
    assert result["items"][0]["session_id"] == "sess-hist-1"
    assert result["items"][0]["summary"]["accuracy_percent"] == 80
