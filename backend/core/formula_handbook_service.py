from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from core.supabase_client import (
    get_user_xp,
    list_agent_state_rows,
    list_learning_session_ids,
)

logger = logging.getLogger("core.formula_handbook")

HYPOTHESES = ["H01_Trig", "H02_ExpLog", "H03_Chain", "H04_Rules"]

DEFAULT_CATEGORIES = [
    {
        "id": "basic_derivatives",
        "name": "Đạo hàm cơ bản",
        "description": "Hằng số, lũy thừa, căn bậc hai và dạng đa thức cơ bản.",
        "formula_ids": [
            "constant_derivative",
            "power_rule",
            "linear_derivative",
            "root_derivative",
            "reciprocal_derivative",
            "polynomial_combo",
        ],
    },
    {
        "id": "arithmetic_rules",
        "name": "Quy tắc tính",
        "description": "Tổng, hiệu, tích, thương trong đạo hàm.",
        "formula_ids": [
            "sum_rule",
            "difference_rule",
            "product_rule",
            "quotient_rule",
        ],
    },
    {
        "id": "basic_trig",
        "name": "Đạo hàm lượng giác",
        "description": "Các công thức sin, cos, tan và biến thể hàm hợp.",
        "formula_ids": [
            "sin_derivative",
            "cos_derivative",
            "tan_derivative",
            "cot_derivative",
            "sec_derivative",
            "csc_derivative",
            "sin_composite",
            "cos_composite",
        ],
    },
    {
        "id": "exp_log",
        "name": "Đạo hàm mũ và logarit",
        "description": "Công thức e^x, a^x, ln, log và dạng hàm hợp liên quan.",
        "formula_ids": [
            "exp_derivative",
            "a_pow_x_derivative",
            "ln_derivative",
            "log_a_x_derivative",
            "exp_composite",
            "ln_composite",
            "x_pow_x_derivative",
        ],
    },
    {
        "id": "chain_rule",
        "name": "Quy tắc chain rule",
        "description": "Quy tắc đạo hàm hàm hợp từ cơ bản đến nâng cao.",
        "formula_ids": [
            "chain_rule_general",
            "chain_square",
            "chain_sqrt",
            "chain_sin",
            "chain_ln",
            "implicit_chain",
            "nested_chain",
        ],
    },
]

ALLOWED_CATEGORY_IDS = {
    "all",
    "basic_derivatives",
    "arithmetic_rules",
    "basic_trig",
    "exp_log",
    "chain_rule",
}


class FormulaHandbookService:
    def __init__(
        self,
        lookup_path: Path | None = None,
        handbook_path: Path | None = None,
    ) -> None:
        base_dir = Path(__file__).resolve().parents[1]
        self.lookup_path = lookup_path or (base_dir / "data" / "formula_lookup.json")
        self.handbook_path = handbook_path or (base_dir / "data" / "formula_handbook.json")

        self._formulas = self._load_lookup_formulas()
        self._formula_by_id = {item["id"]: item for item in self._formulas}
        self._categories = self._load_categories()

    @staticmethod
    def normalize_category(raw_category: str) -> str:
        category = str(raw_category or "all").strip().lower()
        return category if category in ALLOWED_CATEGORY_IDS else ""

    async def get_catalog_for_user(
        self,
        user_id: str,
        category: str,
        search: str | None,
        access_token: str | None = None,
    ) -> list[dict[str, Any]]:
        mastery_by_hypothesis = await self.get_mastery_by_hypothesis(
            user_id=user_id,
            access_token=access_token,
        )
        return self._build_catalog(
            category=category,
            search=search,
            mastery_by_hypothesis=mastery_by_hypothesis,
        )

    async def get_mastery_by_hypothesis(
        self,
        user_id: str,
        access_token: str | None = None,
    ) -> dict[str, int]:
        if not user_id:
            return {key: 50 for key in HYPOTHESES}

        try:
            session_ids = await list_learning_session_ids(
                student_id=user_id,
                limit=30,
                access_token=access_token,
            )

            if session_ids:
                state_rows = await list_agent_state_rows(
                    session_ids=session_ids,
                    access_token=access_token,
                )
                mastery = self._mastery_from_agent_states(state_rows)
                if mastery:
                    return mastery

            xp_row = await get_user_xp(user_id=user_id, access_token=access_token)
            return self._mastery_from_xp(xp_row)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to resolve mastery for user=%s: %s", user_id, exc)
            return {key: 50 for key in HYPOTHESES}

    def _load_lookup_formulas(self) -> list[dict[str, Any]]:
        if not self.lookup_path.exists():
            logger.warning("Formula lookup not found: %s", self.lookup_path)
            return []

        try:
            with self.lookup_path.open("r", encoding="utf-8") as stream:
                raw = json.load(stream)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to read formula lookup %s: %s", self.lookup_path, exc)
            return []

        if not isinstance(raw, list):
            logger.warning("Invalid formula lookup shape in %s", self.lookup_path)
            return []

        normalized: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue

            formula_id = str(item.get("id") or "").strip()
            latex = str(item.get("latex") or "").strip()
            if not formula_id or not latex:
                continue

            normalized.append(
                {
                    "id": formula_id,
                    "title": str(item.get("title") or formula_id).strip(),
                    "latex": latex,
                    "explanation": str(item.get("explanation") or "").strip(),
                    "example": str(item.get("example") or "").strip(),
                    "related_hypothesis": str(
                        item.get("related_hypothesis") or "H04_Rules"
                    ).strip(),
                    "difficulty": str(item.get("difficulty") or "medium").strip().lower(),
                    "keywords": [
                        str(keyword).strip()
                        for keyword in item.get("keywords", [])
                        if isinstance(keyword, str) and str(keyword).strip()
                    ],
                }
            )

        return normalized

    def _load_categories(self) -> list[dict[str, Any]]:
        if not self.handbook_path.exists():
            return [dict(item) for item in DEFAULT_CATEGORIES]

        try:
            with self.handbook_path.open("r", encoding="utf-8") as stream:
                payload = json.load(stream)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to read handbook config %s: %s", self.handbook_path, exc)
            return [dict(item) for item in DEFAULT_CATEGORIES]

        raw_categories = payload.get("categories") if isinstance(payload, dict) else None
        if not isinstance(raw_categories, list):
            return [dict(item) for item in DEFAULT_CATEGORIES]

        categories: list[dict[str, Any]] = []
        for item in raw_categories:
            if not isinstance(item, dict):
                continue

            category_id = str(item.get("id") or "").strip().lower()
            if category_id not in ALLOWED_CATEGORY_IDS:
                continue

            formula_ids = [
                str(formula_id).strip()
                for formula_id in item.get("formula_ids", [])
                if isinstance(formula_id, str) and str(formula_id).strip()
            ]

            categories.append(
                {
                    "id": category_id,
                    "name": str(item.get("name") or category_id).strip(),
                    "description": str(item.get("description") or "").strip(),
                    "formula_ids": formula_ids,
                }
            )

        return categories or [dict(item) for item in DEFAULT_CATEGORIES]

    def _build_catalog(
        self,
        category: str,
        search: str | None,
        mastery_by_hypothesis: dict[str, int],
    ) -> list[dict[str, Any]]:
        normalized_search = str(search or "").strip().lower()

        categories: list[dict[str, Any]] = []
        for item in self._categories:
            if category != "all" and item["id"] != category:
                continue

            formulas: list[dict[str, Any]] = []
            for formula_id in item.get("formula_ids", []):
                formula = self._formula_by_id.get(formula_id)
                if not formula:
                    continue

                if normalized_search and not self._matches_search(
                    formula=formula,
                    search_text=normalized_search,
                ):
                    continue

                hypothesis = str(formula.get("related_hypothesis") or "H04_Rules")
                mastery_percent = int(mastery_by_hypothesis.get(hypothesis, 50))
                formulas.append(
                    {
                        "id": formula["id"],
                        "title": formula["title"],
                        "latex": formula["latex"],
                        "explanation": formula["explanation"],
                        "example": formula["example"],
                        "example_latex": formula["example"],
                        "related_hypothesis": hypothesis,
                        "difficulty": formula["difficulty"],
                        "keywords": formula.get("keywords", []),
                        "mastery_percent": mastery_percent,
                        "mastery_status": self._to_mastery_status(mastery_percent),
                    }
                )

            if not formulas and category != "all":
                categories.append(
                    {
                        "id": item["id"],
                        "name": item["name"],
                        "description": item["description"],
                        "formula_count": 0,
                        "mastery_percent": 0,
                        "formulas": [],
                    }
                )
                continue

            if not formulas:
                continue

            category_mastery = int(
                round(sum(item["mastery_percent"] for item in formulas) / len(formulas))
            )
            categories.append(
                {
                    "id": item["id"],
                    "name": item["name"],
                    "description": item["description"],
                    "formula_count": len(formulas),
                    "mastery_percent": category_mastery,
                    "formulas": formulas,
                }
            )

        return categories

    @staticmethod
    def _matches_search(formula: dict[str, Any], search_text: str) -> bool:
        haystack = [
            str(formula.get("id") or ""),
            str(formula.get("title") or ""),
            str(formula.get("latex") or ""),
            str(formula.get("explanation") or ""),
            str(formula.get("example") or ""),
        ]
        haystack.extend(str(item) for item in formula.get("keywords", []))

        combined = " ".join(haystack).lower()
        return search_text in combined

    @staticmethod
    def _to_mastery_status(mastery_percent: int) -> str:
        value = max(0, min(100, int(mastery_percent)))
        if value >= 80:
            return "learned"
        if value >= 50:
            return "learning"
        return "locked"

    @staticmethod
    def _parse_belief_dist(value: Any) -> dict[str, float] | None:
        raw = value
        if isinstance(value, str):
            try:
                raw = json.loads(value)
            except json.JSONDecodeError:
                return None

        if not isinstance(raw, dict):
            return None

        parsed: dict[str, float] = {}
        for hypothesis in HYPOTHESES:
            try:
                parsed[hypothesis] = float(raw.get(hypothesis, 0.0))
            except (TypeError, ValueError):
                parsed[hypothesis] = 0.0
        return parsed

    def _mastery_from_agent_states(
        self,
        state_rows: list[dict[str, Any]],
    ) -> dict[str, int] | None:
        if not state_rows:
            return None

        totals = {key: 0.0 for key in HYPOTHESES}
        counts = {key: 0 for key in HYPOTHESES}

        for row in state_rows:
            if not isinstance(row, dict):
                continue
            belief_dist = self._parse_belief_dist(row.get("belief_dist"))
            if not belief_dist:
                continue

            for hypothesis, value in belief_dist.items():
                totals[hypothesis] += max(0.0, min(1.0, value))
                counts[hypothesis] += 1

        if sum(counts.values()) == 0:
            return None

        mastery: dict[str, int] = {}
        for hypothesis in HYPOTHESES:
            if counts[hypothesis] == 0:
                mastery[hypothesis] = 50
                continue

            avg_weakness = totals[hypothesis] / counts[hypothesis]
            mastery[hypothesis] = int(round((1.0 - avg_weakness) * 100))

        return mastery

    @staticmethod
    def _mastery_from_xp(xp_row: dict[str, Any]) -> dict[str, int]:
        total_xp = int(xp_row.get("total_xp", 0) or 0)
        current_streak = int(xp_row.get("current_streak", 0) or 0)

        if total_xp >= 1500:
            base = 80
        elif total_xp >= 600:
            base = 60
        elif total_xp >= 200:
            base = 45
        else:
            base = 30

        streak_bonus = min(10, max(0, current_streak) * 2)
        value = max(0, min(100, base + streak_bonus))
        return {hypothesis: value for hypothesis in HYPOTHESES}


formula_handbook_service = FormulaHandbookService()
