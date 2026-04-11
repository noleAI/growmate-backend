import json
import math
import os
from agents.base import IAgent, AgentInput, AgentOutput

class BayesianTracker(IAgent):
    def __init__(self, prior: dict = None):
        # Load constraints from json
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        config_path = os.path.join(base_dir, "data", "derivative_priors.json")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                self.config = json.load(f)
            self.beliefs = prior or self.config["priors"].copy()
        except FileNotFoundError:
            self.config = {"likelihoods": {}}
            self.beliefs = prior or {"concept_a": 0.5, "concept_b": 0.5}

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
            confidence=1.0 - self.get_entropy() # Inversely proportional to entropy
        )
        
    def update_evidence(self, category: str, evidence: str) -> dict:
        if category in self.config.get("likelihoods", {}) and evidence in self.config["likelihoods"][category]:
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
        
    def reset(self):
        self.beliefs = self.config["priors"].copy() if "priors" in self.config else {"concept_a": 0.5, "concept_b": 0.5}
        
    def get_entropy(self) -> float:
        # Entropy = -sum(p * log(p))
        entropy = 0.0
        for p in self.beliefs.values():
            if p > 0:
                entropy -= p * math.log(p)
        return entropy
        
bayesian_tracker = BayesianTracker()
