import random

from core.quiz_service import QuizService


def test_build_or_get_session_order_does_not_mutate_global_rng() -> None:
    service = QuizService()

    random.seed("quiz-global-rng-check")
    expected_next = random.random()

    random.seed("quiz-global-rng-check")
    _ = service.build_or_get_session_order(
        session_id="sess-rng-safety",
        mode="explore",
        total_questions=10,
    )
    actual_next = random.random()

    assert actual_next == expected_next


def test_build_or_get_session_order_is_deterministic_for_same_inputs() -> None:
    service_a = QuizService()
    service_b = QuizService()

    order_a = service_a.build_or_get_session_order(
        session_id="sess-deterministic",
        mode="exam_prep",
        total_questions=8,
    )
    order_b = service_b.build_or_get_session_order(
        session_id="sess-deterministic",
        mode="exam_prep",
        total_questions=8,
    )

    assert order_a == order_b
