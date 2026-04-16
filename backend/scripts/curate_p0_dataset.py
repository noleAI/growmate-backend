from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT_DIR / "data" / "quiz_question_template_normalized.ndjson"
DEFAULT_CRAWL_TIME = "2026-04-15T09:00:00Z"

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


def _ordered_record(record: dict[str, Any]) -> dict[str, Any]:
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


def _build_metadata(source_id: str, tags: list[str], hypothesis_tag: str) -> dict[str, Any]:
    return {
        "source_question_id": source_id,
        "source_provider": "growmate_curated",
        "crawl_time": DEFAULT_CRAWL_TIME,
        "quality_status": "reviewed",
        "tags": tags,
        "hypothesis_tag": hypothesis_tag,
    }


def _build_mcq(
    source_id: str,
    difficulty: int,
    content: str,
    options: list[dict[str, str]],
    correct_option_id: str,
    explanation: str,
    tags: list[str],
    hypothesis_tag: str,
) -> dict[str, Any]:
    return _ordered_record(
        {
            "subject": "math",
            "topic_code": "derivative",
            "topic_name": "Đạo hàm",
            "exam_year": 2026,
            "question_type": "MULTIPLE_CHOICE",
            "part_no": 1,
            "difficulty_level": difficulty,
            "content": content,
            "media_url": None,
            "payload": {
                "options": options,
                "correct_option_id": correct_option_id,
                "explanation": explanation,
            },
            "metadata": _build_metadata(source_id, tags, hypothesis_tag),
            "is_active": True,
            "grade_level": "11",
        }
    )


def _build_short_answer(
    source_id: str,
    difficulty: int,
    content: str,
    exact_answer: str,
    accepted_answers: list[str],
    explanation: str,
    tags: list[str],
    hypothesis_tag: str,
) -> dict[str, Any]:
    return _ordered_record(
        {
            "subject": "math",
            "topic_code": "derivative",
            "topic_name": "Đạo hàm",
            "exam_year": 2026,
            "question_type": "SHORT_ANSWER",
            "part_no": 3,
            "difficulty_level": difficulty,
            "content": content,
            "media_url": None,
            "payload": {
                "exact_answer": exact_answer,
                "accepted_answers": accepted_answers,
                "explanation": explanation,
            },
            "metadata": _build_metadata(source_id, tags, hypothesis_tag),
            "is_active": True,
            "grade_level": "11",
        }
    )


def _curated_records() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    # H01 - Trigonometry (6 records)
    records.append(
        _build_mcq(
            source_id="MATH_DERIV_51",
            difficulty=2,
            content="Cho hàm số y = \\sin(3x). Giá trị của y^{\\prime}(0) bằng",
            options=[
                {"id": "A", "text": "0"},
                {"id": "B", "text": "1"},
                {"id": "C", "text": "3"},
                {"id": "D", "text": "9"},
            ],
            correct_option_id="C",
            explanation="Ta có y^{\\prime} = 3\\cos(3x). Thay x = 0 suy ra y^{\\prime}(0) = 3\\cos 0 = 3.",
            tags=["trigonometry", "trigonometric_function", "calculation"],
            hypothesis_tag="H01_Trig",
        )
    )
    records.append(
        _build_mcq(
            source_id="MATH_DERIV_52",
            difficulty=3,
            content="Cho y = \\cos(2x). Giá trị của y^{\\prime} tại x = \\pi/3 là",
            options=[
                {"id": "A", "text": "-\\sqrt{3}"},
                {"id": "B", "text": "\\sqrt{3}"},
                {"id": "C", "text": "-1"},
                {"id": "D", "text": "1"},
            ],
            correct_option_id="A",
            explanation="y^{\\prime} = -2\\sin(2x). Tại x = \\pi/3 thì y^{\\prime} = -2\\sin(2\\pi/3) = -2\\cdot \\sqrt{3}/2 = -\\sqrt{3}.",
            tags=["trigonometry", "trigonometric_function", "derivative_values"],
            hypothesis_tag="H01_Trig",
        )
    )
    records.append(
        _build_mcq(
            source_id="MATH_DERIV_53",
            difficulty=1,
            content="Đạo hàm của hàm số y = \\tan x tại x = 0 bằng",
            options=[
                {"id": "A", "text": "0"},
                {"id": "B", "text": "1"},
                {"id": "C", "text": "-1"},
                {"id": "D", "text": "\\sqrt{2}"},
            ],
            correct_option_id="B",
            explanation="(\\tan x)' = \\sec^2 x. Tại x = 0: \\sec^2 0 = 1.",
            tags=["trigonometry", "rules", "basic"],
            hypothesis_tag="H01_Trig",
        )
    )
    records.append(
        _build_mcq(
            source_id="MATH_DERIV_54",
            difficulty=2,
            content="Cho y = \\sin x \\cdot \\cos x. Giá trị của y^{\\prime}(\\pi/4) là",
            options=[
                {"id": "A", "text": "0"},
                {"id": "B", "text": "1"},
                {"id": "C", "text": "-1"},
                {"id": "D", "text": "1/2"},
            ],
            correct_option_id="A",
            explanation="y = \\frac{1}{2}\\sin(2x) nên y^{\\prime} = \\cos(2x). Tại x = \\pi/4: y^{\\prime} = \\cos(\\pi/2) = 0.",
            tags=["trigonometry", "product_rule", "calculation"],
            hypothesis_tag="H01_Trig",
        )
    )
    records.append(
        _build_mcq(
            source_id="MATH_DERIV_55",
            difficulty=3,
            content="Với y = 2\\sin x + 3\\cos x, công thức đúng của y^{\\prime\\prime} là",
            options=[
                {"id": "A", "text": "2\\sin x - 3\\cos x"},
                {"id": "B", "text": "-2\\sin x - 3\\cos x"},
                {"id": "C", "text": "-2\\cos x + 3\\sin x"},
                {"id": "D", "text": "2\\cos x + 3\\sin x"},
            ],
            correct_option_id="B",
            explanation="y^{\\prime} = 2\\cos x - 3\\sin x, tiếp tục lấy đạo hàm được y^{\\prime\\prime} = -2\\sin x - 3\\cos x.",
            tags=["trigonometry", "second_order_derivative", "rules"],
            hypothesis_tag="H01_Trig",
        )
    )
    records.append(
        _build_short_answer(
            source_id="MATH_DERIV_56",
            difficulty=3,
            content="Cho y = \\sin x + \\cos x. Trong khoảng (0; 2\\pi), phương trình y^{\\prime}=0 có bao nhiêu nghiệm?",
            exact_answer="2",
            accepted_answers=["2"],
            explanation="Ta có y^{\\prime} = \\cos x - \\sin x = 0 \\Leftrightarrow \\tan x = 1. Trong (0; 2\\pi), nghiệm là x = \\pi/4 và x = 5\\pi/4 nên có 2 nghiệm.",
            tags=["trigonometry", "trigonometric_equation", "derivative_values"],
            hypothesis_tag="H01_Trig",
        )
    )

    # H02 - Exponential & logarithm (7 records)
    records.append(
        _build_mcq(
            source_id="MATH_DERIV_57",
            difficulty=1,
            content="Đạo hàm của hàm số y = e^{2x} là",
            options=[
                {"id": "A", "text": "e^{2x}"},
                {"id": "B", "text": "2e^{2x}"},
                {"id": "C", "text": "2xe^{2x}"},
                {"id": "D", "text": "e^{x}"},
            ],
            correct_option_id="B",
            explanation="Áp dụng chain rule cho e^{u}: (e^{u})' = e^{u}u'. Với u = 2x thì u' = 2, do đó y' = 2e^{2x}.",
            tags=["exponential_function", "rules", "basic"],
            hypothesis_tag="H02_ExpLog",
        )
    )
    records.append(
        _build_mcq(
            source_id="MATH_DERIV_58",
            difficulty=2,
            content="Cho y = \\ln(3x+1). Giá trị y^{\\prime}(0) bằng",
            options=[
                {"id": "A", "text": "1/3"},
                {"id": "B", "text": "1"},
                {"id": "C", "text": "3"},
                {"id": "D", "text": "0"},
            ],
            correct_option_id="C",
            explanation="y' = \\frac{3}{3x+1}. Tại x = 0 suy ra y'(0) = 3.",
            tags=["logarithm", "calculation", "derivative_values"],
            hypothesis_tag="H02_ExpLog",
        )
    )
    records.append(
        _build_mcq(
            source_id="MATH_DERIV_59",
            difficulty=2,
            content="Đạo hàm của y = 5^x tại x=1 bằng",
            options=[
                {"id": "A", "text": "5"},
                {"id": "B", "text": "\\ln 5"},
                {"id": "C", "text": "5\\ln 5"},
                {"id": "D", "text": "1/(5\\ln 5)"},
            ],
            correct_option_id="C",
            explanation="(a^x)' = a^x\\ln a. Tại x=1: y' = 5^1\\ln 5 = 5\\ln 5.",
            tags=["exponential_function", "rules", "derivative_values"],
            hypothesis_tag="H02_ExpLog",
        )
    )
    records.append(
        _build_mcq(
            source_id="MATH_DERIV_60",
            difficulty=3,
            content="Cho y = xe^x. Giá trị y^{\\prime}(1) là",
            options=[
                {"id": "A", "text": "e"},
                {"id": "B", "text": "2e"},
                {"id": "C", "text": "e^2"},
                {"id": "D", "text": "1+e"},
            ],
            correct_option_id="B",
            explanation="Theo product rule: y' = e^x + xe^x = (x+1)e^x. Tại x=1 ta có y'(1)=2e.",
            tags=["exponential_function", "product_rule", "calculation"],
            hypothesis_tag="H02_ExpLog",
        )
    )
    records.append(
        _build_mcq(
            source_id="MATH_DERIV_61",
            difficulty=2,
            content="Cho y = \\ln(x^2+1). Giá trị y^{\\prime}(1) bằng",
            options=[
                {"id": "A", "text": "1"},
                {"id": "B", "text": "2"},
                {"id": "C", "text": "1/2"},
                {"id": "D", "text": "3/2"},
            ],
            correct_option_id="A",
            explanation="y' = \\frac{2x}{x^2+1}. Tại x=1 được y'(1)=\\frac{2}{2}=1.",
            tags=["logarithm", "chain_rule", "calculation"],
            hypothesis_tag="H02_ExpLog",
        )
    )
    records.append(
        _build_mcq(
            source_id="MATH_DERIV_62",
            difficulty=3,
            content="Cho y = \\ln x + mx. Tìm m để y^{\\prime}(1)=0.",
            options=[
                {"id": "A", "text": "m = -1"},
                {"id": "B", "text": "m = 0"},
                {"id": "C", "text": "m = 1"},
                {"id": "D", "text": "m = 2"},
            ],
            correct_option_id="A",
            explanation="y' = \\frac{1}{x}+m nên y'(1)=1+m. Điều kiện y'(1)=0 suy ra m=-1.",
            tags=["logarithm", "parameter", "derivative_values"],
            hypothesis_tag="H02_ExpLog",
        )
    )
    records.append(
        _build_short_answer(
            source_id="MATH_DERIV_63",
            difficulty=3,
            content="Với y = 2^x, hãy tính y^{\\prime}(0).",
            exact_answer="ln(2)",
            accepted_answers=["ln(2)", "\\ln(2)", "0.6931"],
            explanation="Theo công thức (a^x)' = a^x\\ln a nên y' = 2^x\\ln 2. Tại x=0 ta được y'(0)=\\ln 2.",
            tags=["exponential_function", "derivative_values", "rules"],
            hypothesis_tag="H02_ExpLog",
        )
    )

    # H03 - Chain rule (10 records)
    records.append(
        _build_mcq(
            source_id="MATH_DERIV_64",
            difficulty=2,
            content="Đạo hàm của y = (3x-1)^5 là",
            options=[
                {"id": "A", "text": "5(3x-1)^4"},
                {"id": "B", "text": "15(3x-1)^4"},
                {"id": "C", "text": "15(3x-1)^5"},
                {"id": "D", "text": "(3x-1)^4"},
            ],
            correct_option_id="B",
            explanation="Áp dụng chain rule: [(u)^5]' = 5u^4u'. Với u=3x-1, u'=3 nên y'=15(3x-1)^4.",
            tags=["chain_rule", "composition", "power_rule"],
            hypothesis_tag="H03_Chain",
        )
    )
    records.append(
        _build_mcq(
            source_id="MATH_DERIV_65",
            difficulty=2,
            content="Đạo hàm của y = \\sqrt{2x+1} là",
            options=[
                {"id": "A", "text": "\\frac{1}{2\\sqrt{2x+1}}"},
                {"id": "B", "text": "\\frac{1}{\\sqrt{2x+1}}"},
                {"id": "C", "text": "\\frac{2}{\\sqrt{2x+1}}"},
                {"id": "D", "text": "\\sqrt{2x+1}"},
            ],
            correct_option_id="B",
            explanation="y = (2x+1)^{1/2} nên y' = \\frac{1}{2}(2x+1)^{-1/2}\\cdot 2 = \\frac{1}{\\sqrt{2x+1}}.",
            tags=["chain_rule", "sqrt", "composition"],
            hypothesis_tag="H03_Chain",
        )
    )
    records.append(
        _build_mcq(
            source_id="MATH_DERIV_66",
            difficulty=2,
            content="Cho y = \\sin(x^2). Giá trị y^{\\prime}(1) bằng",
            options=[
                {"id": "A", "text": "\\cos 1"},
                {"id": "B", "text": "2\\cos 1"},
                {"id": "C", "text": "2\\sin 1"},
                {"id": "D", "text": "\\sin 1"},
            ],
            correct_option_id="B",
            explanation="Theo chain rule, y' = \\cos(x^2)\\cdot 2x. Tại x=1 ta được y'(1)=2\\cos 1.",
            tags=["chain_rule", "trigonometric_function", "derivative_values"],
            hypothesis_tag="H03_Chain",
        )
    )
    records.append(
        _build_mcq(
            source_id="MATH_DERIV_67",
            difficulty=3,
            content="Cho y = e^{x^2+1}. Giá trị y^{\\prime}(0) là",
            options=[
                {"id": "A", "text": "0"},
                {"id": "B", "text": "e"},
                {"id": "C", "text": "2e"},
                {"id": "D", "text": "1"},
            ],
            correct_option_id="A",
            explanation="y' = e^{x^2+1}\\cdot 2x. Tại x=0 thì hệ số 2x bằng 0 nên y'(0)=0.",
            tags=["chain_rule", "exponential_function", "composition"],
            hypothesis_tag="H03_Chain",
        )
    )
    records.append(
        _build_mcq(
            source_id="MATH_DERIV_68",
            difficulty=3,
            content="Cho y = \\ln(1+3x^2). Giá trị y^{\\prime}(1) bằng",
            options=[
                {"id": "A", "text": "3/2"},
                {"id": "B", "text": "6"},
                {"id": "C", "text": "1/2"},
                {"id": "D", "text": "2"},
            ],
            correct_option_id="A",
            explanation="y' = \\frac{6x}{1+3x^2}. Tại x=1, y'(1)=\\frac{6}{4}=\\frac{3}{2}.",
            tags=["chain_rule", "logarithm", "composition"],
            hypothesis_tag="H03_Chain",
        )
    )
    records.append(
        _build_mcq(
            source_id="MATH_DERIV_69",
            difficulty=3,
            content="Cho y = (x^2+1)^3. Giá trị y^{\\prime}(1) là",
            options=[
                {"id": "A", "text": "12"},
                {"id": "B", "text": "24"},
                {"id": "C", "text": "16"},
                {"id": "D", "text": "6"},
            ],
            correct_option_id="B",
            explanation="y' = 3(x^2+1)^2\\cdot 2x = 6x(x^2+1)^2. Tại x=1 được y'(1)=6\\cdot1\\cdot4=24.",
            tags=["chain_rule", "power_rule", "composition"],
            hypothesis_tag="H03_Chain",
        )
    )
    records.append(
        _build_mcq(
            source_id="MATH_DERIV_70",
            difficulty=3,
            content="Đạo hàm của y = \\cos(3x^2-1) là",
            options=[
                {"id": "A", "text": "-\\sin(3x^2-1)"},
                {"id": "B", "text": "-6x\\sin(3x^2-1)"},
                {"id": "C", "text": "6x\\cos(3x^2-1)"},
                {"id": "D", "text": "6x\\sin(3x^2-1)"},
            ],
            correct_option_id="B",
            explanation="Theo chain rule: (\\cos u)' = -\\sin u\\cdot u'. Với u=3x^2-1, u'=6x nên y'=-6x\\sin(3x^2-1).",
            tags=["chain_rule", "trigonometric_function", "composition"],
            hypothesis_tag="H03_Chain",
        )
    )
    records.append(
        _build_short_answer(
            source_id="MATH_DERIV_71",
            difficulty=2,
            content="Cho y = (2x+1)^4. Tính y^{\\prime}(0).",
            exact_answer="8",
            accepted_answers=["8"],
            explanation="y' = 4(2x+1)^3\\cdot 2 = 8(2x+1)^3. Tại x=0, y'(0)=8.",
            tags=["chain_rule", "power_rule", "derivative_values"],
            hypothesis_tag="H03_Chain",
        )
    )
    records.append(
        _build_short_answer(
            source_id="MATH_DERIV_72",
            difficulty=3,
            content="Cho y = (mx+1)^3. Tìm m để y^{\\prime}(0)=6.",
            exact_answer="2",
            accepted_answers=["2"],
            explanation="Ta có y' = 3(mx+1)^2\\cdot m. Tại x=0: y'(0)=3m. Điều kiện 3m=6 suy ra m=2.",
            tags=["chain_rule", "parameter", "composition"],
            hypothesis_tag="H03_Chain",
        )
    )
    records.append(
        _build_mcq(
            source_id="MATH_DERIV_73",
            difficulty=3,
            content="Cho y = e^{\\sin x}. Giá trị y^{\\prime}(0) bằng",
            options=[
                {"id": "A", "text": "0"},
                {"id": "B", "text": "1"},
                {"id": "C", "text": "e"},
                {"id": "D", "text": "2"},
            ],
            correct_option_id="B",
            explanation="y' = e^{\\sin x}\\cdot \\cos x. Tại x=0: y'(0)=e^0\\cdot1=1.",
            tags=["chain_rule", "exponential_function", "trigonometric_function"],
            hypothesis_tag="H03_Chain",
        )
    )

    return records


def _load_rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _apply_existing_fixes(rows: list[dict[str, Any]]) -> int:
    changed = 0
    for row in rows:
        metadata = row.get("metadata")
        if not isinstance(metadata, dict):
            continue
        source_id = str(metadata.get("source_question_id", ""))

        if source_id == "MATH_DERIV_6":
            payload = row.get("payload") or {}
            old = str(payload.get("explanation") or "")
            new = old.replace("v(4) = 84 = 32", "v(4) = 8\\cdot4 = 32")
            if new != old:
                payload["explanation"] = new
                row["payload"] = payload
                changed += 1

        if source_id == "MATH_DERIV_27":
            payload = row.get("payload") or {}
            new_text = "Hàm số hằng y = 1 có đạo hàm bằng 0 tại mọi điểm, nên đáp án đúng là 0."
            if str(payload.get("explanation") or "") != new_text:
                payload["explanation"] = new_text
                row["payload"] = payload
                changed += 1

        if source_id == "MATH_DERIV_45":
            payload = row.get("payload") or {}
            sub_questions = payload.get("sub_questions") or []
            if isinstance(sub_questions, list):
                explanation_by_id = {
                    "a": "v(t)=3t^{2}-6t+7 nên v(2)=12-12+7=7 m/s, mệnh đề đúng.",
                    "b": "a(t)=v^{\\prime}(t)=6t-6 nên a(2)=6 m/s^{2}, mệnh đề đúng.",
                    "c": "v=16 cho t=3 (vì t>0), khi đó a(3)=12 khác 10 nên mệnh đề sai.",
                    "d": "v(t) là parabol mở lên, đạt min tại t=-b/(2a)=1 nên mệnh đề đúng.",
                }
                updated_any = False
                for sq in sub_questions:
                    if not isinstance(sq, dict):
                        continue
                    sq_id = str(sq.get("id", ""))
                    new_ex = explanation_by_id.get(sq_id)
                    if new_ex and str(sq.get("explanation") or "") != new_ex:
                        sq["explanation"] = new_ex
                        updated_any = True
                if updated_any:
                    payload["sub_questions"] = sub_questions
                    row["payload"] = payload
                    changed += 1

    return changed


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(_ordered_record(row), ensure_ascii=False))
            stream.write("\n")


def main() -> None:
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {DATASET_PATH}")

    rows = _load_rows(DATASET_PATH)
    existing_by_id = {
        str((row.get("metadata") or {}).get("source_question_id", "")): row
        for row in rows
    }

    fixed_count = _apply_existing_fixes(rows)

    new_records = _curated_records()
    appended_count = 0
    for record in new_records:
        source_id = str((record.get("metadata") or {}).get("source_question_id", ""))
        if source_id in existing_by_id:
            continue
        rows.append(record)
        existing_by_id[source_id] = record
        appended_count += 1

    _write_rows(DATASET_PATH, rows)

    print(f"Fixed existing records: {fixed_count}")
    print(f"Appended new records: {appended_count}")
    print(f"Total records now: {len(rows)}")


if __name__ == "__main__":
    main()
