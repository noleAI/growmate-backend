import pytest
from agents.academic_agent.bayesian_tracker import BayesianTracker

@pytest.fixture
def tracker():
    return BayesianTracker()

def test_chain_rule_diagnosis(tracker):
    """Mô phỏng học sinh sai chain rule liên tục"""
    # Sai 3 lần liên tiếp: E_MISSING_INNER
    for _ in range(3):
        tracker.update_evidence("answer_pattern", "E_MISSING_INNER")
        
    belief = tracker.beliefs
    top_hypothesis = max(belief, key=belief.get)
    
    assert belief["H01_Chain"] > belief["H08_Proficient"]
    assert top_hypothesis == "H01_Chain"

def test_proficient_student(tracker):
    """Mô phỏng học sinh giỏi"""
    for _ in range(3):
        tracker.update_evidence("answer_pattern", "E_CORRECT")
        
    belief = tracker.beliefs
    assert belief["H08_Proficient"] > 0.85
    assert tracker.get_entropy() < 1.0 # Độ bất định thấp

def test_granular_evidence_discrimination(tracker):
    """Test khả năng phân biệt lỗi chi tiết"""
    # Trường hợp 1: Lỗi thiếu inner derivative
    tracker.update_evidence("answer_pattern", "E_MISSING_INNER")
    belief_1 = tracker.beliefs.copy()
    
    tracker.reset() 
    
    # Trường hợp 2: Lỗi sai dấu
    tracker.update_evidence("answer_pattern", "E_WRONG_SIGN")
    belief_2 = tracker.beliefs.copy()
    
    assert belief_1["H01_Chain"] > belief_2["H01_Chain"]
    
    assert belief_2["H05_Notation"] > belief_1["H05_Notation"] or \
           belief_2["H03_Trig"] > belief_1["H03_Trig"]
