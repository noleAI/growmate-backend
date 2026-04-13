Dựa trên **Section 3.5 (Trang 42-43)** của Proposal và sơ đồ `diagram.md`, đây là **Guideline Implement chi tiết cho Orchestrator Engine**, được tối ưu hóa cho nhịp độ Hackathon nhưng vẫn đảm bảo kiến trúc mở rộng sang Phase 2.

---
## 🧠 1. KIẾN TRÚC & CHIẾN LƯỢC MVP (Quan trọng)

| Thành phần (Theo Diagram/Proposal) | Cách tiếp cận MVP (12 ngày) | Lý do & Ghi chú |
| :--- | :--- | :--- |
| **Policy Network (Sec 3.5.1)** | **Deterministic Utility Logic**. Thay vì MLP 2-3 lớp, dùng hàm Utility Weighted Sum. | Proposal Sec 3.5.1 ghi rõ: *"MVP: Policy Logic Deterministic / Utility"*. Tránh over-engineering neural network trong 12 ngày, ưu tiên độ trễ thấp và logic giải thích được. |
| **State Embedding** | Dictionary/JSON object chứa các feature chuẩn hóa từ 3 Agent. | Dữ liệu đầu vào thô sẽ được `StateAggregator` gom lại thành vector feature phẳng. |
| **Calibration & Monitoring** | **Threshold-based**. Tính tổng Uncertainty = $w_1 H_{academic} + w_2 H_{empathy}$. | Sec 3.5.2: *"MVP: Threshold-based"*. Không dùng Temperature Scaling phức tạp. Dùng ngưỡng cố định (ví dụ: 0.6) để trigger HITL. |
| **Decision & HITL** | Routing logic đơn giản: Nếu `Uncertainty > Threshold` -> HITL, Ngược lại -> Argmax(Utility). | Đảm bảo luồng chạy realtime, không blocking UI. |

> 📌 **Nguyên tắc:** Viết code theo **Interface**. Orchestrator gọi `policy.predict(state)`. Hiện tại implement bằng hàm `calculate_utility`. Phase 2 chỉ cần swap class này bằng Neural Network mà không phải sửa code luồng chính.

---

## 📁 2. CẤU TRÚC CODE ORCHESTRATOR
```text
backend/
├── orchestrator/
│   ├── engine.py            # ✅ Core Orchestrator (Glue code)
│   ├── aggregator.py        # 🆕 Gom state từ các Agent
│   ├── policy.py            # 🆕 Deterministic Utility Logic (MVP)
│   ├── monitoring.py        # 🆕 Tính toán Uncertainty & HITL Trigger
│   └── schemas.py           # 📐 Pydantic models cho State/Action
├── api/routes/
│   └── orchestrator.py      # Endpoint /step hoặc WS handler
└── configs/
    └── orchestrator.yaml    # ⚙️ Weights, Thresholds
```

---

## 🛠️ 3. IMPLEMENTATION CHI TIẾT (Python)

### 3.1. State Schemas (`schemas.py`)
Định nghĩa chuẩn dữ liệu trao đổi giữa các Agent.

```python
from pydantic import BaseModel
from typing import Dict, List, Optional

class AcademicState(BaseModel):
    belief_distribution: Dict[str, float]
    entropy: float
    top_hypothesis: str
    confidence: float

class EmpathyState(BaseModel):
    confusion: float
    fatigue: float
    uncertainty: float
    particle_distribution: Dict[str, int]

class MemoryState(BaseModel):
    q_values: Dict[str, float]
    avg_reward: float

class AggregatedState(BaseModel):
    academic: AcademicState
    empathy: EmpathyState
    memory: MemoryState
    embedding: Dict[str, float]  # Vector phẳng cho Policy
```

### 3.2. State Aggregator (`aggregator.py`)
Gom dữ liệu và tạo `embedding` (Feature Vector).

```python
from .schemas import AggregatedState, AcademicState, EmpathyState, MemoryState

class StateAggregator:
    def __init__(self, config: dict):
        self.embedding_keys = config.get("embedding_keys", [])
        self.weights = config.get("embedding_weights", {})

    def aggregate(self, academic: AcademicState, empathy: EmpathyState, memory: MemoryState) -> AggregatedState:
        # Tạo embedding: Gom các metric quan trọng lại
        embedding = {
            "academic_entropy": academic.entropy,
            "academic_confidence": academic.confidence,
            "empathy_confusion": empathy.confusion,
            "empathy_fatigue": empathy.fatigue,
            "empathy_uncertainty": empathy.uncertainty,
            "memory_best_q": max(memory.q_values.values()) if memory.q_values else 0.0,
            # ... thêm các feature khác nếu cần
        }
        
        return AggregatedState(
            academic=academic,
            empathy=empathy,
            memory=memory,
            embedding=embedding
        )
```

### 3.3. Policy Module (`policy.py`)
Triển khai **Deterministic Utility** thay vì Neural Network.

```python
import logging
from typing import Tuple, Dict, List
from .schemas import AggregatedState

logger = logging.getLogger("orchestrator.policy")

class PolicyEngine:
    """
    MVP: Deterministic Utility Logic
    Sec 3.5.1: "Orchestrator sử dụng policy logic deterministic dựa trên utility comparison"
    """
    def __init__(self, config: dict):
        self.actions = config["actions"] # ["diagnose", "remediate", "recover", "encourage", "hitl"]
        self.utility_rules = config["utility_rules"]

    def predict(self, state: AggregatedState) -> Tuple[str, Dict[str, float]]:
        """
        Tính Utility cho từng action dựa trên state hiện tại.
        Trả về: Action tốt nhất và Action Distribution (dưới dạng Utility normalized)
        """
        u_scores = {}
        
        for action in self.actions:
            score = 0.0
            
            # Rule Example: Action 'recover' (nghỉ ngơi) có utility cao nếu Fatigue cao
            if action == "recover":
                score += self.utility_rules["recover"]["base"]
                score += state.empathy.fatigue * self.utility_rules["recover"]["fatigue_weight"]
                score -= state.academic.confidence * self.utility_rules["recover"]["confidence_penalty"]
            
            # Rule Example: Action 'diagnose' có utility cao nếu Uncertainty cao
            elif action == "diagnose":
                score += self.utility_rules["diagnose"]["base"]
                score += state.academic.entropy * self.utility_rules["diagnose"]["entropy_weight"]
                
            # Rule Example: Action 'remediate' ưu tiên nếu biết lỗi cụ thể (Confidence cao)
            elif action == "remediate":
                score += self.utility_rules["remediate"]["base"]
                score += state.academic.confidence * self.utility_rules["remediate"]["confidence_weight"]
            
            u_scores[action] = score

        # Normalize để làm "Action Distribution" giả lập softmax
        import numpy as np
        vals = np.array(list(u_scores.values()))
        exp_vals = np.exp(vals - np.max(vals))
        probs = exp_vals / exp_vals.sum()
        dist = {a: float(p) for a, p in zip(self.actions, probs)}
        
        best_action = max(u_scores, key=u_scores.get)
        return best_action, dist
```

### 3.4. Monitoring & HITL (`monitoring.py`)
Tự giám sát độ bất định và quyết định can thiệp.

```python
from .schemas import AggregatedState

class MonitoringEngine:
    def __init__(self, config: dict):
        self.uncertainty_threshold = config["uncertainty_threshold"] # VD: 0.6
        self.weights = config.get("uncertainty_weights", {"academic": 0.4, "empathy": 0.6})

    def check_uncertainty(self, state: AggregatedState) -> Tuple[float, bool]:
        """
        Tính Total Uncertainty theo Sec 3.5.2:
        • Academic uncertainty: Entropy belief.
        • Empathy uncertainty: Entropy mental state.
        """
        # Chuẩn hóa entropy về [0, 1] (Entropy max của phân phối N state là log(N))
        # Giả sử Academic belief entropy đã chuẩn hóa hoặc ta tự normalize
        u_academic = state.academic.entropy 
        u_empathy = state.empathy.uncertainty # Đã là normalized entropy trong PF
        
        total_uncertainty = (
            self.weights["academic"] * u_academic +
            self.weights["empathy"] * u_empathy
        )
        
        trigger_hitl = total_uncertainty > self.uncertainty_threshold
        return round(total_uncertainty, 3), trigger_hitl
```

### 3.5. Core Orchestrator Engine (`engine.py`)
Kết nối tất cả.

```python
import logging
from .aggregator import StateAggregator
from .policy import PolicyEngine
from .monitoring import MonitoringEngine
from .schemas import AggregatedState

logger = logging.getLogger("orchestrator.engine")

class Orchestrator:
    def __init__(self, config: dict):
        self.aggregator = StateAggregator(config["aggregator"])
        self.policy = PolicyEngine(config["policy"])
        self.monitor = MonitoringEngine(config["monitoring"])
        
    def run_step(self, academic_state, empathy_state, memory_state) -> dict:
        # 1. Aggregate State
        agg_state = self.aggregator.aggregate(academic_state, empathy_state, memory_state)
        
        # 2. Monitoring (Tính Uncertainty)
        total_uncertainty, hitl_needed = self.monitor.check_uncertainty(agg_state)
        
        # 3. Policy Decision
        best_action, action_dist = self.policy.predict(agg_state)
        
        # 4. HITL Override
        final_action = best_action
        hitl_payload = None
        
        if hitl_needed:
            final_action = "hitl" # Force trigger HITL
            hitl_payload = {
                "reason": "High Uncertainty",
                "total_uncertainty": total_uncertainty,
                "suggested_action": best_action,
                "message": "Hệ thống chưa chắc chắn về trạng thái của bạn. Bạn muốn tiếp tục hay nghỉ ngơi?"
            }
            logger.info(f"HITL Triggered: U={total_uncertainty}")

        # 5. Return Decision
        return {
            "action": final_action,
            "action_distribution": action_dist,
            "total_uncertainty": total_uncertainty,
            "hitl_triggered": hitl_needed,
            "hitl_payload": hitl_payload,
            "rationale": self._get_rationale(agg_state, best_action)
        }

    def _get_rationale(self, state: AggregatedState, action: str) -> str:
        # Logic giải thích tại sao chọn action (cho Audit Log)
        if action == "recover":
            return f"Fatigue cao ({state.empathy.fatigue:.2f}), ưu tiên nghỉ ngơi."
        elif action == "diagnose":
            return f"Uncertainty học tập cao (H={state.academic.entropy:.2f}), cần chẩn đoán thêm."
        return f"Utility action '{action}' cao nhất dựa trên policy hiện tại."
```

---

## 🔗 4. TÍCH HỢP VÀO LUỒNG CHÍNH

### Trong `backend/main.py` hoặc Route Handler
```python
from orchestrator.engine import Orchestrator
from orchestrator.schemas import AcademicState, EmpathyState, MemoryState

orchestrator = Orchestrator(config)

@app.post("/api/session/next_step")
async def next_step(input_data: dict):
    # Nhận state từ các agent khác (lấy từ memory/session context)
    academic_st = AcademicState(**session_context["academic"])
    empathy_st = EmpathyState(**session_context["empathy"])
    memory_st = MemoryState(**session_context["memory"])
    
    # Chạy Orchestrator
    decision = orchestrator.run_step(academic_st, empathy_st, memory_st)
    
    # Xử lý kết quả
    if decision["hitl_triggered"]:
        # Lưu vào queue HITL, trả về UI yêu cầu xác nhận
        return {"status": "hitl", "payload": decision["hitl_payload"]}
    
    # Trả về action để hệ thống thực thi (gửi câu hỏi, gợi ý...)
    return {"status": "auto", "action": decision["action"], "rationale": decision["rationale"]}
```

---

## 📊 5. DASHBOARD PAYLOAD (Inspection Dashboard)
Để chứng minh cơ chế theo proposal, payload gửi xuống Dashboard phải có:

```json
{
  "component": "orchestrator",
  "decision": {
    "action": "recover",
    "confidence": 0.85, 
    "total_uncertainty": 0.72,
    "hitl_triggered": true,
    "action_distribution": {
      "diagnose": 0.15,
      "remediate": 0.10,
      "recover": 0.65,
      "encourage": 0.10
    }
  },
  "monitoring": {
    "academic_entropy": 0.4,
    "empathy_uncertainty": 0.8,
    "threshold": 0.6
  },
  "audit_log": {
    "timestamp": "2026-04-15T10:00:00Z",
    "state_snapshot": { ... },
    "policy_type": "Deterministic_Utility_v1"
  }
}
```
**Visual trên Dashboard:**
1. **Action Distribution:** Biểu đồ tròn/cột thể hiện xác suất các action.
2. **Uncertainty Gauge:** Kim chỉ mức độ bất định, vạch đỏ ở ngưỡng HITL.
3. **Decision Log:** Bảng ghi lại `Action`, `Reason`, `HITL Status`.

---

## ✅ 6. DEFINITION OF DONE (DoD)
- [ ] **Kiến trúc:** Tách biệt `Aggregator`, `Policy`, `Monitoring` đúng theo diagram.
- [ ] **Policy:** Implement hàm Utility determinist, output Action Distribution hợp lý (tổng = 1).
- [ ] **Monitoring:** Tính đúng Total Uncertainty, trigger HITL khi vượt ngưỡng config.
- [ ] **Integration:** Orchestrator nhận state từ Academic/Empathy/Memory, trả về Action đúng luồng.
- [ ] **Dashboard:** Push payload realtime, hiển thị Uncertainty và Action Distribution.
- [ ] **Config:** Tất cả weights, thresholds load từ YAML, không hardcode.
- [ ] **Test:** Unit test cho Policy logic (verify utility weights), Monitoring (verify threshold trigger).
- [ ] **Log:** Audit log ghi nhận `policy_type`, `state_embedding`, `rationale` cho báo cáo kỹ thuật.

---

## 💡 LỜI KHUYÊN SENIOR ARCHITECT
1.  **Utility Weights Tuning:** Dành ngày 10/04 để tune `utility_rules` trong YAML sao cho hành vi Orchestrator "người" nhất. Ví dụ: Không bao giờ chọn `diagnose` khi `fatigue > 0.8`.
2.  **Abstraction Layer:** Giữ nguyên class name `PolicyEngine`. Khi Phase 2, bạn chỉ cần thay body hàm `predict` bằng code gọi model PyTorch/TensorFlow, phần còn lại giữ nguyên.
3.  **HITL Payload:** Thiết kế message HITL thân thiện (như ví dụ trong proposal: *"Mình không chắc bạn đang mệt hay bối rối..."*). Đây là điểm UX ghi điểm lớn.
4.  **Latency:** Logic Deterministic chạy < 5ms. Đảm bảo Orchestrator không bao giờ là nút cổ chai (bottleneck).