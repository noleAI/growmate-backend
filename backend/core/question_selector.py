from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

from core.user_classifier import UserLevel


HYPOTHESES = ["H01_Trig", "H02_ExpLog", "H03_Chain", "H04_Rules"]


def compute_average_level(player_levels: List[UserLevel]) -> UserLevel:
    if not player_levels:
        return UserLevel.INTERMEDIATE

    level_to_score = {
        UserLevel.BEGINNER: 0,
        UserLevel.INTERMEDIATE: 1,
        UserLevel.ADVANCED: 2,
    }

    scores = []
    for level in player_levels:
        if isinstance(level, UserLevel):
            scores.append(level_to_score[level])
        else:
            normalized = str(level).lower()
            if normalized == UserLevel.BEGINNER.value:
                scores.append(0)
            elif normalized == UserLevel.ADVANCED.value:
                scores.append(2)
            else:
                scores.append(1)

    avg_score = sum(scores) / len(scores)
    if avg_score < 0.67:
        return UserLevel.BEGINNER
    if avg_score < 1.67:
        return UserLevel.INTERMEDIATE
    return UserLevel.ADVANCED


def select_multiplayer_questions(
    player_levels: List[UserLevel],
    question_pool: List[Dict[str, Any]],
    num_questions: int = 10,
    difficulty_distribution: Dict[str, float] | None = None,
) -> List[Dict[str, Any]]:
    if num_questions <= 0 or not question_pool:
        return []

    avg_level = compute_average_level(player_levels)
    default_distribution = {
        UserLevel.BEGINNER: {"easy": 0.4, "medium": 0.5, "hard": 0.1},
        UserLevel.INTERMEDIATE: {"easy": 0.3, "medium": 0.5, "hard": 0.2},
        UserLevel.ADVANCED: {"easy": 0.2, "medium": 0.5, "hard": 0.3},
    }

    distribution = difficulty_distribution or default_distribution[avg_level]
    target_counts = _target_difficulty_counts(num_questions, distribution)

    selected: List[Dict[str, Any]] = []
    selected_count_by_difficulty = {"easy": 0, "medium": 0, "hard": 0}
    used_ids: set[str] = set()

    # First pass: cover each hypothesis if possible.
    by_hypothesis: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for question in question_pool:
        by_hypothesis[_extract_hypothesis(question)].append(question)

    for hypothesis in HYPOTHESES:
        if len(selected) >= num_questions:
            break
        candidates = by_hypothesis.get(hypothesis, [])
        best_candidate: Dict[str, Any] | None = None
        best_score: float | None = None

        for candidate in candidates:
            qid = _question_id(candidate)
            if qid in used_ids:
                continue

            difficulty = _difficulty(candidate)
            score = float(target_counts[difficulty] - selected_count_by_difficulty[difficulty])
            if best_score is None or score > best_score:
                best_score = score
                best_candidate = candidate

        if best_candidate is not None:
            selected.append(best_candidate)
            used_ids.add(_question_id(best_candidate))
            selected_count_by_difficulty[_difficulty(best_candidate)] += 1

    # Second pass: satisfy desired difficulty mix.
    for difficulty in ["easy", "medium", "hard"]:
        needed = max(0, target_counts[difficulty] - selected_count_by_difficulty[difficulty])
        if needed <= 0:
            continue

        for question in question_pool:
            if len(selected) >= num_questions or needed <= 0:
                break
            qid = _question_id(question)
            if qid in used_ids:
                continue
            if _difficulty(question) != difficulty:
                continue

            selected.append(question)
            used_ids.add(qid)
            selected_count_by_difficulty[difficulty] += 1
            needed -= 1

    # Third pass: fill any remaining slots from the pool order.
    if len(selected) < num_questions:
        for question in question_pool:
            if len(selected) >= num_questions:
                break
            qid = _question_id(question)
            if qid in used_ids:
                continue
            selected.append(question)
            used_ids.add(qid)
            selected_count_by_difficulty[_difficulty(question)] += 1

    return selected[:num_questions]


def _question_id(question: Dict[str, Any]) -> str:
    return str(
        question.get("question_id")
        or question.get("id")
        or question.get("quiz_id")
        or f"question-{id(question)}"
    )


def _extract_hypothesis(question: Dict[str, Any]) -> str:
    return str(
        question.get("target_hypothesis")
        or question.get("hypothesis")
        or question.get("hypothesis_tag")
        or "H04_Rules"
    )


def _difficulty(question: Dict[str, Any]) -> str:
    difficulty = str(question.get("difficulty", "medium")).lower()
    if difficulty not in {"easy", "medium", "hard"}:
        return "medium"
    return difficulty


def _target_difficulty_counts(num_questions: int, distribution: Dict[str, float]) -> Dict[str, int]:
    easy = int(round(num_questions * float(distribution.get("easy", 0.0))))
    medium = int(round(num_questions * float(distribution.get("medium", 0.0))))
    hard = int(round(num_questions * float(distribution.get("hard", 0.0))))

    counts = {"easy": easy, "medium": medium, "hard": hard}
    total = sum(counts.values())

    if total < num_questions:
        counts["medium"] += num_questions - total
    elif total > num_questions:
        overflow = total - num_questions
        for key in ["hard", "easy", "medium"]:
            if overflow <= 0:
                break
            reduction = min(overflow, counts[key])
            counts[key] -= reduction
            overflow -= reduction

    return counts

