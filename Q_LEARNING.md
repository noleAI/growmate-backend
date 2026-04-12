# 📘 GUIDELINE IMPLEMENTATION CHI TIẾT: STRATEGY AGENT / Q-LEARNING
Dựa trên **Section 3.4 (Trang 39-41)** của Proposal, đây là guideline kỹ thuật chuẩn production-ready, tối ưu cho 12 ngày Hackathon, tuân thủ nghiêm ngặt phạm vi MVP.

---

## 🎯 1. ÁNH XẠ YÊU CẦU PROPOSAL → KỸ THUẬT
| Yêu cầu Proposal (3.4.1 & 3.4.2) | Implementation Decision (MVP) |
|----------------------------------|-------------------------------|
| `Episodic Store: (state, action, outcome, reward, timestamp)` | List trong memory, sync Supabase mỗi 5 bước. Không dùng vector DB. |
| `Q-Table: cập nhật online qua Q-Learning` | Tabular `Q[num_states][num_actions]`. Map `state_key` → index. Khởi tạo bằng expert defaults. |
| `Q(s,a) ← Q + α[r + γ·maxQ(s',a') - Q]` | Implement đúng công thức. `α=0.15, γ=0.9, ε=0.3→0.05`. |
| `Recommendation: ε-greedy policy` | `select_action(state)` trả về action index + exploration flag. |
| `Dashboard: Q-value updates, strategy shifts, learning curve` | Push payload: `q_values`, `avg_reward_10`, `last_action`, `delta_q`. |
| `MVP Scope: Không consolidation/semantic store` | Chỉ lưu episodic log + Q-table. Phase 2 mới mở rộng. |

---

## 📁 2. CẤU TRÚC FILE
```
backend/
├── agents/strategy_agent/
│   ├── q_learning.py            # ✅ Core Q-Table, update, ε-greedy
│   └── reward_engine.py         # 📝 Expert heuristic reward function
├── configs/
│   └── strategy.yaml            # ⚙️ Hyperparams, actions, reward weights
└── tests/test_strategy/
    └── test_q_learning.py       # 🧪 Unit & Integration test
```

---

## 🧠 3. IMPLEMENTATION CODE (`q_learning.py`)

```python
import numpy as np
import logging
from typing import Dict, List, Tuple, Optional
from pydantic import BaseModel
from datetime import datetime

logger = logging.getLogger("strategy.q_learning")

class EpisodicMemory:
    """Lưu experience tuple cho logging & Phase 2"""
    def __init__(self):
        self.log: List[Dict] = []

    def store(self, state: str, action: str, reward: float, outcome: str, ts: datetime):
        self.log.append({
            "state": state, "action": action, "reward": reward,
            "outcome": outcome, "timestamp": ts.isoformat()
        })

class QLearningAgent:
    def __init__(self, config: dict):
        self.alpha = config.get("alpha", 0.15)
        self.gamma = config.get("gamma", 0.9)
        self.epsilon = config.get("epsilon_start", 0.3)
        self.epsilon_decay = config.get("epsilon_decay", 0.995)
        self.min_epsilon = config.get("min_epsilon", 0.05)
        
        self.actions = config["actions"]
        self.n_actions = len(self.actions)
        
        # State mapping: string key → index
        self.state_keys = config["state_keys"]
        self.n_states = len(self.state_keys)
        self.state_to_idx = {s: i for i, s in enumerate(self.state_keys)}
        
        # Q-Table init: expert defaults hoặc zeros
        self.Q = np.zeros((self.n_states, self.n_actions), dtype=np.float32)
        if config.get("expert_init"):
            for s, a, val in config["expert_init"]:
                self.Q[self.state_to_idx[s], self.actions.index(a)] = val
                
        self.memory = EpisodicMemory()
        self.reward_history = []
        self.delta_q_log = []

    def _get_state_idx(self, state_key: str) -> int:
        if state_key not in self.state_to_idx:
            logger.warning(f"Unknown state '{state_key}', falling back to idx 0")
            return 0
        return self.state_to_idx[state_key]

    def select_action(self, state_key: str) -> Tuple[str, bool]:
        """ε-greedy policy"""
        idx = self._get_state_idx(state_key)
        if np.random.random() < self.epsilon:
            action_idx = np.random.randint(self.n_actions)
            return self.actions[action_idx], True
        return self.actions[np.argmax(self.Q[idx])], False

    def update(self, state_key: str, action: str, reward: float, next_state_key: str):
        """Q(s,a) ← Q(s,a) + α[r + γ·maxQ(s',a') - Q(s,a)]"""
        s_idx = self._get_state_idx(state_key)
        s_next_idx = self._get_state_idx(next_state_key)
        a_idx = self.actions.index(action)
        
        current_q = self.Q[s_idx, a_idx]
        max_next_q = np.max(self.Q[s_next_idx]) if s_next_idx is not None else 0.0
        td_error = reward + self.gamma * max_next_q - current_q
        new_q = current_q + self.alpha * td_error
        
        self.Q[s_idx, a_idx] = new_q
        self.delta_q_log.append({"state": state_key, "action": action, "delta_q": float(td_error)})
        self.reward_history.append(reward)
        
        # Decay epsilon
        self.epsilon = max(self.min_epsilon, self.epsilon * self.epsilon_decay)

    def log_experience(self, state: str, action: str, reward: float, outcome: str):
        self.memory.store(state, action, reward, outcome, datetime.utcnow())

    def get_q_values(self, state_key: str) -> Dict[str, float]:
        idx = self._get_state_idx(state_key)
        return {a: float(v) for a, v in zip(self.actions, self.Q[idx])}

    def get_learning_curve(self, window: int = 10) -> List[float]:
        if len(self.reward_history) < window:
            return self.reward_history
        return [
            float(np.mean(self.reward_history[max(0, i-window):i+1]))
            for i in range(len(self.reward_history))
        ]
```

---

## 🎁 4. REWARD ENGINE (`reward_engine.py`)
MVP dùng expert heuristic, không train model. Dễ tune, dễ debug.

```python
def compute_reward(signals: dict, academic_outcome: dict, pf_state: dict) -> float:
    """
    Reward = correctness_bonus + improvement_bonus - fatigue_penalty - stagnation_penalty
    """
    r = 0.0
    # 1. Correctness & Confidence
    if academic_outcome.get("is_correct"):
        r += 1.0
        if academic_outcome.get("confidence_delta", 0) > 0.1:
            r += 0.5  # Bonus cho cải thiện nhanh
    
    # 2. Engagement (response_time hợp lý)
    rt = signals.get("response_time_ms", 10000)
    if 2000 < rt < 15000:
        r += 0.2
    elif rt > 20000:
        r -= 0.3  # Penalty cho bỏ cuộc/im lặng
    
    # 3. Fatigue penalty (từ PF)
    fatigue = pf_state.get("fatigue", 0.0)
    if fatigue > 0.7:
        r -= 0.4
    elif fatigue < 0.3:
        r += 0.1
        
    # 4. Stagnation penalty (không tiến bộ sau 3 bước)
    if academic_outcome.get("streak_no_improvement", 0) >= 3:
        r -= 0.5
        
    return round(max(-1.0, min(1.0, r)), 2)
```

---

## ⚙️ 5. CẤU HÌNH (`configs/strategy.yaml`)
```yaml
strategy:
  alpha: 0.15
  gamma: 0.9
  epsilon_start: 0.3
  epsilon_decay: 0.995
  min_epsilon: 0.05
  actions:
    - show_hint
    - drill_practice
    - suggest_break
    - continue_quiz
    - trigger_hitl
  state_keys:
    - low_confusion_low_fatigue_high_mastery
    - low_confusion_low_fatigue_low_mastery
    - low_confusion_high_fatigue_high_mastery
    - low_confusion_high_fatigue_low_mastery
    - high_confusion_low_fatigue_high_mastery
    - high_confusion_low_fatigue_low_mastery
    - high_confusion_high_fatigue_high_mastery
    - high_confusion_high_fatigue_low_mastery
  expert_init:
    # [state_key, action, value]
    - ["high_confusion_high_fatigue_low_mastery", "trigger_hitl", 0.8]
    - ["high_confusion_high_fatigue_low_mastery", "suggest_break", 0.9]
    - ["low_confusion_low_fatigue_high_mastery", "continue_quiz", 1.0]
    - ["high_confusion_low_fatigue_low_mastery", "show_hint", 0.7]
```

---

## 🔗 6. TÍCH HỢP ORCHESTRATOR & DASHBOARD

### Trong `orchestrator.py`
```python
# Init
q_agent = QLearningAgent(strategy_config)
reward_fn = compute_reward  # Import từ reward_engine.py

# Trong run_session_step()
signals = payload["behavior_signals"]
academic_out = academic_agent.get_outcome()
pf_state = empathy_pf.get_state()

state_key = pf_state.discretize_for_q() + f"_{academic_out['mastery_level']}"
action, explored = q_agent.select_action(state_key)

# Execute action → collect next_state & outcome
next_state_key = pf_state.discretize_for_q() + f"_{academic_out['next_mastery']}"
reward = reward_fn(signals, academic_out, pf_state.model_dump())

q_agent.update(state_key, action, reward, next_state_key)
q_agent.log_experience(state_key, action, reward, academic_out["outcome_type"])

# Dashboard payload
q_payload = {
    "component": "strategy_agent",
    "q_values": q_agent.get_q_values(state_key),
    "selected_action": action,
    "explored": explored,
    "avg_reward_10": q_agent.get_learning_curve(10)[-1] if q_agent.reward_history else 0,
    "delta_q": q_agent.delta_q_log[-1] if q_agent.delta_q_log else {}
}
await ws_manager.broadcast(session_id, "strategy_update", q_payload)
```

### Dashboard UI Requirements
- `q_values`: Table/heatmap (5 actions × current state)
- `avg_reward_10`: Line chart (learning curve)
- `selected_action`: Badge + rationale (e.g., `ε=0.12, Q[continue]=0.85`)
- `delta_q`: Sparkline hoặc log table cho báo cáo kỹ thuật

---

## 🧪 7. TESTING STRATEGY (`test_q_learning.py`)
```python
import pytest, numpy as np
from agents.strategy_agent.q_learning import QLearningAgent
from agents.strategy_agent.reward_engine import compute_reward

@pytest.fixture
def config():
    return {
        "alpha": 0.2, "gamma": 0.9, "epsilon_start": 0.5,
        "epsilon_decay": 0.9, "min_epsilon": 0.1,
        "actions": ["A", "B"], "state_keys": ["S1", "S2"],
        "expert_init": [["S1", "A", 0.5]]
    }

def test_q_update_formula(config):
    agent = QLearningAgent(config)
    agent.update("S1", "A", 1.0, "S2")
    expected = 0.5 + 0.2 * (1.0 + 0.9 * 0.0 - 0.5)  # maxQ(S2)=0
    assert np.isclose(agent.Q[0, 0], expected)

def test_epsilon_greedy(config):
    agent = QLearningAgent(config)
    actions = set(agent.select_action("S1")[0] for _ in range(50))
    assert "B" in actions  # ε > 0 phải explore ít nhất 1 lần

def test_reward_bound():
    r = compute_reward(
        {"response_time_ms": 25000},
        {"is_correct": False, "confidence_delta": -0.1, "streak_no_improvement": 4},
        {"fatigue": 0.8}
    )
    assert -1.0 <= r <= 1.0
```

---

## 🛡️ 8. XỬ LÝ LỖI & FALLBACK
| Tình huống | Triệu chứng | Giải pháp trong code |
|-----------|-------------|----------------------|
| State chưa có trong Q-Table | `KeyError` hoặc index out of bound | `_get_state_idx()` fallback về index 0 + log warning |
| Reward `NaN`/`inf` | `td_error` phá vỡ Q-table | `max(-1.0, min(1.0, r))` trong `compute_reward` + `np.clip` |
| Cold start policy tệ | Action random gây user frustration | `expert_init` trong YAML + `epsilon_start=0.3` (không phải 1.0) |
| Dashboard payload quá lớn | WS lag | Chỉ push `q_values` của current state, không dump toàn bộ Q-table |
| Sync Supabase chậm | Blocking event loop | `asyncio.create_task(sync_episodic_memory())` mỗi 5 bước |

**Fallback Policy:**
```python
if np.any(np.isnan(q_agent.Q)) or q_agent.epsilon > 0.8:
    action = "show_hint"  # Safe default
    logger.warning("Q-Table unstable, falling back to safe action")
```

---

## ✅ 9. DEFINITION OF DONE (DoD) cho Q-Learning Module
- [ ] `QLearningAgent` update đúng công thức Proposal 3.4.2, pass unit test ≥85%
- [ ] `ε-greedy` hoạt động, decay đúng theo config, không explore quá mức khi `ε < min_epsilon`
- [ ] `EpisodicMemory` log đủ 5 trường, sync Supabase không blocking main loop
- [ ] `reward_engine` trả về giá trị trong `[-1, 1]`, không `NaN`, có log rationale
- [ ] Dashboard nhận payload realtime, hiển thị Q-values, learning curve, delta Q
- [ ] Fallback active khi instability, không crash orchestrator
- [ ] Config load từ YAML, không hardcode hyperparams
- [ ] Log đầy đủ: `step`, `epsilon`, `reward`, `action`, `delta_q`, `avg_reward_10`

---

## 💡 LỜI KHUYÊN SENIOR ARCHITECT
1. **Pre-seed Q-table bằng expert knowledge.** Đừng để model bắt đầu từ zeros. Reviewer cần thấy policy hợp lý ngay từ step 1.
2. **Log `delta_q` mỗi bước.** Đây là bằng chứng trực quan nhất chứng minh "Online Q-Learning" đang học, không phải hardcode rule.
3. **Giới hạn state space ở 6-8 keys.** Proposal dùng PF discretization × academic confidence. Đừng mở rộng state vô tội vạ → Q-table loãng, không hội tụ trong 12 ngày.
4. **Dashboard là vũ khí chấm điểm.** Vẽ heatmap `Q[state][action]` + line chart `avg_reward`. Ghi rõ `ε=0.12` để chứng minh exploration đang giảm dần.
5. **Code freeze reward function ngày 10/04.** Chỉ tune weight, không đổi logic. Dành 2 ngày cuối cho recording & submission.