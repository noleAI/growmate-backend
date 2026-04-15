from typing import Any, Dict, List


class FormulaRecommender:
    """Recommend formulas for weak hypotheses using a temporary in-code catalog."""

    HYPOTHESIS_FORMULA_MAP: Dict[str, List[Dict[str, str]]] = {
        "H01_Trig": [
            {
                "formulaId": "sin_derivative",
                "title": "Dao ham sin x",
                "formula": "(sin x)' = cos x",
            },
            {
                "formulaId": "cos_derivative",
                "title": "Dao ham cos x",
                "formula": "(cos x)' = -sin x",
            },
            {
                "formulaId": "tan_derivative",
                "title": "Dao ham tan x",
                "formula": "(tan x)' = sec^2 x",
            },
        ],
        "H02_ExpLog": [
            {
                "formulaId": "exp_derivative",
                "title": "Dao ham e^x",
                "formula": "(e^x)' = e^x",
            },
            {
                "formulaId": "ln_derivative",
                "title": "Dao ham ln x",
                "formula": "(ln x)' = 1/x",
            },
        ],
        "H03_Chain": [
            {
                "formulaId": "chain_rule_basic",
                "title": "Quy tac chuoi co ban",
                "formula": "(f(g(x)))' = f'(g(x)) * g'(x)",
            },
            {
                "formulaId": "chain_rule_trig",
                "title": "Quy tac chuoi voi luong giac",
                "formula": "(sin(u(x)))' = cos(u(x)) * u'(x)",
            },
        ],
        "H04_Rules": [
            {
                "formulaId": "sum_rule",
                "title": "Quy tac tong hieu",
                "formula": "(u +/- v)' = u' +/- v'",
            },
            {
                "formulaId": "product_rule",
                "title": "Quy tac tich",
                "formula": "(u*v)' = u'*v + u*v'",
            },
            {
                "formulaId": "quotient_rule",
                "title": "Quy tac thuong",
                "formula": "(u/v)' = (u'*v - u*v')/v^2",
            },
        ],
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

            for formula in self.HYPOTHESIS_FORMULA_MAP.get(hypothesis, []):
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
