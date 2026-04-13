import pytest

from agents.academic_agent.bayesian_tracker import BayesianTracker


@pytest.fixture
def tracker():
    return BayesianTracker()


def test_normalization(tracker):
    """Tổng xác suất luôn bằng 1 sau mỗi lần update"""
    # Assuming config is loaded properly
    # use a concrete wrong-answer pattern present in the likelihoods
    tracker.update_evidence("answer_pattern", "E_WRONG_OPERATOR")
    assert abs(sum(tracker.beliefs.values()) - 1.0) < 1e-6


def test_single_update_logic(tracker):
    """Kiểm tra logic cập nhật cơ bản cho H08 (Proficient) khi trả lời đúng"""
    # Assuming config is loaded properly
    initial_h08 = tracker.beliefs.get("H08_Proficient", 0.0)
    # use the correct-answer evidence key defined in derivative_priors.json
    tracker.update_evidence("answer_pattern", "E_CORRECT")
    final_belief = tracker.beliefs

    if "H08_Proficient" in final_belief:
        assert final_belief["H08_Proficient"] > initial_h08


def test_edge_case_zero_division():
    """Test handling of prior=0 or likelihood=0"""
    tracker = BayesianTracker()
    tracker.beliefs = {"H1": 0.0, "H2": 1.0}
    tracker.config = {"likelihoods": {"test_cat": {"test_ev": {"H1": 0.0, "H2": 0.0}}}}

    tracker.update_evidence("test_cat", "test_ev")
    # If all likelihoods or priors result in 0, the sum is 0.
    # Current implementation doesn't update beliefs if marginal_likelihood == 0.
    # So it should remain unchanged.
    assert tracker.beliefs == {"H1": 0.0, "H2": 1.0}
