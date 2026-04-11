import pytest
from agents.academic_agent.bayesian_tracker import BayesianTracker

@pytest.fixture
def tracker():
    return BayesianTracker()

def test_normalization(tracker):
    """Tổng xác suất luôn bằng 1 sau mỗi lần update"""
    tracker.update_evidence("answer_pattern", "E_AMBIGUOUS_ERROR") # equivalent to wrong_answer
    assert abs(sum(tracker.beliefs.values()) - 1.0) < 1e-6

def test_single_update_logic(tracker):
    """Kiểm tra logic cập nhật cơ bản cho H08 (Proficient) khi trả lời đúng"""
    initial_h08 = tracker.beliefs["H08_Proficient"]
    tracker.update_evidence("answer_pattern", "E_CORRECT")
    final_belief = tracker.beliefs
    
    assert final_belief["H08_Proficient"] > initial_h08
    assert final_belief["H08_Proficient"] > 0.3 # Hội tụ lên ~0.33 sau 1 lần đúng.
