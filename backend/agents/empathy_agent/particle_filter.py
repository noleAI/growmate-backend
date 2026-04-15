import logging
import time
from datetime import datetime, timezone
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
        self.bounds = cfg.get(
            "state_bounds", {"confusion": [0.0, 1.0], "fatigue": [0.0, 1.0]}
        )

        q_cfg = cfg.get("q_discretization", {})
        self.q_confusion_threshold = float(q_cfg.get("confusion_high", 0.5))
        self.q_fatigue_threshold = float(q_cfg.get("fatigue_high", 0.6))
        self.q_fallback_state = str(
            q_cfg.get("fallback_state", "low_confusion_low_fatigue")
        )

        self.uncertainty_override_threshold = float(
            cfg.get("uncertainty_override_threshold", 0.85)
        )
        self.override_action = str(cfg.get("override_action", "de_stress"))

        self.state_order = ["focused", "confused", "exhausted", "frustrated"]
        utility_cfg = cfg.get("utility", {})
        self.utility_actions = utility_cfg.get(
            "actions", ["continue_quiz", "show_hint", "suggest_break", "trigger_hitl"]
        )
        utility_matrix = utility_cfg.get(
            "matrix",
            [
                [1.0, 0.2, -0.5, -0.8],
                [0.1, 0.8, 0.4, 0.3],
                [-0.3, 0.3, 1.0, 0.6],
                [-0.5, -0.2, -0.1, -0.4],
            ],
        )
        self.tie_break_priority = utility_cfg.get(
            "tie_break_priority", ["show_hint", "suggest_break", "continue_quiz", "trigger_hitl"]
        )

        matrix = np.array(utility_matrix, dtype=float)
        if matrix.shape != (len(self.utility_actions), len(self.state_order)):
            logger.warning(
                "Invalid utility matrix shape %s. Falling back to default utility table.",
                matrix.shape,
            )
            matrix = np.array(
                [
                    [1.0, 0.2, -0.5, -0.8],
                    [0.1, 0.8, 0.4, 0.3],
                    [-0.3, 0.3, 1.0, 0.6],
                    [-0.5, -0.2, -0.1, -0.4],
                ],
                dtype=float,
            )
            self.utility_actions = [
                "continue_quiz",
                "show_hint",
                "suggest_break",
                "trigger_hitl",
            ]
        self.utility_matrix = matrix
        self.likelihood_fn = likelihood_fn or default_log_likelihood

        self.particles = np.random.rand(self.n, 2)
        self.weights = np.ones(self.n, dtype=float) / self.n
        self.step = 0

    @property
    def name(self) -> str:
        return "empathy"

    async def process(self, input_data: AgentInput) -> AgentOutput:
        start_time = time.perf_counter()
        raw_signals = input_data.behavior_signals or {}
        if not isinstance(raw_signals, dict):
            raw_signals = {}

        analytics_signals = self._derive_signals_from_analytics(input_data.analytics_data)
        signals = self._blend_signals(raw_signals, analytics_signals)

        signal_history = list(input_data.signal_history or [])
        if raw_signals:
            signal_history.append(dict(raw_signals))
        signal_history = signal_history[-5:]

        spam_detected = self.detect_spam(signal_history)
        afk_detected = self.detect_afk(input_data.last_signal_time)

        if spam_detected or afk_detected:
            state = self.get_state()
            confidence = float(np.clip(1.0 - state.uncertainty, 0.0, 1.0))
            belief_distribution = self._compute_state_belief(state)
            eu_values, recommended_action = self._compute_eu_values(belief_distribution)

            payload = state.model_dump()
            payload.update(
                {
                    "q_state": self.discretize_for_q(state),
                    "resample_triggered": False,
                    "step": self.step,
                    "belief_distribution": belief_distribution,
                    "particle_distribution": self._particle_distribution_histogram(),
                    "eu_values": eu_values,
                    "recommended_action": recommended_action,
                    "hitl_triggered": False,
                    "override_recommended_action": "de_stress",
                    "spam_detected": spam_detected,
                    "afk_detected": afk_detected,
                    "pause_recommended": True,
                }
            )

            return AgentOutput(
                action="empathy_tracked",
                payload=payload,
                confidence=confidence,
                metadata={
                    "latency_ms": int((time.perf_counter() - start_time) * 1000),
                    "spam_detected": spam_detected,
                    "afk_detected": afk_detected,
                    "analytics_signals_used": bool(analytics_signals),
                },
            )

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
        belief_distribution = self._compute_state_belief(state)
        eu_values, recommended_action = self._compute_eu_values(belief_distribution)
        hitl_triggered = state.uncertainty >= self.uncertainty_override_threshold

        payload = state.model_dump()
        payload.update(
            {
                "q_state": self.discretize_for_q(state),
                "resample_triggered": resample_triggered,
                "step": self.step,
                "belief_distribution": belief_distribution,
                "particle_distribution": self._particle_distribution_histogram(),
                "eu_values": eu_values,
                "recommended_action": recommended_action,
                "hitl_triggered": hitl_triggered,
                "override_recommended_action": self.override_action
                if hitl_triggered
                else None,
                "spam_detected": False,
                "afk_detected": False,
                "pause_recommended": False,
            }
        )

        return AgentOutput(
            action="empathy_tracked",
            payload=payload,
            confidence=confidence,
            metadata={
                "latency_ms": latency_ms,
                "analytics_signals_used": bool(analytics_signals),
            },
        )

    def _derive_signals_from_analytics(
        self, analytics_data: Optional[Dict[str, Any]]
    ) -> Dict[str, float]:
        if not isinstance(analytics_data, dict):
            return {}

        derived: Dict[str, float] = {}

        accuracy = self._extract_rate(
            analytics_data,
            ["accuracy_rate", "accuracy", "session_accuracy"],
        )
        if accuracy is not None:
            derived["error_rate"] = float(np.clip(1.0 - accuracy, 0.0, 1.0))

        correction_rate = self._extract_rate(
            analytics_data,
            ["correction_rate", "self_correction_rate"],
        )
        if correction_rate is not None:
            derived["correction_rate"] = correction_rate

        engagement = self._extract_rate(
            analytics_data,
            ["engagement_score", "engagement", "engagement_index"],
        )
        if engagement is not None:
            derived["confidence_slider"] = engagement
            derived["idle_time_ratio"] = float(np.clip(1.0 - engagement, 0.0, 1.0))

        idle_ratio = self._extract_rate(
            analytics_data,
            ["idle_time_ratio", "inactivity_ratio"],
        )
        if idle_ratio is not None:
            existing_idle = derived.get("idle_time_ratio", 0.0)
            derived["idle_time_ratio"] = max(existing_idle, idle_ratio)

        session_minutes = self._extract_float(
            analytics_data,
            ["session_time_minutes", "session_duration_minutes", "session_minutes"],
        )
        if session_minutes is not None:
            fatigue_proxy = float(np.clip(session_minutes / 90.0, 0.0, 1.0))
            existing_idle = derived.get("idle_time_ratio", 0.0)
            derived["idle_time_ratio"] = max(existing_idle, fatigue_proxy)

        return derived

    def _blend_signals(
        self,
        behavior_signals: Dict[str, Any],
        analytics_signals: Dict[str, float],
    ) -> Dict[str, float]:
        merged: Dict[str, float] = {}

        for key, value in behavior_signals.items():
            numeric = self._extract_float({key: value}, [key])
            if numeric is not None:
                merged[key] = numeric

        for key, value in analytics_signals.items():
            if key in merged:
                merged[key] = float(np.clip(0.7 * merged[key] + 0.3 * value, 0.0, 1.0))
            else:
                merged[key] = value

        return merged

    def _extract_float(
        self,
        data: Dict[str, Any],
        keys: List[str],
    ) -> Optional[float]:
        for key in keys:
            if key not in data:
                continue
            try:
                value = float(data[key])
            except (TypeError, ValueError):
                continue
            if np.isfinite(value):
                return value
        return None

    def _extract_rate(
        self,
        data: Dict[str, Any],
        keys: List[str],
    ) -> Optional[float]:
        value = self._extract_float(data, keys)
        if value is None:
            return None
        if value > 1.0:
            value = value / 100.0
        return float(np.clip(value, 0.0, 1.0))

    def detect_spam(self, signals: List[Dict[str, Any]]) -> bool:
        if not signals:
            return False

        consecutive_fast = 0
        max_consecutive_fast = 0
        correctness_samples: List[float] = []

        for signal in signals[-5:]:
            response_time_ms = float(signal.get("response_time_ms", 10000))
            if response_time_ms < 2000:
                consecutive_fast += 1
                max_consecutive_fast = max(max_consecutive_fast, consecutive_fast)
            else:
                consecutive_fast = 0

            if "is_correct" in signal:
                correctness_samples.append(1.0 if bool(signal.get("is_correct")) else 0.0)
            elif "correct" in signal:
                correctness_samples.append(1.0 if bool(signal.get("correct")) else 0.0)

        if max_consecutive_fast < 3:
            return False

        if not correctness_samples:
            return True

        accuracy = sum(correctness_samples) / len(correctness_samples)
        return accuracy < 0.2

    def detect_afk(self, last_signal_time: Optional[str]) -> bool:
        if not last_signal_time:
            return False

        try:
            if isinstance(last_signal_time, str):
                parsed = datetime.fromisoformat(last_signal_time.replace("Z", "+00:00"))
            else:
                return False
        except ValueError:
            return False

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)

        return (datetime.now(timezone.utc) - parsed).total_seconds() > 180

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
        confusion = "high" if pf_state.confusion > self.q_confusion_threshold else "low"
        fatigue = "high" if pf_state.fatigue > self.q_fatigue_threshold else "low"
        q_state = f"{confusion}_confusion_{fatigue}_fatigue"
        valid_states = {
            "low_confusion_low_fatigue",
            "low_confusion_high_fatigue",
            "high_confusion_low_fatigue",
            "high_confusion_high_fatigue",
        }
        if q_state not in valid_states:
            return self.q_fallback_state
        return q_state

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

    def _compute_state_belief(self, state: PFState) -> Dict[str, float]:
        # Map continuous [confusion, fatigue] estimate into 4-state belief bins.
        confusion = float(np.clip(state.confusion, 0.0, 1.0))
        fatigue = float(np.clip(state.fatigue, 0.0, 1.0))
        focused = (1.0 - confusion) * (1.0 - fatigue)
        confused = confusion * (1.0 - fatigue)
        exhausted = (1.0 - confusion) * fatigue
        frustrated = confusion * fatigue
        raw = np.array([focused, confused, exhausted, frustrated], dtype=float)
        total = float(np.sum(raw)) + 1e-12
        normalized = raw / total
        return {
            state_name: float(prob)
            for state_name, prob in zip(self.state_order, normalized, strict=False)
        }

    def _compute_eu_values(
        self, belief_distribution: Dict[str, float]
    ) -> tuple[Dict[str, float], str]:
        belief_vec = np.array(
            [belief_distribution[s] for s in self.state_order], dtype=float
        )
        eu_vector = self.utility_matrix @ belief_vec
        eu_values = {
            action: float(score)
            for action, score in zip(self.utility_actions, eu_vector, strict=False)
        }

        max_eu = float(np.max(eu_vector))
        candidate_indices = np.where(np.isclose(eu_vector, max_eu))[0]
        if len(candidate_indices) == 1:
            best_action = self.utility_actions[int(candidate_indices[0])]
            return eu_values, best_action

        candidate_actions = {self.utility_actions[int(i)] for i in candidate_indices}
        for action in self.tie_break_priority:
            if action in candidate_actions:
                return eu_values, action

        return eu_values, self.utility_actions[int(candidate_indices[0])]

    def _particle_distribution_histogram(self) -> List[float]:
        confusion_bucket = float(np.mean(self.particles[:, 0] > self.q_confusion_threshold))
        fatigue_bucket = float(np.mean(self.particles[:, 1] > self.q_fatigue_threshold))

        focused = float(
            np.mean(
                (self.particles[:, 0] <= self.q_confusion_threshold)
                & (self.particles[:, 1] <= self.q_fatigue_threshold)
            )
        )
        confused = float(
            np.mean(
                (self.particles[:, 0] > self.q_confusion_threshold)
                & (self.particles[:, 1] <= self.q_fatigue_threshold)
            )
        )
        exhausted = float(
            np.mean(
                (self.particles[:, 0] <= self.q_confusion_threshold)
                & (self.particles[:, 1] > self.q_fatigue_threshold)
            )
        )
        frustrated = float(
            np.mean(
                (self.particles[:, 0] > self.q_confusion_threshold)
                & (self.particles[:, 1] > self.q_fatigue_threshold)
            )
        )

        # Keep compatibility with legacy histogram consumers while exposing 4-state bins.
        return [
            focused,
            confused,
            exhausted,
            frustrated,
            confusion_bucket,
            fatigue_bucket,
        ]


particle_filter = ParticleFilter()
