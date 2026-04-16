from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from core.user_classifier import UserLevel, classify, get_study_plan

logger = logging.getLogger("core.onboarding_service")

HYPOTHESIS_TO_FOCUS_AREA = {
    "H01_Trig": "trig",
    "H02_ExpLog": "exp_log",
    "H03_Chain": "chain_rule",
    "H04_Rules": "rules",
}

LEVEL_TO_DIFFICULTY = {
    UserLevel.BEGINNER: 1,
    UserLevel.INTERMEDIATE: 2,
    UserLevel.ADVANCED: 3,
}


class OnboardingService:
    def __init__(self, questions_path: Path | None = None) -> None:
        base_dir = Path(__file__).resolve().parents[1]
        self.questions_path = questions_path or (
            base_dir / "data" / "onboarding_questions.json"
        )
        self._questions = self._load_questions()
        self._question_by_id = {
            str(item.get("id", "")).strip(): item for item in self._questions
        }

    def get_questions_for_client(self) -> list[dict[str, Any]]:
        ordered = sorted(
            self._questions,
            key=lambda item: int(item.get("order", 0) or 0),
        )

        result: list[dict[str, Any]] = []
        for index, item in enumerate(ordered, start=1):
            options = item.get("options")
            if not isinstance(options, list):
                options = []

            sanitized_options = [
                {
                    "id": str(option.get("id") or "").strip(),
                    "text": str(option.get("text") or "").strip(),
                }
                for option in options
                if isinstance(option, dict)
            ]

            result.append(
                {
                    "id": str(item.get("id") or "").strip(),
                    "order": int(item.get("order", index) or index),
                    "difficulty": str(item.get("difficulty") or "medium").strip(),
                    "weight": self._question_weight(item),
                    "content": str(item.get("content") or "").strip(),
                    "options": sanitized_options,
                    "related_hypothesis": str(
                        item.get("related_hypothesis") or "H04_Rules"
                    ).strip(),
                }
            )

        return result

    def evaluate_answers(self, answers: list[dict[str, Any]]) -> dict[str, Any]:
        if not self._questions:
            raise RuntimeError("Onboarding question catalog is empty")

        normalized_answers = self._normalize_answers(answers)
        total_questions = len(self._questions)
        weighted_total = sum(self._question_weight(item) for item in self._questions)

        correct_answers = 0
        weighted_correct = 0
        weighted_incorrect_by_hypothesis = {
            key: 0 for key in HYPOTHESIS_TO_FOCUS_AREA.keys()
        }

        for question in self._questions:
            question_id = str(question.get("id", "")).strip()
            selected = normalized_answers.get(question_id, {}).get("selected")
            weight = self._question_weight(question)
            correct_option_id = str(question.get("correct_option_id", "")).strip().upper()
            hypothesis = str(question.get("related_hypothesis") or "H04_Rules")

            if selected and selected == correct_option_id:
                correct_answers += 1
                weighted_correct += weight
                continue

            if hypothesis not in weighted_incorrect_by_hypothesis:
                weighted_incorrect_by_hypothesis[hypothesis] = 0
            weighted_incorrect_by_hypothesis[hypothesis] += weight

        accuracy_percent = int(round((weighted_correct / weighted_total) * 100))
        avg_response_time_ms = self._average_response_time_ms(normalized_answers)

        onboarding_results = {
            "correct": weighted_correct,
            "total": weighted_total,
            "avg_response_time_ms": avg_response_time_ms,
        }

        user_level = classify(onboarding_results)
        base_plan = get_study_plan(user_level)

        focus_areas = self._resolve_focus_areas(weighted_incorrect_by_hypothesis)
        if not focus_areas:
            default_focus = HYPOTHESIS_TO_FOCUS_AREA.get(
                str(base_plan.get("starting_hypothesis", "")),
                "rules",
            )
            focus_areas = [default_focus]

        study_plan = {
            "daily_minutes": int(base_plan.get("daily_minutes", 15)),
            "focus_areas": focus_areas,
            "recommended_difficulty": LEVEL_TO_DIFFICULTY[user_level],
            "difficulty": str(base_plan.get("difficulty", "mixed")),
            "starting_hypothesis": str(
                base_plan.get("starting_hypothesis", "H04_Rules")
            ),
            "hint_policy": str(base_plan.get("hint_policy", "adaptive")),
        }

        return {
            "user_level": user_level.value,
            "onboarding_results": onboarding_results,
            "study_plan": study_plan,
            "summary": {
                "total_questions": total_questions,
                "answered_questions": len(normalized_answers),
                "correct_answers": correct_answers,
                "weighted_correct": weighted_correct,
                "weighted_total": weighted_total,
                "accuracy_percent": accuracy_percent,
                "avg_response_time_ms": avg_response_time_ms,
                "weak_hypotheses": [
                    {
                        "hypothesis": key,
                        "error_weight": int(value),
                    }
                    for key, value in sorted(
                        weighted_incorrect_by_hypothesis.items(),
                        key=lambda pair: pair[1],
                        reverse=True,
                    )
                    if int(value) > 0
                ],
            },
        }

    def _load_questions(self) -> list[dict[str, Any]]:
        if not self.questions_path.exists():
            logger.warning("Onboarding question file not found: %s", self.questions_path)
            return []

        try:
            with self.questions_path.open("r", encoding="utf-8") as stream:
                payload = json.load(stream)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "Failed to read onboarding question file %s: %s",
                self.questions_path,
                exc,
            )
            return []

        if not isinstance(payload, dict):
            return []

        questions = payload.get("questions")
        if not isinstance(questions, list):
            return []

        normalized: list[dict[str, Any]] = []
        for item in questions:
            if not isinstance(item, dict):
                continue

            question_id = str(item.get("id") or "").strip()
            correct_option_id = str(item.get("correct_option_id") or "").strip().upper()
            options = item.get("options")

            if not question_id or not correct_option_id or not isinstance(options, list):
                continue

            normalized.append(item)

        return normalized

    def _normalize_answers(
        self,
        answers: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        normalized: dict[str, dict[str, Any]] = {}

        for item in answers:
            if not isinstance(item, dict):
                continue

            question_id = str(item.get("question_id") or "").strip()
            if not question_id or question_id not in self._question_by_id:
                continue

            if question_id in normalized:
                # Keep the first answer to avoid accidental override from duplicate submits.
                continue

            selected = str(item.get("selected") or "").strip().upper()
            if not selected:
                continue

            time_taken_sec = item.get("time_taken_sec")
            normalized[question_id] = {
                "selected": selected,
                "time_taken_sec": self._safe_float(time_taken_sec),
            }

        if not normalized:
            raise ValueError("answers must include at least one valid question response")

        return normalized

    @staticmethod
    def _question_weight(question: dict[str, Any]) -> int:
        try:
            return max(1, int(question.get("weight", 1) or 1))
        except (TypeError, ValueError):
            return 1

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        if value is None:
            return None

        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None

        if parsed < 0:
            return None

        return parsed

    @staticmethod
    def _average_response_time_ms(
        normalized_answers: dict[str, dict[str, Any]],
    ) -> int:
        durations_sec = [
            float(item["time_taken_sec"])
            for item in normalized_answers.values()
            if item.get("time_taken_sec") is not None
        ]

        if not durations_sec:
            return 0

        return int(round((sum(durations_sec) / len(durations_sec)) * 1000))

    @staticmethod
    def _resolve_focus_areas(
        weighted_incorrect_by_hypothesis: dict[str, int],
    ) -> list[str]:
        ranked = sorted(
            weighted_incorrect_by_hypothesis.items(),
            key=lambda pair: pair[1],
            reverse=True,
        )

        focus_areas: list[str] = []
        for hypothesis, error_weight in ranked:
            if int(error_weight) <= 0:
                continue
            area = HYPOTHESIS_TO_FOCUS_AREA.get(hypothesis)
            if not area:
                continue
            focus_areas.append(area)
            if len(focus_areas) >= 2:
                break

        return focus_areas


onboarding_service = OnboardingService()
