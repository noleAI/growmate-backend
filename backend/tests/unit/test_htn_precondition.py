from agents.academic_agent.htn_utils import safe_eval_precondition


def test_valid_expression_and():
    ctx = {"entropy": 0.6, "fatigue": 0.4}
    assert safe_eval_precondition("entropy < 0.85 AND fatigue < 0.75", ctx) is True


def test_valid_expression_or_pass():
    # entropy >= 0.85 is False, but fatigue >= 0.8 is True → OR yields True
    ctx = {"entropy": 0.9, "fatigue": 0.85}
    assert safe_eval_precondition("entropy < 0.85 OR fatigue >= 0.8", ctx) is True


def test_boundary_values():
    ctx = {"entropy": 0.85, "fatigue": 0.75}
    assert safe_eval_precondition("entropy >= 0.85 OR fatigue >= 0.75", ctx) is True
    assert safe_eval_precondition("entropy < 0.85 AND fatigue < 0.75", ctx) is False


def test_injection_protection():
    # HTN_MODEL.md yêu cầu an toàn, không cho phép code injection
    ctx = {"entropy": 0.5}
    assert safe_eval_precondition("__import__('os').system('rm -rf /')", ctx) is False
    assert safe_eval_precondition("entropy; import os", ctx) is False


def test_missing_key_safe_fallback():
    ctx = {"entropy": 0.5}  # thiếu fatigue
    # Should return False because 'fatigue' is not in context → NameError → safe fallback
    assert safe_eval_precondition("entropy < 0.85 AND fatigue < 0.75", ctx) is False
