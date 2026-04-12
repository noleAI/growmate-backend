from typing import Dict

import numpy as np


def _as_finite_float(value):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(numeric):
        return None
    return numeric


# Placeholder likelihood model. Domain-specific observation mapping can replace this.
def default_log_likelihood(
    particles: np.ndarray, signals: Dict[str, float]
) -> np.ndarray:
    confusion = particles[:, 0]
    fatigue = particles[:, 1]

    log_w = np.zeros(particles.shape[0], dtype=float)

    response_time_ms = _as_finite_float(signals.get("response_time_ms"))
    if response_time_ms is not None:
        expected_rt = 3000.0 + 12000.0 * fatigue + 4000.0 * confusion
        rt_sigma = 4000.0
        log_w += -((response_time_ms - expected_rt) ** 2) / (2.0 * rt_sigma**2)

    incorrect_attempts = _as_finite_float(signals.get("incorrect_attempts"))
    if incorrect_attempts is not None:
        expected_incorrect = 0.5 + 3.0 * confusion + fatigue
        incorrect_sigma = 1.5
        log_w += -((incorrect_attempts - expected_incorrect) ** 2) / (
            2.0 * incorrect_sigma**2
        )

    confidence_slider = _as_finite_float(signals.get("confidence_slider"))
    if confidence_slider is not None:
        expected_confidence = 1.0 - (0.7 * confusion + 0.3 * fatigue)
        confidence_sigma = 0.2
        log_w += -((confidence_slider - expected_confidence) ** 2) / (
            2.0 * confidence_sigma**2
        )

    error_rate = _as_finite_float(signals.get("error_rate"))
    if error_rate is not None:
        expected_error = 0.2 + 0.6 * confusion
        error_sigma = 0.15
        log_w += -((error_rate - expected_error) ** 2) / (2.0 * error_sigma**2)

    correction_rate = _as_finite_float(signals.get("correction_rate"))
    if correction_rate is not None:
        expected_correction = 0.7 - 0.5 * confusion
        correction_sigma = 0.2
        log_w += -((correction_rate - expected_correction) ** 2) / (
            2.0 * correction_sigma**2
        )

    idle_time_ratio = _as_finite_float(signals.get("idle_time_ratio"))
    if idle_time_ratio is not None:
        expected_idle = 0.1 + 0.4 * fatigue
        idle_sigma = 0.15
        log_w += -((idle_time_ratio - expected_idle) ** 2) / (2.0 * idle_sigma**2)

    return log_w
