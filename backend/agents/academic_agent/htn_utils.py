"""
HTN Utilities: Safe precondition evaluation for HTN Planner.

Provides safe_eval_precondition() that evaluates YAML-defined precondition
strings (e.g. "entropy < 0.85 AND fatigue < 0.75") against a context
dictionary, with protection against code injection.
"""

import logging
import re

logger = logging.getLogger("htn_utils")

# Allowed tokens: variable names (alpha + underscore), numbers, comparisons, AND/OR, parens, spaces
_SAFE_TOKEN_PATTERN = re.compile(r"^[\w\s\.\<\>\=\!]+$")

# Dangerous patterns to reject
_DANGEROUS_PATTERNS = [
    "__import__",
    "import ",
    "exec(",
    "eval(",
    "open(",
    "os.",
    "sys.",
    "subprocess",
    "__builtins__",
    "__class__",
    "getattr",
    "setattr",
    "delattr",
    "globals",
    "locals",
    "compile",
    "breakpoint",
]


def safe_eval_precondition(precondition_str: str, context: dict) -> bool:
    """
    Safely evaluate a precondition string against a context dict.

    Args:
        precondition_str: e.g. "entropy < 0.85 AND fatigue < 0.75"
        context: dict with variable names as keys, e.g. {"entropy": 0.5, "fatigue": 0.3}

    Returns:
        True if precondition is met, False otherwise (including on error).
    """
    if not precondition_str:
        return True

    # Check for dangerous patterns
    for pattern in _DANGEROUS_PATTERNS:
        if pattern in precondition_str:
            logger.warning(f"Rejected dangerous precondition: {precondition_str}")
            return False

    # Check for semicolons (statement separator)
    if ";" in precondition_str:
        logger.warning(f"Rejected precondition with semicolons: {precondition_str}")
        return False

    try:
        # Replace AND/OR for Python eval
        py_cond = precondition_str.replace("AND", "and").replace("OR", "or")
        safe_dict = {"__builtins__": {}}
        safe_dict.update(context)
        result = eval(py_cond, safe_dict)
        return bool(result)
    except NameError:
        # Missing variable in context → safe fallback
        logger.warning(
            f"Missing variable in precondition '{precondition_str}'"
            f" with context keys: {list(context.keys())}"
        )
        return False
    except Exception as e:
        logger.error(f"Error evaluating precondition '{precondition_str}': {e}")
        return False
