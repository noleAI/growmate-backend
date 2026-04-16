from collections import Counter

from core.question_selector import compute_average_level, select_multiplayer_questions
from core.user_classifier import UserLevel


def _build_question_pool() -> list[dict]:
    pool: list[dict] = [
        {
            "question_id": "seed_h01_easy",
            "target_hypothesis": "H01_Trig",
            "difficulty": "easy",
        },
        {
            "question_id": "seed_h02_medium",
            "target_hypothesis": "H02_ExpLog",
            "difficulty": "medium",
        },
        {
            "question_id": "seed_h03_hard",
            "target_hypothesis": "H03_Chain",
            "difficulty": "hard",
        },
        {
            "question_id": "seed_h04_medium",
            "target_hypothesis": "H04_Rules",
            "difficulty": "medium",
        },
    ]

    hypotheses = ["H01_Trig", "H02_ExpLog", "H03_Chain", "H04_Rules"]
    difficulties = ["easy", "medium", "hard"]

    for hypothesis in hypotheses:
        for difficulty in difficulties:
            for idx in range(3):
                pool.append(
                    {
                        "question_id": f"{hypothesis}_{difficulty}_{idx}",
                        "target_hypothesis": hypothesis,
                        "difficulty": difficulty,
                    }
                )

    return pool


def test_compute_average_level_maps_to_intermediate() -> None:
    result = compute_average_level(
        [UserLevel.BEGINNER, UserLevel.INTERMEDIATE, UserLevel.ADVANCED]
    )
    assert result == UserLevel.INTERMEDIATE


def test_multiplayer_selector_keeps_hypothesis_coverage() -> None:
    selected = select_multiplayer_questions(
        player_levels=[UserLevel.INTERMEDIATE, UserLevel.INTERMEDIATE],
        question_pool=_build_question_pool(),
        num_questions=10,
    )

    assert len(selected) == 10

    hypothesis_set = {
        question.get("target_hypothesis") for question in selected if question.get("target_hypothesis")
    }
    assert {"H01_Trig", "H02_ExpLog", "H03_Chain", "H04_Rules"}.issubset(hypothesis_set)


def test_multiplayer_selector_balances_advanced_distribution() -> None:
    selected = select_multiplayer_questions(
        player_levels=[UserLevel.ADVANCED, UserLevel.ADVANCED],
        question_pool=_build_question_pool(),
        num_questions=10,
    )

    counts = Counter(question.get("difficulty") for question in selected)
    assert counts["easy"] == 2
    assert counts["medium"] == 5
    assert counts["hard"] == 3


def test_multiplayer_selector_accepts_custom_distribution() -> None:
    selected = select_multiplayer_questions(
        player_levels=[UserLevel.BEGINNER],
        question_pool=_build_question_pool(),
        num_questions=10,
        difficulty_distribution={"easy": 0.7, "medium": 0.2, "hard": 0.1},
    )

    counts = Counter(question.get("difficulty") for question in selected)
    assert counts["easy"] >= 6
