Để kiểm thử (test) và xác thực mô hình Bayesian trong hệ thống chẩn đoán lỗi đạo hàm, chúng ta cần đảm bảo 3 yếu tố: **Tính đúng đắn của thuật toán cập nhật**, **Khả năng hội tụ (Convergence)**, và **Độ nhạy với nhiễu**.

Dưới đây là quy trình test flow chi tiết, bao gồm các kịch bản (scenarios) cụ thể và code mẫu để bạn tích hợp vào `tests/`.

### 1. Unit Tests: Kiểm tra tính đúng đắn của phép cập nhật
Mục tiêu: Đảm công thức Bayes $P(H|E) = \frac{P(E|H)P(H)}{\sum P(E|H_i)P(H_i)}$ được implement chínhاقت.

**Kịch bản Test:**
*   **Test 1: Cập nhật đơn lẻ.** Input một evidence, kiểm tra posterior có khớp với tính toán tay không.
*   **Test 2: Chuẩn hóa (Normalization).** Tổng các xác suất hậu nghiệm $\sum P(H_i|E)$ phải bằng 1.0 (sai số < $10^{-6}$).
*   **Test 3: Edge Case.** Khi prior = 0 hoặc likelihood = 0 (tránh chia cho 0 hoặc log(0)).

```python
# tests/test_bayesian_core.py
import pytest
from academic_agent.bayesian_tracker import BayesianTracker
import json

@pytest.fixture
def tracker():
    config = json.load(open("data/derivative_priors.json"))
    return BayesianTracker(
        hypotheses=config["hypotheses"],
        priors=config["priors"],
        likelihoods=config["likelihoods"]
    )

def test_normalization(tracker):
    """Tổng xác suất luôn bằng 1 sau mỗi lần update"""
    tracker.update("wrong_answer")
    belief = tracker.get_belief()
    assert abs(sum(belief.values()) - 1.0) < 1e-6

def test_single_update_logic(tracker):
    """Kiểm tra logic cập nhật cơ bản cho H08 (Proficient) khi trả lời đúng"""
    initial_h08 = tracker.priors["H08_Proficient"] # 0.08
    tracker.update("correct_answer")
    final_belief = tracker.get_belief()
    
    # H08 phải tăng lên đáng kể vì P(correct|H08) = 0.92 (rất cao)
    # Các hypothesis khác có P(correct|H) thấp hơn nên sẽ giảm relative weight
    assert final_belief["H08_Proficient"] > initial_h08
    assert final_belief["H08_Proficient"] > 0.5 # Hội tụ nhanh về proficient nếu đúng ngay từ đầu
```

---

### 2. Integration Tests: Kiểm tra Flow Chẩn đoán (Diagnostic Scenarios)
Mục tiêu: Mô phỏng hành vi học sinh thực tế để xem mô hình có "đoán" đúng nguyên nhân gốc rễ (Root Cause) không.

#### Kịch bản A: Học sinh mắc lỗi Chain Rule điển hình (H01)
*   **Hành vi:** Sai liên tiếp 3 câu dạng $(2x+1)^5$, $\sin(3x)$, nhưng đúng câu đa thức đơn giản.
*   **Kỳ vọng:** $P(H01\_Chain)$ phải là giá trị lớn nhất (> 0.6) sau 3-4 lần update.

#### Kịch bản B: Học sinh giỏi nhưng cẩn thận chậm (H08 + Slow)
*   **Hành vi:** Trả lời đúng hết, nhưng thời gian phản hồi > 12s (slow_response).
*   **Kỳ vọng:** $P(H08\_Proficient)$ vẫn cao, nhưng $P(H05\_Notation)$ hoặc $H04$ có thể tăng nhẹ do `slow_response` likelihood cao ở các nhóm này, tuy nhiên `correct_answer` sẽ át chế.

#### Kịch bản C: Nhiễu ngẫu nhiên (Noisy Student)
*   **Hành vi:** Sai, Đúng, Sai, Đúng xen kẽ.
*   **Kỳ vọng:** Entropy cao, không có hypothesis nào chiếm ưu thế tuyệt đối (> 0.7). Hệ thống nên gợi ý "ôn tập tổng quát" thay vì can thiệp sâu vào 1 chủ đề.

```python
# tests/test_diagnostic_scenarios.py

def test_chain_rule_diagnosis(tracker):
    """Mô phỏng học sinh sai chain rule liên tục"""
    # Giả lập: Sai 3 lần liên tiếp (default evidence là wrong_answer cho đơn giản, 
    # trong thực tế có thể pass specific pattern như 'E_MISSING_INNER')
    for _ in range(3):
        tracker.update("wrong_answer")
        
    belief = tracker.get_belief()
    top_hypothesis = max(belief, key=belief.get)
    
    # Vì H01, H02, H03 đều có P(wrong|H) cao, nhưng H01 có prior cao nhất (0.22) 
    # và likelihood cao (0.82), nó sẽ dẫn đầu.
    # Lưu ý: Nếu chỉ dùng 'wrong_answer' chung chung, khó phân biệt H01/H03.
    # Test này xác nhận mô hình hoạt động ổn định với dữ liệu nhiễu.
    assert belief["H01_Chain"] > belief["H08_Proficient"]
    print(f"Top Diagnosis: {top_hypothesis} with prob {belief[top_hypothesis]:.2f}")

def test_proficient_student(tracker):
    """Mô phỏng học sinh giỏi"""
    for _ in range(3):
        tracker.update("correct_answer")
        
    belief = tracker.get_belief()
    assert belief["H08_Proficient"] > 0.85
    assert tracker.get_entropy() < 1.0 # Độ bất định thấp
```

---

### 3. Stress Tests & Convergence Analysis
Mục tiêu: Đánh giá tốc độ hội tụ và độ ổn định khi số lượng câu hỏi tăng.

**Cách thực hiện:**
Viết một script mô phỏng Monte Carlo để chạy 1000 lượt học sinh ảo với các profile khác nhau.

```python
# scripts/simulate_convergence.py
import random
import json
from academic_agent.bayesian_tracker import BayesianTracker

def run_simulation(student_profile="chain_rule_error"):
    config = json.load(open("data/derivative_priors.json"))
    tracker = BayesianTracker(**config)
    
    # Định nghĩa hành vi sinh viên ảo
    if student_profile == "chain_rule_error":
        # 80% khả năng sai các câu chain rule, 90% đúng các câu khác
        # Ở đây mô phỏng đơn giản: feed evidence 'wrong_answer' liên tục
        evidence_stream = ["wrong_answer"] * 5 + ["correct_answer"] * 2
        
    elif student_profile == "proficient":
        evidence_stream = ["correct_answer"] * 10
        
    for evidence in evidence_stream:
        tracker.update(evidence)
        
    return tracker.get_belief(), tracker.get_entropy()

# Chạy test
belief, entropy = run_simulation("chain_rule_error")
print("Final Belief:", belief)
print("Final Entropy:", entropy)
```

---

### 4. Kiểm thử Tính Nhạy của Evidence Chi Tiết (Nếu áp dụng Proposal phân rã lỗi)
Nếu bạn đã áp dụng việc phân rã `wrong_answer` thành `E_MISSING_INNER`, `E_WRONG_SIGN`, v.v., cần test thêm:

**Kịch bản: Phân biệt H01 (Chain) và H05 (Sign)**
*   **Input 1:** `E_MISSING_INNER` (Quên nhân đạo hàm trong).
    *   **Kỳ vọng:** $P(H01\_Chain)$ tăng mạnh, $P(H05\_Notation)$ tăng ít.
*   **Input 2:** `E_WRONG_SIGN` (Sai dấu âm).
    *   **Kỳ vọng:** $P(H05\_Notation)$ hoặc $P(H03\_Trig)$ tăng mạnh hơn $H01$.

```python
def test_granular_evidence_discrimination(tracker):
    """Test khả năng phân biệt lỗi chi tiết"""
    
    # Trường hợp 1: Lỗi thiếu inner derivative -> Strong signal for Chain Rule
    tracker.update_evidence("answer_pattern", "E_MISSING_INNER")
    belief_1 = tracker.get_belief()
    
    # Reset tracker (hoặc tạo mới)
    tracker.reset() 
    
    # Trường hợp 2: Lỗi sai dấu -> Strong signal for Notation/Trig
    tracker.update_evidence("answer_pattern", "E_WRONG_SIGN")
    belief_2 = tracker.get_belief()
    
    # H01 phải cao hơn ở case 1 so với case 2
    assert belief_1["H01_Chain"] > belief_2["H01_Chain"]
    
    # H05 hoặc H03 phải cao hơn ở case 2
    assert belief_2["H05_Notation"] > belief_1["H05_Notation"] or \
           belief_2["H03_Trig"] > belief_1["H03_Trig"]
```

---

### 5. Checklist Xác nhận trước khi Deploy MVP

1.  **[ ] Valid JSON:** File `derivative_priors.json` load được không lỗi syntax.
2.  **[ ] Zero Division:** Xử lý trường hợp likelihood = 0 (thêm smoothing $\epsilon = 10^{-9}$ nếu cần).
3.  **[ ] Entropy Threshold:** Xác định ngưỡng entropy để chuyển trạng thái từ "Diagnosing" sang "Intervening" hoặc "Testing". (Ví dụ: Entropy < 0.8 bits).
4.  **[ ] Latency:** Thời gian chạy `tracker.update()` phải < 10ms để không gây trễ UI Flutter.
5.  **[ ] Cold Start:** Khi chưa có dữ liệu (prior đều hoặc expert prior), hệ thống không đưa ra chẩn đoán sai lệch quá mức (bias ban đầu hợp lý).

### Gợi ý Công cụ Hỗ trợ
*   Dùng `pytest` cho unit/integration tests.
*   Dùng `matplotlib` hoặc `seaborn` trong script simulation để vẽ biểu đồ hội tụ của xác suất qua từng bước update (giúp debug trực quan xem mô hình có "học" đúng hướng không).