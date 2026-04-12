import logging
import time
from typing import Any, Callable, Dict, List, Optional

import numpy as np
from pydantic import BaseModel

from agents.base import AgentInput, AgentOutput, IAgent
from agents.empathy_agent.likelihood import default_log_likelihood

logger = logging.getLogger("empathy.pf")


class PFState(BaseModel):
    confusion: float
    fatigue: float
    uncertainty: float
    ess: float
    particle_cloud: List[List[float]]
    weights: List[float]


class ParticleFilter(IAgent):
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        num_particles: int = 100,
        likelihood_fn: Optional[Callable[[np.ndarray, Dict[str, float]], np.ndarray]] = None,
    ):
        cfg = config or {}
        self.n = int(cfg.get("n_particles", num_particles))
        self.sigma_process = float(cfg.get("process_noise", 0.05))
        self.jitter_sigma = float(cfg.get("jitter_sigma", 0.01))
        self.ess_threshold = float(cfg.get("ess_threshold_ratio", 0.5))
        self.bounds = cfg.get("state_bounds", {"confusion": [0.0, 1.0], "fatigue": [0.0, 1.0]})
        self.likelihood_fn = likelihood_fn or default_log_likelihood

        self.particles = np.random.rand(self.n, 2)
        self.weights = np.ones(self.n, dtype=float) / self.n
        self.step = 0

    @property
    def name(self) -> str:
        return "empathy"

    async def process(self, input_data: AgentInput) -> AgentOutput:
        start_time = time.perf_counter()
        signals = input_data.behavior_signals or {}

        self.predict()
        self.update(signals, self.likelihood_fn)

        resample_triggered = self.should_resample()
        if resample_triggered:
            self.resample()

        state = self.get_state()
        latency_ms = int((time.perf_counter() - start_time) * 1000)

        logger.info(
            "[empathy] step=%s ess=%.2f uncertainty=%.3f resample_triggered=%s latency=%sms",
            self.step,
            state.ess,
            state.uncertainty,
            resample_triggered,
            latency_ms,
        )

        confidence = float(np.clip(1.0 - state.uncertainty, 0.0, 1.0))
        payload = state.model_dump()
        payload.update(
            {
                "q_state": self.discretize_for_q(state),
                "resample_triggered": resample_triggered,
                "step": self.step,
            }
        )

        return AgentOutput(
            action="empathy_tracked",
            payload=payload,
            confidence=confidence,
            metadata={"latency_ms": latency_ms},
        )

    def predict(self) -> None:
        """State transition with process noise for confusion and fatigue."""
        noise = np.random.randn(self.n, 2) * self.sigma_process
        self.particles = self.particles + noise
        self.particles = np.clip(self.particles, 0.0, 1.0)
        self.step += 1

    def update(
        self,
        signals: Dict[str, float],
        likelihood_fn: Callable[[np.ndarray, Dict[str, float]], np.ndarray],
    ) -> None:
        """Update particle weights using log-likelihood for numerical stability."""
        try:
            log_weights = likelihood_fn(self.particles, signals)
            if log_weights.shape[0] != self.n:
                raise ValueError("likelihood function returned invalid shape")

            safe_log_weights = np.where(np.isfinite(log_weights), log_weights, -1e12)
            shifted = safe_log_weights - np.max(safe_log_weights)
            new_weights = np.exp(shifted)
            new_weights = new_weights + 1e-12
            normalizer = float(np.sum(new_weights))

            if normalizer <= 0.0 or not np.isfinite(normalizer):
                raise ValueError("invalid weight normalizer")

            self.weights = new_weights / normalizer
        except Exception as exc:
            logger.warning("PF update failed: %s. Falling back to uniform weights.", exc)
            self.weights = np.ones(self.n, dtype=float) / self.n

    def resample(self) -> None:
        """Systematic resampling plus jitter to avoid degeneracy collapse."""
        positions = (np.arange(self.n) + np.random.rand()) / self.n
        cumulative_weights = np.cumsum(self.weights)
        indices = np.searchsorted(cumulative_weights, positions)
        self.particles = self.particles[indices].copy()
        self.weights = np.ones(self.n, dtype=float) / self.n

        jitter = np.random.randn(self.n, 2) * self.jitter_sigma
        self.particles = np.clip(self.particles + jitter, 0.0, 1.0)

    def should_resample(self) -> bool:
        ess = 1.0 / np.sum(np.square(self.weights))
        return bool(ess < (self.n * self.ess_threshold))

    def get_state(self) -> PFState:
        """Return weighted PF estimate and observability metrics."""
        ess = 1.0 / np.sum(np.square(self.weights))
        uncertainty = 1.0 - (ess / self.n)

        return PFState(
            confusion=float(np.average(self.particles[:, 0], weights=self.weights)),
            fatigue=float(np.average(self.particles[:, 1], weights=self.weights)),
            uncertainty=float(np.clip(uncertainty, 0.0, 1.0)),
            ess=float(ess),
            particle_cloud=self.particles.tolist(),
            weights=self.weights.tolist(),
        )

    def discretize_for_q(self, state: Optional[PFState] = None) -> str:
        """Convert continuous PF estimate into Q-table key."""
        pf_state = state or self.get_state()
        confusion = "high" if pf_state.confusion > 0.5 else "low"
        fatigue = "high" if pf_state.fatigue > 0.6 else "low"
        return f"{confusion}_confusion_{fatigue}_fatigue"

    def reset(self, explicit_feedback: Optional[Dict[str, float]] = None) -> None:
        """Reset particle cloud for new sessions or explicit corrective feedback."""
        self.particles = np.random.rand(self.n, 2)
        self.weights = np.ones(self.n, dtype=float) / self.n
        self.step = 0

        if explicit_feedback:
            confusion = float(explicit_feedback.get("confusion", 0.5))
            fatigue = float(explicit_feedback.get("fatigue", 0.5))
            target = np.array([confusion, fatigue], dtype=float)
            self.particles = self.particles * 0.5 + 0.5 * target
            self.particles = np.clip(self.particles, 0.0, 1.0)

    def get_state_summary(self) -> Dict[str, float]:
        """Backward-compatible summary used by legacy callers."""
        state = self.get_state()
        return {
            "confusion": state.confusion,
            "fatigue": state.fatigue,
            "uncertainty_score": state.uncertainty,
            "ess": state.ess,
        }


particle_filter = ParticleFilter()
