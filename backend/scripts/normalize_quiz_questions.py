from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_PATH = ROOT_DIR / "data" / "quiz_question_template_normalized.ndjson"

KEY_ORDER = [
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

LATEX_FUNCTIONS = ("sin", "cos", "tan", "cot", "sec", "csc", "ln", "log")


def infer_hypothesis_tag(tags: list[Any]) -> str | None:
    normalized_tags = {
        str(tag).strip().lower()
        for tag in tags
        if isinstance(tag, str) and str(tag).strip()
    }

    if normalized_tags & {
        "trigonometry",
        "trigonometric_function",
        "double_angle_formula",
    }:
        return "H01_Trig"

    if normalized_tags & {
        "exponential_function",
        "logarithm",
        "exp",
    }:
        return "H02_ExpLog"

    if normalized_tags & {
        "chain_rule",
        "composition",
        "nested",
    }:
        return "H03_Chain"

    if normalized_tags & {
        "power_rule",
        "product_rule",
        "quotient_rule",
        "rules",
        "calculus",
    }:
        return "H04_Rules"

    return None


def normalize_math_text(text: str) -> str:
    updated = text

    updated = updated.replace("<=>", r"\\Leftrightarrow")
    updated = updated.replace("=>", r"\\Rightarrow")

    updated = re.sub(
        r"(?<!\\)sqrt\(([^()]+)\)",
        r"\\sqrt{\1}",
        updated,
    )

    for fn_name in LATEX_FUNCTIONS:
        updated = re.sub(
            rf"(?<!\\){fn_name}\s*\(",
            rf"\\{fn_name}(",
            updated,
        )

    updated = re.sub(
        r"(?<!\\)\b(sin|cos|tan|cot|sec|csc|ln|log)\s*(x|u|t)\b",
        r"\\\1 \2",
        updated,
    )

    updated = re.sub(
        r"\\(sin|cos|tan|cot|sec|csc|ln|log)([A-Za-z0-9])",
        r"\\\1 \2",
        updated,
    )

    updated = re.sub(r"([A-Za-z])'(?=\()", r"\1^{\\prime}", updated)
    updated = re.sub(r"\^\{([A-Za-z])(\d+)\}", r"^{\1^\2}", updated)
    updated = re.sub(r"(?<![A-Za-z\\])pi(?![A-Za-z])", r"\\pi", updated)
    updated = re.sub(r"\\pi(?=[A-Za-z])", r"\\pi\\", updated)

    return updated


def normalize_recursive(value: Any) -> Any:
    if isinstance(value, str):
        return normalize_math_text(value)

    if isinstance(value, list):
        return [normalize_recursive(item) for item in value]

    if isinstance(value, dict):
        return {key: normalize_recursive(item) for key, item in value.items()}

    return value


def reorder_record(record: dict[str, Any]) -> dict[str, Any]:
    ordered: dict[str, Any] = {}

    for key in KEY_ORDER:
        if key == "grade_level":
            continue
        if key in record:
            ordered[key] = record[key]

    for key, value in record.items():
        if key not in ordered and key != "grade_level":
            ordered[key] = value

    ordered["grade_level"] = str(record.get("grade_level") or "11")
    return ordered


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_recursive(record)

    normalized["grade_level"] = str(normalized.get("grade_level") or "11")

    metadata = normalized.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    tags = metadata.get("tags")
    if not isinstance(tags, list):
        tags = []
        metadata["tags"] = tags

    if not metadata.get("hypothesis_tag"):
        inferred_hypothesis = infer_hypothesis_tag(tags)
        if inferred_hypothesis:
            metadata["hypothesis_tag"] = inferred_hypothesis

    normalized["metadata"] = metadata
    return reorder_record(normalized)


def load_ndjson(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            row = json.loads(stripped)
            if not isinstance(row, dict):
                raise ValueError(
                    f"Expected JSON object at line {line_number}, got {type(row)!r}"
                )
            rows.append(row)

    return rows


def write_ndjson(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False))
            stream.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize quiz NDJSON and enforce grade_level/hypothesis tags."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT_PATH,
        help=f"Input NDJSON file (default: {DEFAULT_INPUT_PATH})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output NDJSON file. If omitted, writes to '<input>_latex.ndjson'.",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Rewrite the input file in-place.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path: Path = args.input.resolve()
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if args.in_place and args.output is not None:
        raise ValueError("Use either --in-place or --output, not both.")

    output_path = args.output
    if output_path is None and not args.in_place:
        output_path = input_path.with_name(
            f"{input_path.stem}_latex{input_path.suffix}"
        )

    rows = load_ndjson(input_path)
    normalized_rows: list[dict[str, Any]] = []
    changed_count = 0

    for row in rows:
        normalized_row = normalize_record(row)
        if normalized_row != row:
            changed_count += 1
        normalized_rows.append(normalized_row)

    if args.in_place:
        temp_path = input_path.with_suffix(".tmp")
        write_ndjson(temp_path, normalized_rows)
        temp_path.replace(input_path)
        target_path = input_path
    else:
        assert output_path is not None
        write_ndjson(output_path, normalized_rows)
        target_path = output_path

    print(f"Total records: {len(normalized_rows)}")
    print(f"Changed records: {changed_count}")
    print(f"Output file: {target_path}")


if __name__ == "__main__":
    main()
