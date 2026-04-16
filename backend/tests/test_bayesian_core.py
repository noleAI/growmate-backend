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
    """Kiểm tra cập nhật khi trả lời đúng làm belief hội tụ trên 4 hypotheses."""
    initial_entropy = tracker.get_entropy()

    tracker.update_evidence("answer_pattern", "E_CORRECT")
    tracker.update_evidence("answer_pattern", "E_CORRECT")
    tracker.update_evidence("answer_pattern", "E_CORRECT")

    final_belief = tracker.beliefs
    assert len(final_belief) == 4
    assert set(final_belief.keys()) == {
        "H01_Trig",
        "H02_ExpLog",
        "H03_Chain",
        "H04_Rules",
    }
    assert tracker.get_entropy() < initial_entropy


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
