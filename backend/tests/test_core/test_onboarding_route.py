import pytest
from fastapi import HTTPException

from api.routes import onboarding as onboarding_route


@pytest.mark.asyncio
async def test_get_onboarding_questions_returns_sanitized_payload(monkeypatch) -> None:
    def _questions_stub() -> list[dict]:
        return [
            {
                "question_id": "onb_01",
                "question": "Dao ham cua x^2 la gi?",
                "options": ["2x", "x", "x^2"],
                "difficulty": "easy",
            }
        ]

    monkeypatch.setattr(onboarding_route.onboarding_service, "get_questions_for_client", _questions_stub)

    result = await onboarding_route.get_onboarding_questions(_user={"sub": "student-1"})

    assert result["topic"] == "derivative"
    assert result["total_questions"] == 1
    assert result["questions"][0]["question_id"] == "onb_01"


@pytest.mark.asyncio
async def test_submit_onboarding_returns_plan_and_persists_profile(monkeypatch) -> None:
    async def _get_profile_stub(**kwargs) -> dict:
        assert kwargs["user_id"] == "student-1"
        return {
            "user_id": "student-1",
            "display_name": "Student One",
            "avatar_url": None,
            "study_goal": None,
            "daily_minutes": 15,
            "user_level": "beginner",
            "onboarded_at": None,
        }

    async def _upsert_profile_stub(**kwargs) -> dict:
        assert kwargs["user_id"] == "student-1"
        assert kwargs["user_level"] == "intermediate"
        assert kwargs["study_goal"] == "exam_prep"
        assert kwargs["daily_minutes"] == 20
        return kwargs

    def _evaluate_stub(answers):
        assert len(answers) == 2
        return {
            "user_level": "intermediate",
            "study_plan": {
                "daily_minutes": 25,
                "focus_areas": ["chain_rule", "trig"],
                "recommended_difficulty": 2,
                "difficulty": "mixed",
                "starting_hypothesis": "H04_Rules",
                "hint_policy": "adaptive",
            },
            "summary": {
                "total_questions": 10,
                "answered_questions": 10,
                "correct_answers": 6,
                "accuracy_percent": 62,
                "avg_response_time_ms": 8200,
            },
        }

    monkeypatch.setattr(onboarding_route, "get_user_profile", _get_profile_stub)
    monkeypatch.setattr(onboarding_route, "upsert_user_profile", _upsert_profile_stub)
    monkeypatch.setattr(onboarding_route.onboarding_service, "evaluate_answers", _evaluate_stub)

    result = await onboarding_route.submit_onboarding(
        request=onboarding_route.OnboardingSubmitRequest(
            answers=[
                onboarding_route.OnboardingAnswer(
                    question_id="onb_01",
                    selected="A",
                    time_taken_sec=5,
                ),
                onboarding_route.OnboardingAnswer(
                    question_id="onb_02",
                    selected="B",
                    time_taken_sec=6,
                ),
            ],
            study_goal="exam_prep",
            daily_minutes=20,
        ),
        user={"sub": "student-1"},
        access_token="token-1",
    )

    assert result["user_level"] == "intermediate"
    assert result["accuracy_percent"] == 62
    assert result["study_plan"]["daily_minutes"] == 20


@pytest.mark.asyncio
async def test_submit_onboarding_rejects_invalid_study_goal() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await onboarding_route.submit_onboarding(
            request=onboarding_route.OnboardingSubmitRequest(
                answers=[
                    onboarding_route.OnboardingAnswer(
                        question_id="onb_01",
                        selected="A",
                    )
                ],
                study_goal="invalid",
            ),
            user={"sub": "student-1"},
            access_token="token",
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_submit_onboarding_requires_student_id() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await onboarding_route.submit_onboarding(
            request=onboarding_route.OnboardingSubmitRequest(
                answers=[
                    onboarding_route.OnboardingAnswer(
                        question_id="onb_01",
                        selected="A",
                    )
                ],
            ),
            user={},
            access_token="token",
        )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_submit_onboarding_rejects_daily_minutes_out_of_range() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await onboarding_route.submit_onboarding(
            request=onboarding_route.OnboardingSubmitRequest(
                answers=[
                    onboarding_route.OnboardingAnswer(
                        question_id="onb_01",
                        selected="A",
                    )
                ],
                daily_minutes=200,
            ),
            user={"sub": "student-1"},
            access_token="token",
        )

    assert exc_info.value.status_code == 400
