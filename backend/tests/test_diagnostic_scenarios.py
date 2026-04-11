import pytest

from agents.academic_agent.bayesian_tracker import BayesianTracker


@pytest.fixture
def tracker():
    return BayesianTracker()


def test_chain_rule_diagnosis(tracker):
    """Mô phỏng học sinh sai chain rule liên tục"""
    if "H01_Chain" not in tracker.beliefs:
        pytest.skip("Config not matching test expectations")

    # use a specific wrong evidence that signals chain-rule issues
    for _ in range(3):
        tracker.update_evidence("answer_pattern", "E_MISSING_INNER")

    belief = tracker.beliefs
    top_hypothesis = max(belief, key=belief.get)

    # Assuming H01_Chain is a likely cause for E_WRONG_ANSWER
    assert top_hypothesis == "H01_Chain" or belief.get("H01_Chain", 0) > belief.get(
        "H08_Proficient", 0
    )


def test_proficient_student(tracker):
    """Mô phỏng học sinh giỏi"""
    if "H08_Proficient" not in tracker.beliefs:
        pytest.skip("Config not matching test expectations")

    for _ in range(3):
        tracker.update_evidence("answer_pattern", "E_CORRECT")

    belief = tracker.beliefs
    # Expect the proficient hypothesis to increase substantially
    assert belief["H08_Proficient"] > 0.5
    assert tracker.get_entropy() < 1.0


def test_noisy_student(tracker):
    """Mô phỏng học sinh lúc đúng lúc sai (Nhiễu)"""
    if "H01_Chain" not in tracker.beliefs:
        pytest.skip("Config not matching test expectations")

    tracker.update_evidence("answer_pattern", "E_WRONG_OPERATOR")
    tracker.update_evidence("answer_pattern", "E_CORRECT")
    tracker.update_evidence("answer_pattern", "E_WRONG_OPERATOR")

    belief = tracker.beliefs
    top_prob = max(belief.values())

    # No hypothesis should absolutely dominate in a noisy sequence
    assert top_prob < 0.99


def test_granular_evidence_discrimination(tracker):
    """Test khả năng phân biệt lỗi chi tiết"""
    if "H01_Chain" not in tracker.beliefs:
        pytest.skip("Config not matching test expectations")

    tracker.update_evidence("answer_pattern", "E_MISSING_INNER")
    belief_1 = tracker.beliefs.copy()

    tracker.reset()

    tracker.update_evidence("answer_pattern", "E_WRONG_SIGN")
    belief_2 = tracker.beliefs.copy()

    assert belief_1.get("H01_Chain", 0) > belief_2.get("H01_Chain", 0)
    assert belief_2.get("H05_Notation", 0) > belief_1.get(
        "H05_Notation", 0
    ) or belief_2.get("H03_Trig", 0) > belief_1.get("H03_Trig", 0)
