from __future__ import annotations

ALLOWED_MODES = {"exam_prep", "explore"}


def normalize_learning_mode(raw_mode: str | None, default: str = "explore") -> str:
    normalized_default = str(default or "explore").strip().lower()
    if normalized_default not in ALLOWED_MODES:
        normalized_default = "explore"

    if raw_mode is None:
        return normalized_default

    normalized = str(raw_mode).strip().lower()
    if not normalized:
        return normalized_default

    # Backward-compat mapping from previous mode naming.
    if normalized == "normal":
        return "explore"

    if normalized not in ALLOWED_MODES:
        return ""

    return normalized
