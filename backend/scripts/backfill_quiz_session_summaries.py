from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.supabase_client import (
    get_supabase_client,
    list_quiz_question_attempts,
    update_learning_session_progress,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill quiz summary/attempts into learning_sessions.state_snapshot "
            "for completed or abandoned sessions."
        )
    )
    parser.add_argument(
        "--statuses",
        nargs="+",
        default=["completed", "abandoned"],
        help="Session statuses to include (default: completed abandoned)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=200,
        help="Number of sessions to fetch per page (default: 200)",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=0,
        help="Max rows to scan (0 = no limit)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Rebuild summary even if snapshot already has quiz_state.summary",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compute and print stats only, without writing to DB.",
    )
    return parser.parse_args()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _normalize_attempt_row(row: dict[str, Any]) -> dict[str, Any]:
    evaluation = row.get("evaluation") if isinstance(row.get("evaluation"), dict) else {}
    user_answer = row.get("user_answer") if isinstance(row.get("user_answer"), dict) else {}
    question_id = str(
        row.get("question_id")
        or evaluation.get("question_id")
        or user_answer.get("question_id")
        or row.get("question_template_id")
        or ""
    )

    return {
        "question_id": question_id,
        "question_template_id": str(row.get("question_template_id") or ""),
        "question_type": str(row.get("question_type") or ""),
        "is_correct": bool(row.get("is_correct", False)),
        "score": float(row.get("score") or 0.0),
        "max_score": float(row.get("max_score") or 0.0),
        "explanation": str(evaluation.get("explanation") or ""),
        "user_answer": user_answer,
        "submitted_at": row.get("submitted_at"),
        "time_taken_sec": row.get("time_taken_sec"),
    }


def _build_summary(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    answered_count = len(attempts)
    correct_count = int(sum(1 for item in attempts if bool(item.get("is_correct", False))))
    total_score = float(sum(float(item.get("score") or 0.0) for item in attempts))
    max_score = float(sum(float(item.get("max_score") or 0.0) for item in attempts))

    accuracy_percent = 0
    if answered_count > 0:
        accuracy_percent = int(round((correct_count / answered_count) * 100))

    return {
        "answered_count": int(answered_count),
        "correct_count": int(correct_count),
        "total_score": round(total_score, 4),
        "max_score": round(max_score, 4),
        "accuracy_percent": int(max(0, min(100, accuracy_percent))),
    }


async def _list_sessions_page(
    statuses: list[str],
    offset: int,
    batch_size: int,
) -> list[dict[str, Any]]:
    normalized_statuses = [
        str(status).strip().lower() for status in statuses if str(status).strip()
    ]

    def _select() -> list[dict[str, Any]]:
        response = (
            get_supabase_client()
            .table("learning_sessions")
            .select(
                "id,student_id,status,last_question_index,total_questions,progress_percent,last_interaction_at,state_snapshot"
            )
            .in_("status", normalized_statuses)
            .order("start_time", desc=False)
            .range(offset, offset + batch_size - 1)
            .execute()
        )
        rows = getattr(response, "data", []) or []
        return [row for row in rows if isinstance(row, dict)]

    return await asyncio.to_thread(_select)


async def run_backfill(args: argparse.Namespace) -> None:
    statuses = [str(status).strip().lower() for status in args.statuses if str(status).strip()]
    batch_size = max(1, int(args.batch_size or 1))
    max_rows = max(0, int(args.max_rows or 0))

    scanned = 0
    updated = 0
    skipped_missing_ids = 0
    skipped_existing_summary = 0
    skipped_no_attempts = 0
    skipped_write_errors = 0

    offset = 0
    while True:
        if max_rows > 0 and scanned >= max_rows:
            break

        rows = await _list_sessions_page(statuses=statuses, offset=offset, batch_size=batch_size)
        if not rows:
            break

        for row in rows:
            if max_rows > 0 and scanned >= max_rows:
                break

            scanned += 1

            session_id = str(row.get("id") or "").strip()
            student_id = str(row.get("student_id") or "").strip()
            if not session_id or not student_id:
                skipped_missing_ids += 1
                continue

            snapshot = row.get("state_snapshot")
            if not isinstance(snapshot, dict):
                snapshot = {}

            quiz_state = snapshot.get("quiz_state")
            if not isinstance(quiz_state, dict):
                quiz_state = {}

            has_summary = isinstance(quiz_state.get("summary"), dict)
            if has_summary and not bool(args.force):
                skipped_existing_summary += 1
                continue

            try:
                attempts_rows = await list_quiz_question_attempts(
                    session_id=session_id,
                    student_id=student_id,
                    limit=500,
                )
            except Exception as exc:  # noqa: BLE001
                skipped_write_errors += 1
                print(
                    f"[WARN] Failed to load attempts session_id={session_id} student_id={student_id}: {exc}"
                )
                continue

            attempts = [_normalize_attempt_row(item) for item in attempts_rows]
            if not attempts:
                skipped_no_attempts += 1
                continue

            summary = _build_summary(attempts)
            quiz_state["attempts"] = attempts
            quiz_state["summary"] = summary
            quiz_state["updated_at"] = datetime.now(UTC).isoformat()
            snapshot["quiz_state"] = quiz_state

            if bool(args.dry_run):
                updated += 1
                continue

            try:
                await update_learning_session_progress(
                    session_id=session_id,
                    student_id=student_id,
                    last_question_index=_safe_int(row.get("last_question_index"), default=0),
                    total_questions=max(1, _safe_int(row.get("total_questions"), default=10)),
                    progress_percent=max(0, min(100, _safe_int(row.get("progress_percent"), default=0))),
                    last_interaction_at=row.get("last_interaction_at") or datetime.now(UTC),
                    state_snapshot=snapshot,
                    access_token=None,
                )
                updated += 1
            except Exception as exc:  # noqa: BLE001
                skipped_write_errors += 1
                print(
                    f"[WARN] Failed to update snapshot session_id={session_id} student_id={student_id}: {exc}"
                )

        offset += batch_size

    print("=== Backfill Summary ===")
    print(f"scanned={scanned}")
    print(f"updated={updated}")
    print(f"skipped_existing_summary={skipped_existing_summary}")
    print(f"skipped_no_attempts={skipped_no_attempts}")
    print(f"skipped_missing_ids={skipped_missing_ids}")
    print(f"skipped_write_errors={skipped_write_errors}")
    print(f"dry_run={bool(args.dry_run)}")


def main() -> None:
    args = parse_args()
    asyncio.run(run_backfill(args))


if __name__ == "__main__":
    main()
