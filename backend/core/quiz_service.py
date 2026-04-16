from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Dict, List

from core.question_selector import select_quiz_questions_for_mode


class QuizService:
    def __init__(self, dataset_path: Path | None = None) -> None:
        base_dir = Path(__file__).resolve().parents[1]
        self.dataset_path = dataset_path or (
            base_dir / "data" / "quiz_question_template_normalized.ndjson"
        )
        self._questions = self._load_questions()
        self._question_by_id = {
            item["question_id"]: item
            for item in self._questions
            if item.get("question_id")
        }
        self._session_order: Dict[str, List[str]] = {}
        self._session_option_orders: Dict[str, Dict[str, List[dict[str, Any]]]] = {}

    def _load_questions(self) -> list[dict[str, Any]]:
        if not self.dataset_path.exists():
            return []

        rows: list[dict[str, Any]] = []
        with self.dataset_path.open("r", encoding="utf-8") as stream:
            for raw_line in stream:
                line = raw_line.strip()
                if not line:
                    continue

                try:
                    value = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if not isinstance(value, dict):
                    continue

                payload = value.get("payload")
                metadata = value.get("metadata")
                if not isinstance(payload, dict) or not isinstance(metadata, dict):
                    continue

                source_id = str(metadata.get("source_question_id") or "").strip()
                if not source_id:
                    continue

                question_type = str(value.get("question_type") or "").strip().upper()
                if question_type not in {
                    "MULTIPLE_CHOICE",
                    "SHORT_ANSWER",
                    "TRUE_FALSE_CLUSTER",
                }:
                    continue

                difficulty_level = int(value.get("difficulty_level", 2) or 2)
                if difficulty_level <= 1:
                    difficulty = "easy"
                elif difficulty_level == 2:
                    difficulty = "medium"
                else:
                    difficulty = "hard"

                rows.append(
                    {
                        "question_id": source_id,
                        "question_type": question_type,
                        "difficulty": difficulty,
                        "difficulty_level": difficulty_level,
                        "content": str(value.get("content") or ""),
                        "payload": payload,
                        "media_url": value.get("media_url"),
                        "metadata": metadata,
                    }
                )

        return rows

    def get_question_count(self) -> int:
        return len(self._questions)

    def build_or_get_session_order(
        self,
        session_id: str,
        mode: str,
        total_questions: int,
    ) -> list[str]:
        cached = self._session_order.get(session_id)
        if cached:
            return cached

        selected = select_quiz_questions_for_mode(
            question_pool=self._questions,
            mode=mode,
            num_questions=total_questions,
        )
        question_ids = [
            str(item.get("question_id") or "").strip()
            for item in selected
            if str(item.get("question_id") or "").strip()
        ]

        if not question_ids:
            # Fallback to deterministic first-N if selector returns empty.
            question_ids = [
                item["question_id"]
                for item in self._questions[: max(1, int(total_questions or 1))]
            ]

        self._session_order[session_id] = question_ids
        return question_ids

    def get_question_for_session(
        self,
        session_id: str,
        mode: str,
        index: int,
        total_questions: int,
    ) -> dict[str, Any] | None:
        order = self.build_or_get_session_order(session_id, mode, total_questions)
        if not order:
            return None

        safe_index = max(0, int(index or 0))
        if safe_index >= len(order):
            return None

        question_id = order[safe_index]
        question = self._question_by_id.get(question_id)
        if not question:
            return None

        return self._sanitize_question_for_delivery(session_id, question, safe_index, len(order))

    def _sanitize_question_for_delivery(
        self,
        session_id: str,
        question: dict[str, Any],
        index: int,
        total: int,
    ) -> dict[str, Any]:
        payload = question.get("payload")
        if not isinstance(payload, dict):
            payload = {}

        response: dict[str, Any] = {
            "session_id": session_id,
            "question_id": question["question_id"],
            "question_type": question["question_type"],
            "difficulty_level": int(question.get("difficulty_level", 2) or 2),
            "content": str(question.get("content") or ""),
            "media_url": question.get("media_url"),
            "index": int(index),
            "total_questions": int(total),
            "progress_percent": int(round(((index + 1) / max(1, total)) * 100)),
        }

        question_type = response["question_type"]
        if question_type == "MULTIPLE_CHOICE":
            options = payload.get("options")
            if not isinstance(options, list):
                options = []

            order_map = self._session_option_orders.setdefault(session_id, {})
            if response["question_id"] not in order_map:
                cloned = [
                    {
                        "id": str(item.get("id") or "").strip(),
                        "text": str(item.get("text") or ""),
                    }
                    for item in options
                    if isinstance(item, dict)
                ]
                random.shuffle(cloned)
                order_map[response["question_id"]] = cloned

            response["options"] = order_map.get(response["question_id"], [])

        elif question_type == "TRUE_FALSE_CLUSTER":
            sub_questions = payload.get("sub_questions")
            if not isinstance(sub_questions, list):
                sub_questions = []
            response["sub_questions"] = [
                {
                    "id": str(item.get("id") or "").strip(),
                    "text": str(item.get("text") or ""),
                }
                for item in sub_questions
                if isinstance(item, dict)
            ]
            response["general_hint"] = payload.get("general_hint")

        return response

    def submit_answer(
        self,
        session_id: str,
        question_id: str,
        selected_option: str | None = None,
        short_answer: str | None = None,
        cluster_answers: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_question_id = str(question_id or "").strip()
        question = self._question_by_id.get(normalized_question_id)
        if not question:
            raise ValueError("question_id_not_found")

        payload = question.get("payload")
        if not isinstance(payload, dict):
            payload = {}

        question_type = str(question.get("question_type") or "").upper()
        explanation = str(payload.get("explanation") or "").strip()

        if question_type == "MULTIPLE_CHOICE":
            correct_option_id = str(payload.get("correct_option_id") or "").strip().upper()
            selected = str(selected_option or "").strip().upper()
            if not selected:
                raise ValueError("selected_option_required")
            is_correct = selected == correct_option_id

        elif question_type == "SHORT_ANSWER":
            accepted_answers = payload.get("accepted_answers")
            if not isinstance(accepted_answers, list):
                accepted_answers = []
            exact_answer = payload.get("exact_answer")
            if exact_answer is not None:
                accepted_answers = [exact_answer, *accepted_answers]

            normalized_accepted = {
                str(item).strip().lower()
                for item in accepted_answers
                if str(item).strip()
            }
            submitted = str(short_answer or "").strip().lower()
            if not submitted:
                raise ValueError("short_answer_required")
            is_correct = submitted in normalized_accepted

        elif question_type == "TRUE_FALSE_CLUSTER":
            sub_questions = payload.get("sub_questions")
            if not isinstance(sub_questions, list):
                sub_questions = []

            if not isinstance(cluster_answers, dict):
                raise ValueError("cluster_answers_required")

            is_correct = True
            for item in sub_questions:
                if not isinstance(item, dict):
                    continue
                sub_id = str(item.get("id") or "").strip()
                expected = bool(item.get("is_true", False))
                actual = cluster_answers.get(sub_id)
                if actual is None:
                    is_correct = False
                    continue
                if bool(actual) != expected:
                    is_correct = False

        else:
            raise ValueError("unsupported_question_type")

        return {
            "session_id": session_id,
            "question_id": normalized_question_id,
            "question_type": question_type,
            "is_correct": bool(is_correct),
            "explanation": explanation,
        }


quiz_service = QuizService()
