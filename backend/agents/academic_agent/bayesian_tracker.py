import json
import math
import os
import re
from typing import Any, Dict, List

from agents.base import AgentInput, AgentOutput, IAgent


class BayesianTracker(IAgent):
    def __init__(self, prior: dict = None):
        fallback_priors = {
            "H01_Trig": 0.25,
            "H02_ExpLog": 0.25,
            "H03_Chain": 0.25,
            "H04_Rules": 0.25,
        }

        # Load constraints from json
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        config_path = os.path.join(base_dir, "data", "derivative_priors.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
            self.beliefs = prior or self.config["priors"].copy()
        except FileNotFoundError:
            self.config = {"likelihoods": {}}
            self.beliefs = prior or fallback_priors

    @property
    def name(self) -> str:
        return "bayesian"

    async def process(self, input_data: AgentInput) -> AgentOutput:
        # Analyze runtime evidence based on behavior signals
        # and trigger the math bayesian model.
        if input_data.user_response:
            evidence = input_data.user_response.get("evidence", "E_CORRECT")
            self.update_evidence("answer_pattern", evidence)

        return AgentOutput(
            action="belief_updated",
            payload={"belief_dist": self.beliefs},
            confidence=1.0 - self.get_entropy(),  # Inversely proportional to entropy
        )

    def update_evidence(self, category: str, evidence: str) -> dict:
        if (
            category in self.config.get("likelihoods", {})
            and evidence in self.config["likelihoods"][category]
        ):
            likelihoods = self.config["likelihoods"][category][evidence]

            # P(H|E) = (P(E|H) * P(H)) / P(E)
            unnormalized_posterior = {
                h: self.beliefs.get(h, 0.0) * likelihoods.get(h, 0.0)
                for h in self.beliefs
            }

            # Compute Evidence P(E)
            marginal_likelihood = sum(unnormalized_posterior.values())

            # Distribution normalization
            if marginal_likelihood > 0:
                self.beliefs = {
                    h: unnormalized_posterior[h] / marginal_likelihood
                    for h in self.beliefs
                }
        return self.beliefs

    def update_beliefs(self, action: str, outcome: dict) -> dict:
        # Mock bayesian update wrapper for old route compatibility
        evidence = outcome.get("evidence", "E_CORRECT")
        category = "answer_pattern" if action == "submit_answer" else "hint_used"
        return self.update_evidence(category, evidence)

    def apply_profile_prior(self, level: str) -> dict:
        profile_priors = {
            "beginner": {
                "H01_Trig": 0.35,
                "H02_ExpLog": 0.15,
                "H03_Chain": 0.10,
                "H04_Rules": 0.40,
            },
            "intermediate": {
                "H01_Trig": 0.25,
                "H02_ExpLog": 0.25,
                "H03_Chain": 0.25,
                "H04_Rules": 0.25,
            },
            "advanced": {
                "H01_Trig": 0.15,
                "H02_ExpLog": 0.20,
                "H03_Chain": 0.45,
                "H04_Rules": 0.20,
            },
        }

        selected = profile_priors.get(str(level).lower())
        if not selected:
            return self.beliefs

        total = sum(selected.values())
        if total <= 0:
            return self.beliefs

        self.beliefs = {k: v / total for k, v in selected.items()}
        return self.beliefs

    def update_from_error_chain(self, error_chain: List[Dict[str, Any]]) -> dict:
        if not error_chain:
            return self.beliefs

        level_weights = {
            "surface": 0.3,
            "root": 0.7,
            "foundation": 1.0,
        }

        evidence_strength = {hypothesis: 0.0 for hypothesis in self.beliefs}

        for error in error_chain:
            if not isinstance(error, dict):
                continue

            level = str(error.get("level", "root")).lower()
            description = str(error.get("description", ""))
            weight = float(level_weights.get(level, 0.5))

            target_hypothesis = self._map_error_to_hypothesis(description)
            evidence_strength[target_hypothesis] += weight

            # Foundation gaps can propagate to prerequisite rules competency.
            if level == "foundation" and target_hypothesis == "H03_Chain":
                evidence_strength["H04_Rules"] += 0.25 * weight

        likelihood = {
            hypothesis: 0.1 + evidence_strength.get(hypothesis, 0.0)
            for hypothesis in self.beliefs
        }
        unnormalized = {
            hypothesis: self.beliefs[hypothesis] * likelihood[hypothesis]
            for hypothesis in self.beliefs
        }
        marginal = sum(unnormalized.values())

        if marginal > 0:
            self.beliefs = {
                hypothesis: unnormalized[hypothesis] / marginal
                for hypothesis in self.beliefs
            }

        return self.beliefs

    def _map_error_to_hypothesis(self, description: str) -> str:
        text = description.lower()

        trig_pattern = re.compile(r"\b(sin|cos|tan|trig|luong\s*giac)\b")
        exp_log_pattern = re.compile(r"\b(exp|e\^x|ln|log|mu|power)\b")
        chain_pattern = re.compile(r"\b(chain|inner|ham\s*hop|composite)\b")
        rule_pattern = re.compile(r"\b(sum|difference|product|quotient|operator|rule)\b")

        if trig_pattern.search(text):
            return "H01_Trig"
        if exp_log_pattern.search(text):
            return "H02_ExpLog"
        if chain_pattern.search(text):
            return "H03_Chain"
        if rule_pattern.search(text):
            return "H04_Rules"
        return "H04_Rules"

    def reset(self):
        self.beliefs = (
            self.config["priors"].copy()
            if "priors" in self.config
            else {
                "H01_Trig": 0.25,
                "H02_ExpLog": 0.25,
                "H03_Chain": 0.25,
                "H04_Rules": 0.25,
            }
        )

    def get_entropy(self) -> float:
        # Entropy = -sum(p * log(p))
        entropy = 0.0
        for p in self.beliefs.values():
            if p > 0:
                entropy -= p * math.log(p)
        return entropy


bayesian_tracker = BayesianTracker()
