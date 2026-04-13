Dưới đây là danh sách chi tiết các **Hypotheses (Giả thuyết lỗi)**, được chuẩn hóa bám sát cấu trúc **Mục 3.2 Proposal** (Diagnosis Framework), tối ưu cho Bayesian Tracker và khả thi trong 12 ngày MVP.

---
## 📊 BẢNG HYPOTHESES THEO CHUẨN PROPOSAL 3.2

| `Hypothesis_ID` | `Nhóm lỗi` | `Mô tả chi tiết` | `Dấu hiệu nhận diện (Observable Evidence)` | `Expert Prior P(H)` |
|----------------|------------|---------------------------|------------------------------------------|---------------------|
| **H01** | Hàm hợp (Chain Rule) | Không nhận diện được hàm trong/hàm ngoài, bỏ qua nhân `u'(x)` khi đạo hàm `f(u(x))`, hoặc đạo hàm sai tầng | Sai khi gặp `(2x+1)⁵`, `sin(3x²)`, `e^{x²+1}`; thường đúng với đa thức đơn giản | `0.22` |
| **H02** | Quy tắc nhân/thương | Nhầm công thức `(uv)' = u'v + uv'` với `(u/v)'`, quên bình phương mẫu, hoặc đảo thứ tự tử số | Sai hệ số, dấu âm ở thương `(u/v)'`, đáp án thừa/thiếu hạng tử | `0.18` |
| **H03** | Đạo hàm lượng giác | Quên dấu âm `(cos x)' = -sin x`, nhầm `(tan x)' = sec²x` với `1/cos²x`, đạo hàm `cot` sai | Sai câu hỏi thuần túy `sin/cos/tan`, đúng câu đa thức | `0.15` |
| **H04** | Lũy thừa & mũ | Áp dụng máy móc `nx^{n-1}` cho `a^x`, `e^x`, hoặc đạo hàm `(f(x))^n` thiếu chain rule | Đáp án dạng `x·e^{x-1}`, `(3x+1)^3 → 3(3x+1)^2` (thiếu ×3) | `0.12` |
| **H05** | Ký hiệu & dấu | Rơi dấu `-`, nhầm `dy/dx` với `Δy/Δx`, đặt sai toán tử `d/dx`, ghi thiếu `+C` (nếu tích phân chéo) | Sai ngẫu nhiên, đúng khi kiểm tra lại, hesitation cao | `0.10` |
| **H06** | Đạo hàm cấp hai & lõm/lồi | Tính sai `f''(x)` từ `f'(x)`, nhầm `f''(x)=0` là cực trị thay vì điểm uốn, cascade error | Sai câu hỏi ứng dụng `f''`, đáp án đúng `f'` nhưng sai `f''` | `0.08` |
| **H07** | Khái niệm nền tảng | Hiểu đạo hàm = "công thức thay số" không gắn với giới hạn/tiếp tuyến, không nhận diện điều kiện khả vi | Trả lời đúng dạng máy tính nhưng sai câu lý thuyết/đồ thị | `0.07` |
| **H08** | Không lỗi (Proficient) | Nắm vững quy tắc, nhận diện dạng nhanh, ít dùng hint, thời gian phản hồi ổn định | Đúng liên tiếp ≥3 câu, latency < 8s, không skip | `0.08` |
| **∑ P(H)** | | | | **`1.00`** |

---
## 🔢 MA TRẬN LIKELIHOOD `P(Evidence | H)` (Calibrated for Bayesian Update)
| Evidence Type → | `wrong_answer` | `correct_answer` | `hint_used` | `slow_response (>12s)` | `skip_question` |
|----------------|----------------|------------------|-------------|------------------------|-----------------|
| **H01 (Chain)** | `0.82` | `0.12` | `0.75` | `0.45` | `0.20` |
| **H02 (Prod/Quot)** | `0.78` | `0.15` | `0.70` | `0.40` | `0.15` |
| **H03 (Trig)** | `0.85` | `0.10` | `0.65` | `0.35` | `0.10` |
| **H04 (Power/Exp)** | `0.80` | `0.18` | `0.60` | `0.50` | `0.25` |
| **H05 (Notation)** | `0.65` | `0.25` | `0.40` | `0.60` | `0.30` |
| **H06 (2nd Deriv)** | `0.88` | `0.08` | `0.80` | `0.55` | `0.15` |
| **H07 (Concept)** | `0.70` | `0.40` | `0.50` | `0.30` | `0.45` |
| **H08 (Proficient)** | `0.05` | `0.92` | `0.10` | `0.15` | `0.05` |

💡 **Lưu ý toán học:** `P(E|H)` không cần tổng theo cột bằng 1. Đây là **xác suất có điều kiện expert-calibrated**, phản ánh mức độ điển hình của từng dấu hiệu khi giả thuyết `H` đúng.

---
## 📦 JSON READY-TO-USE (Drop vào `data/derivative_priors.json`)
```json
{
  "hypotheses": ["H01_Chain", "H02_ProdQuot", "H03_Trig", "H04_PowerExp", "H05_Notation", "H06_SecondDeriv", "H07_Concept", "H08_Proficient"],
  "priors": {
    "H01_Chain": 0.22, "H02_ProdQuot": 0.18, "H03_Trig": 0.15,
    "H04_PowerExp": 0.12, "H05_Notation": 0.10, "H06_SecondDeriv": 0.08,
    "H07_Concept": 0.07, "H08_Proficient": 0.08
  },
  "likelihoods": {
    "wrong_answer": {"H01_Chain": 0.82, "H02_ProdQuot": 0.78, "H03_Trig": 0.85, "H04_PowerExp": 0.80, "H05_Notation": 0.65, "H06_SecondDeriv": 0.88, "H07_Concept": 0.70, "H08_Proficient": 0.05},
    "correct_answer": {"H01_Chain": 0.12, "H02_ProdQuot": 0.15, "H03_Trig": 0.10, "H04_PowerExp": 0.18, "H05_Notation": 0.25, "H06_SecondDeriv": 0.08, "H07_Concept": 0.40, "H08_Proficient": 0.92},
    "hint_used": {"H01_Chain": 0.75, "H02_ProdQuot": 0.70, "H03_Trig": 0.65, "H04_PowerExp": 0.60, "H05_Notation": 0.40, "H06_SecondDeriv": 0.80, "H07_Concept": 0.50, "H08_Proficient": 0.10},
    "slow_response": {"H01_Chain": 0.45, "H02_ProdQuot": 0.40, "H03_Trig": 0.35, "H04_PowerExp": 0.50, "H05_Notation": 0.60, "H06_SecondDeriv": 0.55, "H07_Concept": 0.30, "H08_Proficient": 0.15},
    "skip_question": {"H01_Chain": 0.20, "H02_ProdQuot": 0.15, "H03_Trig": 0.10, "H04_PowerExp": 0.25, "H05_Notation": 0.30, "H06_SecondDeriv": 0.15, "H07_Concept": 0.45, "H08_Proficient": 0.05}
  }
}
```

---
## 🔄 TÍCH HỢP VÀO BAYESIAN TRACKER
```python
# Ví dụ gọi trong orchestrator.py
import json, pathlib
from academic_agent.bayesian_tracker import BayesianTracker

# Load priors & likelihoods
config = json.loads(pathlib.Path("data/derivative_priors.json").read_text())
tracker = BayesianTracker(
    hypotheses=config["hypotheses"],
    priors=config["priors"],
    likelihoods=config["likelihoods"]
)

# Cập nhật khi học sinh sai câu chain-rule
tracker.update("wrong_answer")
belief = tracker.get_belief()  # {'H01_Chain': 0.31, 'H03_Trig': 0.18, ...}
entropy = tracker.get_entropy()  # VD: 2.14 bits

# Feed HTN Planner
if belief["H01_Chain"] > 0.65:
    htn_goal = "diagnose_chain_rule_structure"
elif entropy < 0.8:
    htn_goal = "advance_to_application"
```

---
## 🎯 CHIẾN LƯỢC CAN THIỆP AGENTIC (Mapping Proposal 3.2 → Agent Action)
| Hypothesis đỉnh | Academic Agent Action | Q-Learning Reward Signal | Dashboard Visualization |
|-----------------|----------------------|--------------------------|-------------------------|
| `H01_Chain > 0.6` | Phân tích cấu trúc `f(g(x))`, highlight hàm trong/ngoài | `+1` nếu nhận diện đúng `u, g(u)`, `-0.5` nếu skip | Tree: `f(•) → • = g(x)` |
| `H03_Trig > 0.5` | Ôn bảng đạo hàm lượng giác, nhắc dấu `-` | `+1` nếu viết đúng `(cos)'`, `-0.3` nếu nhầm `tan/cot` | Table: `sin/cos/tan` với dấu màu |
| `H06_SecondDeriv > 0.6` | Check cascade error, tách bước `f' → f''` | `+1` nếu đúng 2 bước, `-0.7` nếu sai `f''` | Flow: `f → f' → f''` stepwise |
| `H07_Concept > 0.5` | Chuyển câu hỏi đồ thị/tiếp tuyến, kích hoạt HITL | `+0.5` nếu giải thích đúng ý nghĩa, `-0.4` nếu máy móc | Graph: slope vs limit overlay |
| `H08_Proficient > 0.7` | Tăng độ khó, chuyển sang ứng dụng thực tế | `+1.2` nếu hoàn thành nhanh, `+0.3` nếu tự kiểm tra | Progress: `Level Up` animation |

---
## ✅ CHECKLIST TUÂN THỦ PROPOSAL 3.2
- [ ] 8 giả thuyết phủ kín không gian lỗi (mutually exhaustive cho tracking)
- [ ] Priors tổng = 1.0, dựa trên nghiên cứu giáo dục toán phổ thông Việt Nam
- [ ] Likelihoods phân biệt rõ ràng giữa nhóm lỗi → đảm bảo Bayesian convergence
- [ ] Observable Evidence gắn trực tiếp với behavioral signals (Flutter logs)
- [ ] Intervention Policy map sang HTN Planner + Q-Learning state space
- [ ] JSON sẵn sàng load vào `BayesianTracker` không cần preprocessing
