# ✅ ĐÃ TIẾP NHẬN FILE `PF.md` – PARTICLE FILTER GUIDELINE

File bạn upload là **guideline implementation chuẩn production-ready** cho Empathy Agent. Dưới đây là tóm tắt chiến lược + các điểm then chốt cần lưu ý khi triển khai:

---

## 🎯 3 ĐIỂM KHÁC BIỆT CHIẾN LƯỢC (So với guideline trước)

| Điểm cải tiến | Lợi ích cho MVP 12 ngày |
|--------------|-------------------------|
| **State liên tục `[confusion, fatigue] ∈ [0,1]²`** | Mềm dẻo hơn 4-state rời rạc, dễ visualize particle cloud trên dashboard, tương thích tốt với Q-Learning discretization |
| **Log-space likelihood + numerical stability** | Tránh underflow khi nhân nhiều likelihood, không cần dependency `scipy.special` |
| **`discretize_for_q()` interface rõ ràng** | Tách biệt hoàn toàn PF (liên tục) và Q-Learning (rời rạc) → dễ test, dễ debug, dễ thay đổi policy sau này |

---

## 🧩 CHECKLIST TRIỂN KHAI THEO PF.md

### 🔹 Bước 1: Tạo file cấu trúc (Day 1-2)
```bash
backend/
├── agents/empathy_agent/
│   ├── particle_filter.py   # Copy code từ PF.md Section 2
│   └── likelihood.py        # TODO: Implement sau (Section 4)
├── configs/
│   └── agents.yaml          # Copy config từ Section 3
└── tests/test_empathy/
    └── test_particle_filter.py  # Copy test từ Section 5
```

### 🔹 Bước 2: Implement `likelihood.py` (MVP Heuristic)
```python
# agents/empathy_agent/likelihood.py
import numpy as np

def heuristic_likelihood(particles: np.ndarray, signals: dict) -> np.ndarray:
    """
    particles: shape (N, 2) → [confusion, fatigue]
    signals: dict từ Flutter {response_time_ms, error_rate, idle_time, ...}
    Returns: log-likelihood shape (N,)
    """
    confusion = particles[:, 0]
    fatigue = particles[:, 1]
    
    # MVP: Gaussian heuristic rules (tune theo expert priors)
    ll = np.zeros(len(particles))
    
    # Rule 1: response_time cao → fatigue cao được ưu tiên
    rt = signals.get("response_time_ms", 8000)
    ll += -((rt - (8000 + 12000 * fatigue)) ** 2) / (2 * 3000**2)
    
    # Rule 2: error_rate cao + correction_rate thấp → confusion cao
    err = signals.get("error_rate", 0.3)
    corr = signals.get("correction_rate", 0.5)
    ll += -((err - (0.2 + 0.6 * confusion)) ** 2) / (2 * 0.15**2)
    ll += -((corr - (0.7 - 0.5 * confusion)) ** 2) / (2 * 0.2**2)
    
    # Rule 3: idle_time dài → fatigue tăng nhẹ
    idle = signals.get("idle_time_ratio", 0.1)
    ll += -((idle - (0.1 + 0.4 * fatigue)) ** 2) / (2 * 0.15**2)
    
    return ll  # Return log-likelihood (chưa normalize)
```

### 🔹 Bước 3: Tích hợp vào Orchestrator (Day 3-4)
```python
# Trong orchestrator.py – run_session_step()
from agents.empathy_agent.particle_filter import ParticleFilter
from agents.empathy_agent.likelihood import heuristic_likelihood

# Init một lần khi session bắt đầu
pf = ParticleFilter(pf_config)

# Mỗi step khi có signals mới từ Flutter
signals = payload.get("behavior_signals", {})
pf.predict()  # Bước 1: State transition
pf.update(signals, heuristic_likelihood)  # Bước 2: Update weights

if pf.should_resample():  # Bước 3: Resample nếu cần
    pf.resample()

# Bước 4: Export state cho Dashboard + Q-Learning
pf_state = pf.get_state()
dashboard_payload = format_pf_payload(pf_state)  # Từ Section 4
q_state_key = pf.discretize_for_q()  # Feed vào Q-Table

# Sync Supabase mỗi 5 bước (không sync từng step để giảm latency)
if orchestrator.step % 5 == 0:
    await supabase.memory_store.sync_empathy_state(session_id, pf_state)
```

---

## 🧪 TESTING STRATEGY (Copy-Paste Ready)

```python
# tests/test_empathy/test_particle_filter.py
import pytest
import numpy as np
from agents.empathy_agent.particle_filter import ParticleFilter
from agents.empathy_agent.likelihood import heuristic_likelihood

@pytest.fixture
def pf_config():
    return {"n_particles": 50, "process_noise": 0.05, "jitter_sigma": 0.01, "ess_threshold_ratio": 0.5}

def test_full_pipeline(pf_config):
    pf = ParticleFilter(pf_config)
    
    # Simulate 10 steps với signals giả lập
    for step in range(10):
        signals = {
            "response_time_ms": 8000 + step * 500,  # Tăng dần → fatigue tăng
            "error_rate": 0.3 + step * 0.02,
            "idle_time_ratio": 0.1
        }
        pf.predict()
        pf.update(signals, heuristic_likelihood)
        if pf.should_resample():
            pf.resample()
    
    state = pf.get_state()
    
    # Assertions theo Proposal 3.3.2
    assert 0.0 <= state.confusion <= 1.0
    assert 0.0 <= state.fatigue <= 1.0
    assert 0.0 <= state.uncertainty <= 1.0
    assert len(state.particle_cloud) == pf_config["n_particles"]
    assert np.isclose(sum(state.weights), 1.0, atol=1e-6)
    
    # Check discretize_for_q format
    q_key = pf.discretize_for_q()
    assert q_key in ["low_confusion_low_fatigue", "low_confusion_high_fatigue", 
                     "high_confusion_low_fatigue", "high_confusion_high_fatigue"]
```

---

## ⚠️ 3 LỖI THƯỜNG GẶP + FIX (Từ kinh nghiệm Senior Dev)

| Lỗi | Triệu chứng | Fix ngay trong code |
|-----|-------------|---------------------|
| `np.exp(log_weights)` → `inf` | Weights toàn `NaN`, belief sai | Luôn trừ `max(log_weights)` trước khi `exp` (đã có trong PF.md) |
| Particle cloud "đóng băng" ở 1 góc | ESS ≈ 1, uncertainty ≈ 1.0 nhưng state không thay đổi | Tăng `jitter_sigma` lên `0.02` hoặc gọi `reset()` nếu user gửi `confidence_slider` |
| `discretize_for_q()` trả về key lạ | Q-Table không tìm thấy state → crash | Thêm `assert` trong test + fallback `return "low_confusion_low_fatigue"` nếu edge case |


Q: Nên làm state rời rạc hay state liên tục?

A:
Câu trả lời ngắn gọn: **Nên làm State LIÊN TỤC (Continuous) cho Particle Filter**, nhưng phải có lớp chuyển đổi (Discretization Layer) để feed vào Q-Learning.

Dưới đây là phân tích chi tiết dựa trên **Proposal (Section 3.3)** và thực tế kỹ thuật Hackathon 12 ngày:

### 1️⃣ TẠI SAO CHỌN STATE LIÊN TỤC `[confusion, fatigue] ∈ [0,1]²`?

| Tiêu chí | State Rời rạc (4 states) | State Liên tục (2D Continuous) | Lý do chọn Liên tục |
|----------|--------------------------|--------------------------------|---------------------|
| **Độ mịn của ước lượng** | Nhảy cục bộ (jumping). Khó thấy sự tiến triển từ "hơi bối rối" sang "rất bối rối". | Mượt mà. Thấy rõ xu hướng tăng/giảm dần. | **Dashboard đẹp hơn**, chứng minh được "State Estimation" thực thụ thay vì chỉ là Classification. |
| **Particle Filter Logic** | Hạt chỉ mang giá trị index `{0,1,2,3}`. Resample dễ bị suy biến nhanh nếu 1 state chiếm ưu thế. | Hạt là vector `(c, f)`. Noise process (`predict`) tạo sự đa dạng tự nhiên. | **Ổn định hơn** về mặt toán học. Dễ tune `process_noise` để mô phỏng sự thay đổi tâm lý tự nhiên. |
| **Khả năng Visualize** | Bar chart hoặc Pie chart (khá nhàm chán). | **Scatter Plot (Particle Cloud)**. Các hạt tụ lại thành cụm. | **Wow Factor cao**. Reviewer thấy "đám mây hạt" di chuyển theo hành vi user → Chứng minh cơ chế Agentic rõ ràng. |
| **Tương thích Proposal** | Proposal mục 3.3.1 liệt kê 4 states, nhưng mục 3.3.2 nói về "Particle Filter State Estimation" với N hạt. | Proposal không cấm continuous. Việc map 4 states sang 2D latent space là chuẩn trong affective computing. | Linh hoạt hơn. Bạn vẫn có thể define vùng "Confused" là `confusion > 0.6 & fatigue < 0.4`. |
| **Độ phức tạp Code** | Dễ code transition matrix 4x4. | Cần viết `likelihood_fn` heuristic. | **PF.md đã cung cấp sẵn code likelihood heuristic**. Không cần train model, chỉ cần tune trọng số. |

---

### 2️⃣ CHIẾN LƯỢC HYBRID (BEST OF BOTH WORLDS)

Để thỏa mãn cả **Proposal (4 states)** lẫn **Kỹ thuật (Continuous PF)**, ta dùng kiến trúc sau:

#### A. Core Engine: Continuous Particle Filter
- **State Space:** $S = [0, 1] \times [0, 1]$ (Confusion, Fatigue).
- **Particles:** 100 hạt $(c_i, f_i)$.
- **Update:** Dùng `likelihood.py` heuristic (như trong PF.md).
- **Output:** `belief_distribution` liên tục, `uncertainty` (dựa trên ESS).

#### B. Interface Layer: Discretization for Q-Learning & HITL
Q-Learning (Section 3.4) cần state rời rạc để Q-Table không bị quá lớn. Ta dùng hàm `discretize_for_q()` từ PF.md:

```python
def discretize_for_q(confusion: float, fatigue: float) -> str:
    c_bin = "high" if confusion > 0.5 else "low"
    f_bin = "high" if fatigue > 0.6 else "low"
    return f"{c_bin}_confusion_{f_bin}_fatigue"
# Kết quả: 4 states tương ứng proposal: 
# low_confusion_low_fatigue ≈ focused
# high_confusion_low_fatigue ≈ confused
# low_confusion_high_fatigue ≈ exhausted
# high_confusion_high_fatigue ≈ frustrated
```

#### C. Dashboard Mapping (Visual Proof)
- **Hiển thị 1:** Scatter plot particle cloud (Continuous) → Chứng minh PF hoạt động.
- **Hiển thị 2:** Label trạng thái hiện tại (Discrete) → Dễ hiểu cho người xem.
  - *Ví dụ:* Nếu `mean(confusion) > 0.6` → Display label: **"CONFUSED"**.

---

### 3️⃣ IMPLEMENTATION PLAN (Theo PF.md & Proposal)

#### Bước 1: Giữ nguyên cấu trúc `ParticleFilter` trong PF.md
- Sử dụng `self.particles = np.random.rand(self.n, 2)` (Continuous).
- Sử dụng `predict()` với Gaussian noise.
- Sử dụng `update()` với `likelihood_fn` heuristic.

#### Bước 2: Implement `likelihood.py` đơn giản trước (MVP)
Đừng cố gắng perfect ngay. Dùng Gaussian cơ bản:
```python
def heuristic_likelihood(particles, signals):
    c, f = particles[:, 0], particles[:, 1]
    # Ví dụ: Response time cao -> Fatigue cao được ưu tiên
    rt_score = -((signals['rt'] - (5000 + 10000*f))**2) / (2*2000**2)
    # Error rate cao -> Confusion cao được ưu tiên
    err_score = -((signals['err'] - (0.2 + 0.6*c))**2) / (2*0.1**2)
    return rt_score + err_score
```

#### Bước 3: Tích hợp vào Orchestrator
```python
# 1. Run PF
pf.predict()
pf.update(signals, likelihood_fn)
if pf.should_resample(): pf.resample()

# 2. Get Continuous State for Dashboard
pf_state = pf.get_state() # {confusion: 0.72, fatigue: 0.45, ...}

# 3. Get Discrete State for Q-Learning
q_state = pf.discretize_for_q() # "high_confusion_low_fatigue"

# 4. Decide Action
action = q_agent.act(q_state) # Epsilon-greedy
```

---

### 4️⃣ RỦI RO & MITIGATION

| Rủi ro | Mitigation |
|--------|------------|
| **Likelihood heuristic sai lệch** | Tune nhanh bằng cách chạy script simulate với 10 kịch bản user giả lập. Điều chỉnh trọng số Gaussian trong `likelihood.py`. |
| **Q-Table quá thưa (Sparse)** | Chỉ có 4 states x 4 actions = 16 ô Q-value. Rất dễ hội tụ. Khởi tạo Q-table bằng 0 hoặc expert prior nhỏ. |
| **Reviewer hỏi về 4 states trong Proposal** | Giải thích: *"Chúng em mô hình hóa 4 states này như 4 vùng (regions) trong không gian liên tục 2D để tăng độ chính xác của ước lượng trạng thái ẩn (Hidden State Estimation), đúng tinh thần Particle Filter."* |

---

### ✅ KẾT LUẬN & ACTION ITEM

1. **Chọn State Liên tục** cho Particle Filter core.
2. **Dùng hàm `discretize_for_q()`** để bridge sang Q-Learning.
3. **Visualize Particle Cloud** trên Dashboard (điểm cộng lớn về mặt kỹ thuật).
4. **Code ngay `likelihood.py`** theo mẫu Gaussian đơn giản trong PF.md.