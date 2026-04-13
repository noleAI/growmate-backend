# 📘 GUIDELINE IMPLEMENTATION: PARTICLE FILTER (Empathy Agent)
**Mục tiêu:** Triển khai bộ ước lượng trạng thái tâm lý `[confusion, fatigue]` realtime, vector hóa bằng NumPy, tích hợp seamless vào Orchestrator, xuất payload chuẩn cho Dashboard & Q-Learning. Tối ưu cho 12 ngày, không phụ thuộc framework nặng, dễ điều chỉnh tham số qua YAML.

---
## 📁 1. CẤU TRÚC FILE
```
backend/
├── agents/empathy_agent/
│   ├── particle_filter.py       # ✅ Triển khai chính
│   └── likelihood.py            # 📝 Công thức xác suất quan sát (điền sau)
├── configs/
│   └── agents.yaml              # ⚙️ Tham số PF
└── tests/test_empathy/
    └── test_particle_filter.py  # 🧪 Unit & Integration test
```

---
## 🧩 2. CODE IMPLEMENTATION (`particle_filter.py`)
```python
import numpy as np
import logging
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel

logger = logging.getLogger("empathy.pf")

class PFState(BaseModel):
    confusion: float
    fatigue: float
    uncertainty: float
    ess: float
    particle_cloud: List[List[float]]
    weights: List[float]

class ParticleFilter:
    def __init__(self, config: dict):
        self.n = config.get("n_particles", 100)
        self.sigma_process = config.get("process_noise", 0.05)
        self.jitter_sigma = config.get("jitter_sigma", 0.01)
        self.ess_threshold = config.get("ess_threshold_ratio", 0.5)
        
        # Khởi tạo uniform prior trong [0,1]x[0,1]
        self.particles = np.random.rand(self.n, 2)
        self.weights = np.ones(self.n) / self.n
        self.step = 0

    def predict(self):
        """Bước 1: State transition + process noise"""
        noise = np.random.randn(self.n, 2) * self.sigma_process
        self.particles += noise
        self.particles = np.clip(self.particles, 0.0, 1.0)
        self.step += 1

    def update(self, signals: Dict[str, float], likelihood_fn: callable):
        """Bước 2: Update weights dựa trên quan sát hành vi"""
        try:
            # Tính log-likelihood để tránh underflow
            log_weights = likelihood_fn(self.particles, signals)
            self.weights = np.exp(log_weights - np.max(log_weights))  # Numerical stability
            self.weights += 1e-12  # Floor weight
            self.weights /= self.weights.sum()
        except Exception as e:
            logger.warning(f"PF update failed: {e}. Using uniform weights.")
            self.weights = np.ones(self.n) / self.n

    def resample(self):
        """Bước 3: Systematic resampling + jitter"""
        positions = (np.arange(self.n) + np.random.rand()) / self.n
        indices = np.searchsorted(np.cumsum(self.weights), positions)
        self.particles = self.particles[indices].copy()
        self.weights = np.ones(self.n) / self.n
        
        # Jitter tránh particle collapse
        jitter = np.random.randn(self.n, 2) * self.jitter_sigma
        self.particles = np.clip(self.particles + jitter, 0.0, 1.0)

    def should_resample(self) -> bool:
        ess = 1.0 / np.sum(self.weights**2)
        return ess < (self.n * self.ess_threshold)

    def get_state(self) -> PFState:
        """Xuất trạng thái ước lượng + metrics cho dashboard & Q-learning"""
        ess = 1.0 / np.sum(self.weights**2)
        return PFState(
            confusion=float(np.average(self.particles[:, 0], weights=self.weights)),
            fatigue=float(np.average(self.particles[:, 1], weights=self.weights)),
            uncertainty=float(1.0 - ess / self.n),
            ess=float(ess),
            particle_cloud=self.particles.tolist(),
            weights=self.weights.tolist()
        )

    def discretize_for_q(self) -> str:
        """Chuyển state liên tục → discrete state cho Q-Table"""
        state = self.get_state()
        c = "high" if state.confusion > 0.5 else "low"
        f = "high" if state.fatigue > 0.6 else "low"
        return f"{c}_confusion_{f}_fatigue"

    def reset(self, explicit_feedback: Optional[Dict[str, float]] = None):
        """Reset khi session mới hoặc user cung cấp feedback rõ ràng"""
        self.particles = np.random.rand(self.n, 2)
        self.weights = np.ones(self.n) / self.n
        self.step = 0
        if explicit_feedback:
            # Bias particle về vùng feedback (optional refinement)
            self.particles *= 0.5
            self.particles += 0.5 * np.array([
                explicit_feedback.get("confusion", 0.5),
                explicit_feedback.get("fatigue", 0.5)
            ])
            self.particles = np.clip(self.particles, 0.0, 1.0)
```

---
## ⚙️ 3. CẤU HÌNH (`configs/agents.yaml`)
```yaml
empathy:
  particle_filter:
    n_particles: 100
    process_noise: 0.05          # Drift tự nhiên của trạng thái tâm lý
    jitter_sigma: 0.01           # Nhiễu sau resampling
    ess_threshold_ratio: 0.5     # Resample khi ESS < 50% N
    state_bounds: [0.0, 1.0]     # Confusion & Fatigue đều chuẩn hóa
```
**Cách load:**
```python
import yaml
with open("configs/agents.yaml") as f:
    config = yaml.safe_load(f)
pf = ParticleFilter(config["empathy"]["particle_filter"])
```

---
## 🔗 4. TÍCH HỢP VÀO ORCHESTRATOR & DASHBOARD
### 🔹 Trong `orchestrator.py`
```python
# Init
pf = ParticleFilter(pf_config)
likelihood_fn = load_likelihood_function("empathy/likelihood.py")  # TODO: điền sau

# Trong run_session_step()
signals = payload.get("behavior_signals", {})
pf.predict()
pf.update(signals, likelihood_fn)

if pf.should_resample():
    pf.resample()

pf_state = pf.get_state()
state.empathy_state.update(pf_state.model_dump())

# Feed vào Q-Learning
q_state_key = pf.discretize_for_q()
```

### 🔹 Payload Dashboard (`payload_formatter.py`)
```python
def format_pf_payload(pf_state: PFState) -> dict:
    return {
        "component": "empathy_agent",
        "estimation": {
            "confusion": round(pf_state.confusion, 3),
            "fatigue": round(pf_state.fatigue, 3),
            "uncertainty": round(pf_state.uncertainty, 3)
        },
        "particle_cloud": pf_state.particle_cloud,  # [[c,f], ...]
        "weights": pf_state.weights,                # [w1, w2, ...]
        "ess": round(pf_state.ess, 1),
        "step": pf.step
    }
```

---
## 🧪 5. TESTING STRATEGY (`test_particle_filter.py`)
```python
import pytest, numpy as np
from agents.empathy_agent.particle_filter import ParticleFilter, PFState

@pytest.fixture
def pf():
    config = {"n_particles": 50, "process_noise": 0.05, "jitter_sigma": 0.01, "ess_threshold_ratio": 0.5}
    return ParticleFilter(config)

def test_init_bounds(pf):
    assert pf.particles.shape == (50, 2)
    assert np.all((pf.particles >= 0) & (pf.particles <= 1))
    assert np.isclose(pf.weights.sum(), 1.0)

def test_predict_preserves_bounds(pf):
    pf.predict()
    assert np.all((pf.particles >= 0) & (pf.particles <= 1))

def mock_likelihood(particles, signals):
    # Giả lập: response_time cao → fatigue cao được weight cao
    fatigue = particles[:, 1]
    rt = signals.get("response_time_ms", 8000)
    return -((rt - (8000 + 12000 * fatigue)) ** 2) / (2 * 3000**2)

def test_update_shifts_weight(pf):
    pf.update({"response_time_ms": 15000}, mock_likelihood)
    # Particle có fatigue cao phải có weight trung bình > 0.5
    high_fat_mask = pf.particles[:, 1] > 0.6
    assert np.mean(pf.weights[high_fat_mask]) > 0.02  # Threshold tùy chỉnh

def test_resample_maintains_count(pf):
    pf.weights[0] = 0.99
    pf.weights[1:] = 0.01 / (pf.n - 1)
    pf.resample()
    assert len(pf.particles) == pf.n
    assert np.isclose(pf.weights.sum(), 1.0)

def test_discretize_logic(pf):
    pf.particles[:, 0] = 0.7  # confusion cao
    pf.particles[:, 1] = 0.3  # fatigue thấp
    pf.weights = np.ones(pf.n) / pf.n
    assert pf.discretize_for_q() == "high_confusion_low_fatigue"
```

---
## 🛡️ 6. XỬ LÝ LỖI & FALLBACK
| Tình huống | Triệu chứng | Giải pháp trong code |
|------------|-------------|----------------------|
| `weights` underflow → `NaN` | `np.exp(log_weights)` âm vô cực | Dùng `log_weights - max(log_weights)` trước khi exp |
| Particle collapse (ESS ≈ 1) | `uncertainty ≈ 1.0`, dự đoán sai | `jitter_sigma=0.01` + `reset()` nếu conflict với `confidence_slider` |
| Tín hiệu thiếu/không hợp lệ | `signals` rỗng hoặc `NaN` | `try/except` trong `update()`, fallback `uniform weights`, log warning |
| Latency >50ms/step | WS backlog, UI giật | Vector hóa NumPy, không dùng `for`, gọi trong `asyncio.to_thread()` nếu cần |
| State vượt bound | `clip` fail do bug | `np.clip(..., 0.0, 1.0)` ở predict & resample, assert trong test |

**Fallback Policy:**
```python
if np.isnan(pf_state.confusion) or pf_state.uncertainty > 0.9:
    pf.reset(explicit_feedback={"confusion": 0.5, "fatigue": 0.5})
    logger.warning("PF reset due to instability")
```

---
## ✅ 7. DEFINITION OF DONE (PF)
- [ ] `ParticleFilter` class chạy đúng 4 bước: `predict → update → resample → get_state`
- [ ] Vectorized 100%, không dùng vòng lặp qua particle
- [ ] `discretize_for_q()` trả về string đúng format Q-Table
- [ ] Unit test coverage ≥ 85%, pass cả edge cases (NaN, empty signals, weight collapse)
- [ ] Payload dashboard đúng schema, ESS & uncertainty hiển thị realtime
- [ ] Fallback active khi instability, không crash orchestrator
- [ ] Config load từ YAML, không hardcode threshold
- [ ] Log đầy đủ: `step`, `ess`, `uncertainty`, `resample_triggered`, `latency_ms`

---
💡 **Lời khuyên Senior Architect:**
1. **Đừng tối ưu likelihood sớm.** Dùng Gaussian đơn giản trước. Chỉnh tham số sau khi có synthetic data.
2. **Log `ESS` mỗi bước.** Đây là metric vàng để chứng minh "Particle Filter State Estimation" hoạt động thực sự, không phải hardcode.
3. **Visualize particle cloud ngay.** Dùng `alpha=weights` trong scatter plot. Reviewer sẽ thấy rõ "đám mây dịch chuyển theo hành vi user".
4. **Giữ state trong memory.** Sync Supabase mỗi 5 bước. PF cần tốc độ, không cần persist từng step.