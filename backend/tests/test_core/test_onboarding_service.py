import json

import pytest

from core.onboarding_service import OnboardingService


def _write_questions(path):
    payload = {
        "version": "1.0",
        "topic": "derivative",
        "questions": [
            {
                "id": "q1",
                "weight": 1,
                "correct_option_id": "A",
                "related_hypothesis": "H01_Trig",
                "options": [{"id": "A", "text": "a"}, {"id": "B", "text": "b"}],
            },
            {
                "id": "q2",
                "weight": 2,
                "correct_option_id": "B",
                "related_hypothesis": "H03_Chain",
                "options": [{"id": "A", "text": "a"}, {"id": "B", "text": "b"}],
            },
            {
                "id": "q3",
                "weight": 3,
                "correct_option_id": "C",
                "related_hypothesis": "H04_Rules",
                "options": [{"id": "C", "text": "c"}, {"id": "D", "text": "d"}],
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_evaluate_answers_resolves_focus_areas(tmp_path) -> None:
    question_path = tmp_path / "onboarding_questions.json"
    _write_questions(question_path)

    service = OnboardingService(questions_path=question_path)
    result = service.evaluate_answers(
        [
            {"question_id": "q1", "selected": "B", "time_taken_sec": 8},
            {"question_id": "q2", "selected": "A", "time_taken_sec": 10},
            {"question_id": "q3", "selected": "C", "time_taken_sec": 12},
        ]
    )

    assert result["user_level"] == "intermediate"
    assert result["summary"]["accuracy_percent"] == 50
    assert result["study_plan"]["focus_areas"] == ["chain_rule", "trig"]
    assert result["study_plan"]["recommended_difficulty"] == 2


def test_evaluate_answers_returns_advanced_for_high_score(tmp_path) -> None:
    question_path = tmp_path / "onboarding_questions.json"
    _write_questions(question_path)

    service = OnboardingService(questions_path=question_path)
    result = service.evaluate_answers(
        [
            {"question_id": "q1", "selected": "A", "time_taken_sec": 2},
            {"question_id": "q2", "selected": "B", "time_taken_sec": 2},
            {"question_id": "q3", "selected": "C", "time_taken_sec": 2},
        ]
    )

    assert result["user_level"] == "advanced"
    assert result["summary"]["accuracy_percent"] == 100
    assert result["study_plan"]["recommended_difficulty"] == 3


def test_evaluate_answers_requires_valid_answers(tmp_path) -> None:
    question_path = tmp_path / "onboarding_questions.json"
    _write_questions(question_path)

    service = OnboardingService(questions_path=question_path)

    with pytest.raises(ValueError):
        service.evaluate_answers([])
