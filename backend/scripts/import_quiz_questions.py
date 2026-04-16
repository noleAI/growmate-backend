from __future__ import annotations

import argparse
import json
import sys
import uuid
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.supabase_client import get_supabase_client

DEFAULT_INPUT_PATH = ROOT_DIR / "data" / "quiz_question_template_normalized.ndjson"
UPSERT_NAMESPACE = uuid.UUID("1f7fd34d-a75f-4ad7-9d49-9b280f4c31a4")

REQUIRED_KEYS = {
    "subject",
    "topic_code",
    "topic_name",
    "exam_year",
    "question_type",
    "part_no",
    "difficulty_level",
    "content",
    "payload",
    "metadata",
    "is_active",
}

ALLOWED_QUESTION_TYPES = {
    "MULTIPLE_CHOICE",
    "TRUE_FALSE_CLUSTER",
    "SHORT_ANSWER",
}

DB_KEY_ORDER = [
    "id",
    "subject",
    "topic_code",
    "topic_name",
    "exam_year",
    "question_type",
    "part_no",
    "difficulty_level",
    "content",
    "media_url",
    "payload",
    "metadata",
    "is_active",
    "grade_level",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import normalized quiz questions into Supabase with deterministic IDs."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help=f"Input NDJSON file (default: {DEFAULT_INPUT_PATH})",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=50,
        help="Number of records per upsert batch.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and prepare payloads without writing to Supabase.",
    )
    return parser.parse_args()


def load_ndjson(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            value = json.loads(stripped)
            if not isinstance(value, dict):
                raise ValueError(
                    f"Line {line_number}: expected object, got {type(value)!r}"
                )

            rows.append(value)

    return rows


def validate_record(record: dict[str, Any], line_number: int) -> None:
    missing = [key for key in REQUIRED_KEYS if key not in record]
    if missing:
        raise ValueError(f"Line {line_number}: missing required keys {missing}")

    question_type = str(record.get("question_type", "")).strip()
    if question_type not in ALLOWED_QUESTION_TYPES:
        raise ValueError(
            f"Line {line_number}: unsupported question_type '{question_type}'"
        )

    if not isinstance(record.get("payload"), dict):
        raise ValueError(f"Line {line_number}: payload must be a JSON object")

    if not isinstance(record.get("metadata"), dict):
        raise ValueError(f"Line {line_number}: metadata must be a JSON object")

    source_question_id = record["metadata"].get("source_question_id")
    if not source_question_id:
        raise ValueError(
            f"Line {line_number}: metadata.source_question_id is required"
        )


def build_deterministic_id(source_question_id: str) -> str:
    return str(uuid.uuid5(UPSERT_NAMESPACE, source_question_id.strip()))


def reorder_import_payload(record: dict[str, Any]) -> dict[str, Any]:
    ordered: dict[str, Any] = {}

    for key in DB_KEY_ORDER:
        if key == "grade_level":
            continue
        if key in record:
            ordered[key] = record[key]

    for key, value in record.items():
        if key not in ordered and key != "grade_level":
            ordered[key] = value

    ordered["grade_level"] = str(record.get("grade_level") or "11")
    return ordered


def prepare_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    prepared: list[dict[str, Any]] = []

    for line_number, row in enumerate(rows, start=1):
        validate_record(row, line_number)
        metadata = row.get("metadata", {})
        source_question_id = str(metadata["source_question_id"])

        candidate = dict(row)
        candidate["id"] = build_deterministic_id(source_question_id)
        candidate["grade_level"] = str(candidate.get("grade_level") or "11")
        prepared.append(reorder_import_payload(candidate))

    return prepared


def chunked(rows: list[dict[str, Any]], chunk_size: int) -> list[list[dict[str, Any]]]:
    return [rows[index : index + chunk_size] for index in range(0, len(rows), chunk_size)]


def upsert_rows(rows: list[dict[str, Any]], chunk_size: int) -> int:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")

    client = get_supabase_client()
    batches = chunked(rows, chunk_size)
    upserted_count = 0

    for batch_index, batch in enumerate(batches, start=1):
        client.table("quiz_question_template").upsert(
            batch,
            on_conflict="id",
        ).execute()
        upserted_count += len(batch)
        print(
            f"Upserted batch {batch_index}/{len(batches)} "
            f"({len(batch)} records)"
        )

    return upserted_count


def main() -> None:
    args = parse_args()
    input_path = args.input.resolve()

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    rows = load_ndjson(input_path)
    prepared_rows = prepare_rows(rows)

    print(f"Loaded records: {len(rows)}")
    print(f"Prepared records: {len(prepared_rows)}")

    if args.dry_run:
        print("Dry run enabled. No data was written to Supabase.")
        return

    upserted = upsert_rows(prepared_rows, chunk_size=args.chunk_size)
    print(f"Import finished. Upserted records: {upserted}")


if __name__ == "__main__":
    main()
