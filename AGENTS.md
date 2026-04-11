# 📘 GUIDELINE IMPLEMENTATION: AGENTIC CORE & ORCHESTRATOR
**Mục tiêu:** Xây dựng khung xử lý Agentic chuẩn, bất đồng bộ, dễ mở rộng. **Giữ nguyên cấu trúc code & luồng điều khiển**, để trống các chi tiết toán học/quy tắc nghiệp vụ của từng agent để team điền sau theo tiến độ.

---
## 📐 1. KIẾN TRÚC TỔNG THỂ & DATA FLOW
```
[Client Flutter] 
   ↓ POST /api/session/submit + WS behavior stream
[FastAPI Orchestrator] 
   ├─ 1. Validate payload → Load/Init session state
   ├─ 2. Run Agent Pipeline (async, dependency-aware)
   │     ├─ Academic Agent (Bayesian → HTN)
   │     ├─ Empathy Agent (Particle Filter)
   │     └─ Strategy Agent (Q-Learning → Memory)
   ├─ 3. Self-Monitor & HITL Check
   ├─ 4. Format Dashboard Payload + WS Broadcast
   └─ 5. Async Sync → Supabase → Return Next Action
```
**Nguyên tắc thiết kế:**
- ✅ **Async-first:** Toàn bộ pipeline dùng `asyncio`, không block event loop.
- ✅ **Stateless API, Stateful Session:** FastAPI không lưu state. Session state sống trong `dict` memory, sync Supabase mỗi 3 bước hoặc khi session kết thúc.
- ✅ **Config-Driven:** Tham số agent, threshold, prompt nằm trong `configs/agents.yaml`. Không hardcode.
- ✅ **Fail-Safe:** Mọi agent phải có `fallback` trả về action mặc định nếu exception/timeout.

---
## 📁 2. CẤU TRÚC THƯ MỤC CHUẨN
```
backend/
├── agents/
│   ├── base.py                # IAgent, IOrchestrator, BaseSessionState
│   ├── academic_agent/
│   │   ├── bayesian_tracker.py
│   │   └── htn_planner.py
│   ├── empathy_agent/
│   │   └── particle_filter.py
│   └── strategy_agent/
│       └── q_learning.py
├── core/
│   ├── config.py              # Load YAML, env vars
│   ├── state_manager.py       # In-memory cache + Supabase sync
│   ├── llm_service.py         # Async wrapper + fallback
│   └── payload_formatter.py   # Dashboard JSON builder
├── api/
│   ├── routes/session.py
│   └── ws/dashboard.py
├── configs/
│   └── agents.yaml            # ⚠️ PLACEHOLDER CHO CHI TIẾT AGENT
├── tests/
│   ├── test_agents/
│   └── test_orchestrator/
├── Dockerfile
└── main.py
```

---
## 🧩 3. BASE INTERFACES & CONTRACTS (`agents/base.py`)
```python
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pydantic import BaseModel

class AgentInput(BaseModel):
    session_id: str
    question_id: Optional[str] = None
    user_response: Optional[Dict[str, Any]] = None
    behavior_signals: Optional[Dict[str, Any]] = None
    current_state: Dict[str, Any] = {}

class AgentOutput(BaseModel):
    action: str
    payload: Dict[str, Any] = {}
    confidence: float = 0.5
    metadata: Dict[str, Any] = {}

class IAgent(ABC):
    @abstractmethod
    async def process(self, input_data: AgentInput) -> AgentOutput:
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        pass

class SessionState(BaseModel):
    session_id: str
    academic_state: Dict[str, Any] = {}
    empathy_state: Dict[str, Any] = {}
    strategy_state: Dict[str, Any] = {}
    hitl_pending: bool = False
    step: int = 0
```

---
## 🧠 4. ORCHESTRATOR SKELETON (`agents/orchestrator.py`)
```python
import asyncio, logging, time
from typing import Dict, Any
from .base import IAgent, AgentInput, AgentOutput, SessionState
from core.state_manager import StateManager
from core.llm_service import LLMService
from core.payload_formatter import format_dashboard_payload

logger = logging.getLogger("orchestrator")

class AgenticOrchestrator:
    def __init__(self, agents: Dict[str, IAgent], state_mgr: StateManager, llm: LLMService):
        self.agents = agents
        self.state_mgr = state_mgr
        self.llm = llm
        # TODO: Điền threshold từ configs/agents.yaml sau
        self.ENTROPY_THRESHOLD = 0.0
        self.FATIGUE_THRESHOLD = 0.0
        self.Q_STAGNATION_STEPS = 0
        self.MAX_HTL_RETRIES = 3

    async def run_session_step(self, session_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Luồng xử lý chính cho mỗi bước tương tác"""
        start_time = time.time()
        state = await self.state_mgr.load_or_init(session_id)
        
        # 1. Chuẩn bị input chung
        agent_input = AgentInput(
            session_id=session_id,
            question_id=payload.get("question_id"),
            user_response=payload.get("response"),
            behavior_signals=payload.get("behavior_signals"),
            current_state=state.model_dump()
        )

        # 2. Chạy Agent Pipeline (có thể điều chỉnh thành gather nếu độc lập)
        academic_out = await self.agents["academic"].process(agent_input)
        empathy_out = await self.agents["empathy"].process(agent_input)
        strategy_out = await self.agents["strategy"].process(agent_input)

        # 3. Merge state
        state.academic_state.update(academic_out.payload)
        state.empathy_state.update(empathy_out.payload)
        state.strategy_state.update(strategy_out.payload)
        state.step += 1

        # 4. Self-Monitor & HITL Check
        hitl_triggered = await self._check_self_monitor(state)
        if hitl_triggered and not state.hitl_pending:
            state.hitl_pending = True
            await self._trigger_hitl(session_id, state)

        # 5. Select Final Action (ưu tiên: HITL > Strategy > Academic Fallback)
        final_action = self._resolve_action(academic_out, empathy_out, strategy_out, state.hitl_pending)

        # 6. LLM Augmentation (nếu cần)
        if final_action in ["hint", "de_stress", "hitl_brief"]:
            llm_response = await self._call_llm_with_fallback(final_action, state)
            final_action_payload = {"text": llm_response.text, "fallback_used": llm_response.fallback_used}
        else:
            final_action_payload = {}

        # 7. Format & Broadcast
        dashboard_payload = format_dashboard_payload(state, final_action, final_action_payload)
        await self.state_mgr.broadcast_ws(session_id, dashboard_payload)
        
        # 8. Async Sync & Return
        asyncio.create_task(self.state_mgr.sync_to_supabase(session_id, state))
        latency_ms = int((time.time() - start_time) * 1000)
        
        return {
            "action": final_action,
            "payload": final_action_payload,
            "dashboard_update": dashboard_payload,
            "latency_ms": latency_ms
        }

    async def _check_self_monitor(self, state: SessionState) -> bool:
        # TODO: Điền logic kiểm tra entropy, PF collapse, Q-stagnation sau
        return False

    async def _trigger_hitl(self, session_id: str, state: SessionState):
        # TODO: Push to Supabase hitl_queue + WS notify
        pass

    def _resolve_action(self, academic: AgentOutput, empathy: AgentOutput, 
                        strategy: AgentOutput, hitl_pending: bool) -> str:
        if hitl_pending: return "hitl_pending"
        return strategy.action  # Ưu tiên Q-policy, fallback academic.action

    async def _call_llm_with_fallback(self, action_type: str, state: SessionState):
        prompt = self._build_prompt(action_type, state)
        fallback = self._get_fallback_template(action_type)
        return await self.llm.generate(prompt, fallback)

    # TODO: Thêm _build_prompt() và _get_fallback_template() sau
```

---
## 📝 5. AGENT CONFIGURATION PLACEHOLDERS (`configs/agents.yaml`)
```yaml
# ⚠️ FILE NÀY ĐỂ TRỐNG CÁC CHI TIẾT TOÁN HỌC/QUY TẮC. 
# Team sẽ điền sau khi xác nhận dữ liệu & chuyên gia.

academic:
  bayesian:
    hypotheses: []  # TODO: ["sign_error", "chain_rule_missing", "product_rule_confusion", ...]
    prior_weights: {}  # TODO: {"sign_error": 0.4, "chain_rule_missing": 0.3, ...}
    likelihood_matrix_path: "data/likelihood_template.csv"
  htn:
    root_task: "diagnose_derivative_concept"
    primitive_tasks: []  # TODO: ["ask_mcq", "ask_numerical", "give_hint", "switch_topic", ...]
    decomposition_rules_path: "configs/htn_rules_template.yaml"

empathy:
  particle_filter:
    n_particles: 100
    state_dimensions: []  # TODO: ["confusion_level", "fatigue_score"]
    state_bounds: {}  # TODO: {"confusion_level": [0.0, 1.0], "fatigue_score": [0.0, 1.0]}
    resampling_strategy: "systematic"  # systematic | multinomial
    observation_noise_sigma: 0.05

strategy:
  q_learning:
    states: []  # TODO: ["low_confusion_low_fatigue", "high_confusion_low_fatigue", ...]
    actions: []  # TODO: ["next_question", "give_hint", "drill_practice", "de_stress", "escalate_hitl"]
    alpha: 0.1
    gamma: 0.9
    epsilon_start: 0.3
    epsilon_min: 0.05
    q_table_seed_path: "data/q_table_seed.json"

orchestrator:
  self_monitor:
    entropy_threshold: 0.75  # TODO: điều chỉnh sau khi test prior
    pf_collapse_threshold: 0.15  # effective sample size / n_particles
    q_stagnation_steps: 3
  hitl:
    timeout_sec: 3
    fallback_action: "de_stress"
    max_concurrent_queue: 5
```

---
## 💾 6. STATE MANAGEMENT & SUPABASE SYNC (`core/state_manager.py`)
```python
import asyncio, json
from typing import Dict, Any
from supabase import create_client
from agents.base import SessionState

class StateManager:
    def __init__(self, supabase_url: str, supabase_key: str, ws_manager):
        self.supabase = create_client(supabase_url, supabase_key)
        self.ws = ws_manager
        self.cache: Dict[str, SessionState] = {}
        self.sync_counter: Dict[str, int] = {}

    async def load_or_init(self, session_id: str) -> SessionState:
        if session_id not in self.cache:
            # TODO: Ưu tiên load từ cache, nếu miss thì query Supabase
            self.cache[session_id] = SessionState(session_id=session_id)
            self.sync_counter[session_id] = 0
        return self.cache[session_id]

    async def sync_to_supabase(self, session_id: str, state: SessionState):
        self.sync_counter[session_id] += 1
        if self.sync_counter[session_id] % 3 == 0:  # Sync mỗi 3 bước
            await self._db_upsert("agent_state", {
                "session_id": session_id,
                "belief_dist": json.dumps(state.academic_state.get("belief_dist", {})),
                "particles": json.dumps(state.empathy_state.get("particles", [])),
                "q_values": json.dumps(state.strategy_state.get("q_table", {})),
                "updated_at": "now()"
            })
            self.sync_counter[session_id] = 0

    async def broadcast_ws(self, session_id: str, payload: Dict[str, Any]):
        await self.ws.send_to_session(session_id, json.dumps(payload))

    async def _db_upsert(self, table: str, data: Dict[str, Any]):
        # TODO: Implement Supabase upsert với retry
        pass
```

---
## 🧪 7. TESTING & INTEGRATION STRATEGY
| Loại test | Mục tiêu | Công cụ | File mẫu |
|-----------|----------|---------|----------|
| **Unit Agent** | Validate `process()` trả về `AgentOutput` đúng schema, không throw exception | `pytest`, `unittest.mock` | `tests/test_agents/test_bayesian.py` |
| **Orchestrator Routing** | Kiểm tra `_resolve_action()` ưu tiên đúng, HITL trigger đúng ngưỡng | `pytest-asyncio` | `tests/test_orchestrator/test_routing.py` |
| **State Sync** | Mock Supabase, kiểm tra cache → DB sync đúng tần suất | `pytest-mock` | `tests/test_core/test_state_mgr.py` |
| **LLM Fallback** | Mock timeout, verify fallback string được trả về <50ms | `aioresponses` | `tests/test_core/test_llm_service.py` |
| **E2E Flow** | Gửi payload giả lập → nhận action + dashboard payload → validate JSON | `httpx.AsyncClient` | `tests/integration/test_full_pipeline.py` |

**Quy tắc test:** 
- `coverage ≥ 75%` cho `orchestrator.py` & `state_manager.py`
- Mock toàn bộ I/O (DB, WS, LLM) trong unit test
- E2E test chạy trước khi merge vào `main`

---
## 📜 8. QUY TẮC CODE & BEST PRACTICES (12 NGÀY)
1. **Type Hints bắt buộc:** Dùng `pydantic` cho mọi input/output. Không dùng `Dict[str, Any]` tràn lan.
2. **Async/Await chuẩn:** Không dùng `time.sleep()`, `requests`, hoặc blocking DB calls. Dùng `asyncio.sleep()`, `httpx`, `supabase` async wrapper.
3. **Error Handling:** Mọi agent phải `try/except Exception as e: logger.error(...) → return fallback AgentOutput`.
4. **Logging chuẩn:** `logger.info(f"[{agent_name}] step={step} action={action} latency={ms}ms")`. Không `print()`.
5. **Git Flow:** `feature/agent-bayesian` → PR → Review bởi `Khang + Đức` → Merge `develop` → Weekly release tag.
6. **Config không commit secret:** Dùng `.env` cho Supabase key, LLM key. Commit `agents.yaml` template.

---
## ✅ CHECKLIST TRƯỚC KHI MERGE ORCHESTRATOR
- [ ] `agents/base.py` định nghĩa rõ `IAgent`, `AgentInput`, `AgentOutput`, `SessionState`
- [ ] `orchestrator.py` chạy được pipeline rỗng (mock agents), không crash
- [ ] `configs/agents.yaml` có cấu trúc đúng, placeholder rõ ràng
- [ ] `state_manager.py` cache + sync logic hoạt động với mock Supabase
- [ ] Unit test coverage `orchestrator.py` ≥ 75%
- [ ] WebSocket broadcast mock trả về JSON hợp lệ
- [ ] LLM service timeout & fallback hoạt động
- [ ] Không còn `TODO` blocking luồng chính (chỉ còn TODO điền config/math)

