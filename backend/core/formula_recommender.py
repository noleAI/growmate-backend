import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger("core.formula_recommender")


class FormulaRecommender:
    """Recommend formulas for weak hypotheses from a file-backed catalog."""

    _FALLBACK_HYPOTHESIS_FORMULA_MAP: Dict[str, List[Dict[str, str]]] = {
        "H01_Trig": [
            {
                "formulaId": "sin_derivative",
                "title": "Đạo hàm sin x",
                "formula": "(\\sin x)' = \\cos x",
            },
            {
                "formulaId": "cos_derivative",
                "title": "Đạo hàm cos x",
                "formula": "(\\cos x)' = -\\sin x",
            },
            {
                "formulaId": "tan_derivative",
                "title": "Đạo hàm tan x",
                "formula": "(\\tan x)' = \\sec^2 x",
            },
        ],
        "H02_ExpLog": [
            {
                "formulaId": "exp_derivative",
                "title": "Đạo hàm e^x",
                "formula": "(e^x)' = e^x",
            },
            {
                "formulaId": "ln_derivative",
                "title": "Đạo hàm ln x",
                "formula": "(\\ln x)' = 1/x",
            },
        ],
        "H03_Chain": [
            {
                "formulaId": "chain_rule_basic",
                "title": "Quy tắc chuỗi cơ bản",
                "formula": "(f(g(x)))' = f'(g(x)) \\cdot g'(x)",
            },
            {
                "formulaId": "chain_rule_trig",
                "title": "Quy tắc chuỗi với lượng giác",
                "formula": "(\\sin(u(x)))' = \\cos(u(x)) \\cdot u'(x)",
            },
        ],
        "H04_Rules": [
            {
                "formulaId": "sum_rule",
                "title": "Quy tắc tổng hiệu",
                "formula": "(u \\pm v)' = u' \\pm v'",
            },
            {
                "formulaId": "product_rule",
                "title": "Quy tắc tích",
                "formula": "(u\\cdot v)' = u'\\cdot v + u\\cdot v'",
            },
            {
                "formulaId": "quotient_rule",
                "title": "Quy tắc thương",
                "formula": "(u/v)' = (u'*v - u*v')/v^2",
            },
        ],
    }

    def __init__(self, formula_path: Path | None = None) -> None:
        self._formula_path = formula_path or (
            Path(__file__).resolve().parents[1] / "data" / "formula_lookup.json"
        )
        self.formula_map = self._load_formula_map()

    def _load_formula_map(self) -> Dict[str, List[Dict[str, str]]]:
        if not self._formula_path.exists():
            return self._fallback_formula_map()

        try:
            with self._formula_path.open("r", encoding="utf-8") as stream:
                payload = json.load(stream)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Cannot load formula catalog %s: %s", self._formula_path, exc)
            return self._fallback_formula_map()

        if not isinstance(payload, list):
            logger.warning(
                "Formula catalog has invalid shape (expected list) at %s",
                self._formula_path,
            )
            return self._fallback_formula_map()

        mapping: Dict[str, List[Dict[str, str]]] = {
            key: [] for key in self._FALLBACK_HYPOTHESIS_FORMULA_MAP
        }

        for item in payload:
            if not isinstance(item, dict):
                continue

            hypothesis = str(item.get("related_hypothesis", "")).strip()
            if hypothesis not in mapping:
                continue

            formula_id = str(item.get("id") or "").strip()
            title = str(item.get("title") or formula_id or "Formula").strip()
            latex = str(item.get("latex") or item.get("formula") or "").strip()
            if not formula_id or not latex:
                continue

            mapping[hypothesis].append(
                {
                    "formulaId": formula_id,
                    "title": title,
                    "formula": latex,
                }
            )

        total_entries = sum(len(items) for items in mapping.values())
        if total_entries == 0:
            logger.warning(
                "Formula catalog at %s has no valid entries. Using fallback map.",
                self._formula_path,
            )
            return self._fallback_formula_map()

        return mapping

    def _fallback_formula_map(self) -> Dict[str, List[Dict[str, str]]]:
        return {
            hypothesis: [dict(entry) for entry in entries]
            for hypothesis, entries in self._FALLBACK_HYPOTHESIS_FORMULA_MAP.items()
        }

    def recommend_formulas(
        self,
        belief_dist: Dict[str, float],
        threshold: float = 0.3,
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        if not belief_dist:
            return []

        recommendations: List[Dict[str, Any]] = []
        for hypothesis, raw_belief in belief_dist.items():
            try:
                belief = float(raw_belief)
            except (TypeError, ValueError):
                continue

            if belief >= threshold:
                continue

            for formula in self.formula_map.get(hypothesis, []):
                recommendations.append(
                    {
                        "formulaId": formula["formulaId"],
                        "title": formula["title"],
                        "formula": formula["formula"],
                        "hypothesis": hypothesis,
                        "belief": round(belief, 4),
                        "relevanceScore": round(max(0.0, min(1.0, 1.0 - belief)), 4),
                        "reason": f"belief<{threshold} for {hypothesis}",
                    }
                )

        recommendations.sort(
            key=lambda item: (item["relevanceScore"], -item["belief"]),
            reverse=True,
        )
        return recommendations[:limit]
