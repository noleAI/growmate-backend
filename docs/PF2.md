# 📐 HƯỚNG DẪN IMPLEMENT CHI TIẾT: PARTICLE FILTER (EMPATY AGENT)
Dựa trên **Section 3.3 & 3.4** của Proposal, đây là guideline kỹ thuật chuẩn production-ready, tối ưu cho nhịp độ 12 ngày Hackathon, tuân thủ nghiêm ngặt phạm vi MVP.

---

## 🗺️ 1. ÁNH XẠ YÊU CẦU PROPOSAL → KỸ THUẬT
| Yêu cầu Proposal (Trang 34-39) | Implementation Decision |
|-------------------------------|-------------------------|
| `S = {focused, confused, exhausted, frustrated}` | State rời r dạng index `0..3`. Particle = mảng numpy `[N]` chứa state index. |
| `Transition Model P(s_t \| s_{t-1})` | Ma trận `4x4` expert-defined. Load từ JSON. Dùng `np.random.choice` vectorized. |
| `Observation Model P(signals \| s)` | Heuristic rules → `predict_likelihood(signals)` trả về mảng `[4]`. Interface abstraction `ObservationModel`. |
| `Resample: tránh suy biến` | Systematic Resampling (chuẩn, ổn định, O(N)). |
| `Estimate: belief + uncertainty` | `belief = Σ weights`, `uncertainty = normalized_entropy(belief)`. |
| `EU(action) = Σ P(s\|belief) × Utility(action,s)` | Ma trận utility `actions x states`. Dot product với belief → chọn argmax. |
| `HITL trigger khi uncertainty > ngưỡng` | Ngưỡng cố định `0.75` (MVP). Push event `hitl_required` + payload EU rationale. |

---

## ⚙️ 2. CẤU HÌNH JSON (Expert-Defined, MVP)
Tạo 3 file trong `configs/`. Dễ tune, không hardcode.

### `configs/transition_model.json`
```json
{
  "states": ["focused", "confused", "exhausted", "frustrated"],
  "matrix": [
    [0.70, 0.20, 0.05, 0.05],
    [0.15, 0.40, 0.30, 0.15],
    [0.10, 0.10, 0.60, 0.20],
    [0.25, 0.25, 0.20, 0.30]
  ]
}
```
> 💡 *Expert rationale:* `confused → exhausted` cao (0.3) khi time-on-task dài. `focused` duy trì cao (0.7).

### `configs/utility_table.json`
```json
{
  "actions": ["continue_quiz", "show_hint", "suggest_break", "trigger_hitl"],
  "states": ["focused", "confused", "exhausted", "frustrated"],
  "matrix": [
    [ 1.0,  0.2, -0.5, -0.8],
    [ 0.1,  0.8,  0.4,  0.3],
    [-0.3,  0.3,  1.0,  0.6],
    [-0.5, -0.2, -0.1, -0.4]
  ]
}
```
> 💡 *MVP:* `suggest_break` utility cao nhất khi `exhausted`/`frustrated`. `continue_quiz` âm nếu tinh thần suy giảm.

---

## 🧠 3. IMPLEMENTATION CODE (Vectorized, O(N))
File: `empathy_agent/particle_filter.py`

```python
import numpy as np
from typing import Dict, List, Tuple
import json

class ObservationModel:
    """Abstraction layer cho heuristic rules (Proposal 3.3.1)"""
    def __init__(self, config_path: str = "configs/observation_rules.json"):
        with open(config_path) as f:
            self.rules = json.load(f)
            
    def predict_likelihood(self, signals: Dict[str, float]) -> np.ndarray:
        """Trả về P(signals | S) dạng mảng [4] cho 4 states"""
        # MVP: Heuristic weighted sum
        base = np.array([0.25, 0.25, 0.25, 0.25])  # Uniform prior fallback
        for signal, val in signals.items():
            if signal in self.rules:
                weights = np.array(self.rules[signal]["weights"])  # shape (4,)
                base *= (1.0 + val * weights)
        return base / base.sum()  # Normalize

class ParticleFilter:
    def __init__(self, n_particles: int = 100, seed: int = 42):
        self.n = n_particles
        self.rng = np.random.default_rng(seed)
        self.particles = self.rng.integers(0, 4, size=n_particles)  # 0..3 states
        self.weights = np.ones(n_particles) / n_particles
        self.obs_model = ObservationModel()
        
    def _load_config(self, path: str):
        with open(path) as f:
            return json.load(f)

    def predict(self, transition_matrix: np.ndarray) -> None:
        """Bước 1: Sample trạng thái mới từ transition model"""
        # Vectorized: dùng matrix indexing để chọn hàng transition theo particle hiện tại
        probs = transition_matrix[self.particles]  # shape (N, 4)
        self.particles = np.array([self.rng.choice(4, p=p) for p in probs])

    def update_weights(self, signals: Dict[str, float]) -> None:
        """Bước 2: Cập nhật trọng số từ observation model"""
        likelihoods = self.obs_model.predict_likelihood(signals)  # shape (4,)
        particle_likelihoods = likelihoods[self.particles]       # shape (N,)
        self.weights *= particle_likelihoods
        # Normalize tránh underflow
        self.weights /= np.sum(self.weights) + 1e-12

    def resample_systematic(self) -> None:
        """Bước 3: Systematic resampling tránh suy biến hạt"""
        positions = (self.rng.random() + np.arange(self.n)) / self.n
        cum_weights = np.cumsum(self.weights)
        indices = np.searchsorted(cum_weights, positions, side='right')
        indices = np.clip(indices, 0, self.n - 1)
        self.particles = self.particles[indices]
        self.weights.fill(1.0 / self.n)  # Reset weights sau resample

    def estimate(self) -> Tuple[Dict[str, float], float, List[int]]:
        """Bước 4: Tính belief, uncertainty, trả về distribution"""
        belief = np.bincount(self.particles, minlength=4, weights=self.weights)
        belief /= belief.sum() + 1e-12
        # Normalized entropy [0, 1] (0=certainty, 1=max uncertainty)
        safe = np.clip(belief, 1e-12, 1.0)
        entropy = -np.sum(safe * np.log2(safe))
        uncertainty = entropy / np.log2(4)  # Normalize về [0,1]
        
        states = ["focused", "confused", "exhausted", "frustrated"]
        belief_dist = {s: float(b) for s, b in zip(states, belief)}
        particle_hist = np.bincount(self.particles, minlength=4).tolist()
        return belief_dist, float(uncertainty), particle_hist

class EmpathyAgent:
    """Orchestrator cho Particle Filter + Expected Utility + HITL (3.3.3)"""
    def __init__(self, pf_config: str = "configs/transition_model.json",
                 util_config: str = "configs/utility_table.json",
                 hitl_threshold: float = 0.75):
        self.pf = ParticleFilter()
        with open(pf_config) as f: self.transition = np.array(json.load(f)["matrix"])
        with open(util_config) as f: self.util = json.load(f)
        self.actions = self.util["actions"]
        self.util_matrix = np.array(self.util["matrix"])
        self.hitl_threshold = hitl_threshold
        self.decision_log = []

    def process_signals(self, signals: Dict[str, float]) -> Dict:
        self.pf.predict(self.transition)
        self.pf.update_weights(signals)
        self.pf.resample_systematic()
        belief, uncertainty, p_hist = self.pf.estimate()
        
        # Expected Utility
        belief_vec = np.array(list(belief.values()))
        eu_values = self.util_matrix @ belief_vec
        best_action_idx = int(np.argmax(eu_values))
        best_action = self.actions[best_action_idx]
        
        hitl_triggered = uncertainty > self.hitl_threshold
        if hitl_triggered: best_action = "trigger_hitl"
        
        decision = {
            "belief_distribution": belief,
            "uncertainty_score": uncertainty,
            "particle_distribution": p_hist,
            "eu_values": {a: float(e) for a, e in zip(self.actions, eu_values)},
            "recommended_action": best_action,
            "hitl_triggered": hitl_triggered
        }
        self.decision_log.append(decision)
        return decision
```

---

## 🔌 4. TÍCH HỢP VÀO BACKEND (FastAPI Flow)
```python
# backend/routes/empathy.py
from fastapi import APIRouter
from empathy_agent.particle_filter import EmpathyAgent

router = APIRouter()
agent = EmpathyAgent()  # Singleton per session (inject via dependency)

@router.post("/process_signals")
async def process_empathy_signals(session_id: str, signals: dict):
    result = agent.process_signals(signals)
    # Push to WebSocket dashboard
    await ws_manager.broadcast(session_id, "empathy_update", result)
    return result
```
> 📦 **Dependency Injection:** Khởi tạo `EmpathyAgent` mỗi session mới. Sync `decision_log` lên Supabase mỗi 5 bước để dashboard/HITL đọc được khi mất kết nối.

---

## 📊 5. PAYLOAD DASHBOARD & LOGGING (Realtime)
WebSocket payload chuẩn proposal:
```json
{
  "event": "empathy_state_update",
  "session_id": "s_9a8b",
  "timestamp": 1744000000,
  "data": {
    "belief_distribution": {"focused": 0.15, "confused": 0.45, "exhausted": 0.30, "frustrated": 0.10},
    "uncertainty_score": 0.82,
    "particle_distribution": [12, 38, 29, 21],
    "eu_values": {"continue_quiz": -0.12, "show_hint": 0.45, "suggest_break": 0.88, "trigger_hitl": 0.91},
    "recommended_action": "trigger_hitl",
    "hitl_triggered": true
  }
}
```
- **Dashboard UI:** 
  - `particle_distribution` → Histogram bar chart (4 cột).
  - `belief_distribution` → Pie/Donut chart.
  - `uncertainty_score` → Gauge (0→1), đỏ khi `>0.75`.
  - `eu_values` → Table + highlight max.
  - `hitl_triggered` → Popup confirm cho teacher.

---

## 🧪 6. TESTING & VALIDATION
| Test Case | Input | Expected Output |
|-----------|-------|-----------------|
| **Init** | `ParticleFilter()` | `particles.shape=(100,)`, `weights.sum()≈1.0` |
| **Predict** | `transition_matrix` | `particles` dịch chuyển theo xác suất, `weights` không đổi |
| **Update** | `signals={"idle_time": 0.8, "error_rate": 0.6}` | `weights` tăng ở index `2,3`, `belief` shift right |
| **Resample** | Degenerate weights | `particles` tập trung, `weights` reset uniform |
| **EU & HITL** | `uncertainty=0.81`, EU(break)=0.85 | `action="trigger_hitl"`, `hitl_triggered=true` |

```python
# tests/test_empathy_agent.py
def test_pf_eu_and_hitl():
    agent = EmpathyAgent(hitl_threshold=0.7)
    # Mô phỏng chuỗi tín hiệu gây kiệt sức
    res = agent.process_signals({"idle_time": 0.9, "error_rate": 0.8, "correction_rate": 0.2})
    assert res["hitl_triggered"] == True
    assert res["recommended_action"] == "trigger_hitl"
    assert abs(sum(res["belief_distribution"].values()) - 1.0) < 1e-6
```

---

## ⚠️ 7. RỦI RO & MITIGATION (IMPLEMENTATION)
| Rủi ro | Nguyên nhân | Mitigation |
|--------|-------------|------------|
| **Particle degeneracy** (90% hạt cùng 1 state) | Observation likelihood quá chênh lệch | Systematic resampling + jitter nhẹ (`np.random.normal`) nếu ESS < 0.5 |
| **Underflow weights** | Nhân likelihood liên tục → `0.0` | Normalize sau mỗi `update_weights()`. Dùng `log-space` nếu cần (nhưng MVP không cần). |
| **Cold start bias** | Prior uniform không phản ánh real user | Load `initial_belief` từ JSON config nếu có pre-assessment. |
| **EU tie-breaking** | 2 actions có EU gần bằng nhau | Ưu tiên `show_hint` → `suggest_break` → `continue_quiz` (dễ triển khai, an toàn). |
| **WS payload delay** | Dashboard nhận chậm | Delta push only when `change > 0.05` hoặc mỗi 1.5s. |

---

## ✅ 8. DEFINITION OF DONE (DoD) cho Particle Filter Module
- [ ] Class `ParticleFilter` & `EmpathyAgent` pass unit tests (coverage ≥80%).
- [ ] Vectorized implementation, không dùng vòng lặp Python cho predict/update/resample.
- [ ] Config JSON load đúng, `ObservationModel` interface hoạt động với signals dict.
- [ ] `EU(action)` tính đúng theo công thức proposal, trigger HITL khi `uncertainty > threshold`.
- [ ] WebSocket push payload chuẩn, dashboard render realtime belief/particle/uncertainty/EU.
- [ ] Decision log sync Supabase, format sẵn cho báo cáo kỹ thuật & demo video.
- [ ] Code review pass, không dependency ngoài `numpy`, `json`, `typing`.
