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

    return log_w
