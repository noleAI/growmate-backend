Dưới đây là **5 Flow Test chuẩn** cho HTN Agent, được thiết kế sát 100% với `HTN_PLANNER.md` và `HTN_MODEL.md`. Mỗi flow bao gồm: Context khởi tạo, lộ trình chuyển trạng thái, Assertions kiểm chứng, và dữ liệu mock cần thiết. Team có thể chuyển thẳng thành `pytest` hoặc manual test script.

---
## 📋 TỔNG QUAN TEST MATRIX
| Flow ID | Tên | Mục tiêu kiểm chứng | Trạng thái `HTN_MODEL.md` được cover | MoSCOW |
|---------|-----|-------------------|--------------------------------------|--------|
| `F01` | **Standard Diagnosis (Happy Path)** | Luồng chuẩn không lỗi, preconditions pass, primitive success | `Pending → CheckPreconditions → Executing → EvaluateOutcome → Success → Completed` | `[M]` |
| `F02` | **Crisis Mode & De-stress** | Chuyển sang `M01_crisis_flow` khi entropy/fatigue cao, kích hoạt P09 | `CheckPreconditions → AltMethod → Executing → P09 trigger → Resume` | `[M]` |
| `F03` | **Plan Repair (AltMethod)** | Fail 1 lần → swap method → retry thành công, không crash | `EvaluateOutcome → Unexpected → Repairing → SelectStrategy(AltMethod) → ApplyRepair → RetryNode → Success` | `[M]` |
| `F04` | **Max Retry → HITL Escalation** | Fail 3 lần → vượt ngưỡng → push HITL → timeout 3s → fallback P09 | `Repairing → Escalate → HITL_Request → UserDecision(Timeout) → Fallback` | `[M]` |
| `F05` | **Belief Shift Dynamic Reroute** | Bayesian update làm thay đổi entropy giữa luồng → re-eval precondition → chuyển method | `Executing → BeliefShift → Repairing → Re-check → Switch Flow` | `[S]` |

---
## 🔍 CHI TIẾT TỪNG FLOW TEST

### 🔹 `F01: Standard Diagnosis (Happy Path)`
| Thành phần | Giá trị |
|------------|---------|
| **Context** | `{"entropy": 0.5, "fatigue": 0.3, "confusion": 0.4, "max_info_gain": 0.18}` |
| **Method chọn** | `M01_standard_flow → M02_quick_mcq → M03_info_gain_drill → M04_direct_drill → M06_post_test` |
| **Step-by-Step State** | `Pending` → `CheckPreconditions` (pass) → `Executing` (P04→P01→P02→P03 all return `success`) → `EvaluateOutcome` (Success) → `NodeCompleted` → `NextNode` |
| **Assertions** | ✅ `repair_log == []` ✅ `hitl_triggered == False` ✅ `plan_tree.depth ≤ 3` ✅ WS payload `status: "success"` ✅ Latency tổng < 1.5s |
| **Mock Setup** | Patch `PRIMITIVE_REGISTRY` trả `{"status": "success", "payload": {}}` cho tất cả P01-P12. |

---

### 🔹 `F02: Crisis Mode & Cognitive Load`
| Thành phần | Giá trị |
|------------|---------|
| **Context** | `{"entropy": 0.9, "fatigue": 0.8, "confusion": 0.7}` |
| **Method chọn** | `M01_crisis_flow → M05_empathy_check → M04_hint_first → M07_repair` |
| **Step-by-Step State** | `CheckPreconditions` (fails `M01_standard`) → `AltMethod` → `Executing` P08 → `fatigue > 0.7` → `P09_trigger_de_stress` → `pause_active=True` → resume → `P05_generate_hint` |
| **Assertions** | ✅ `P09` được gọi ✅ WS `/de_stress` payload gửi đúng ✅ LLM hint fallback active (mock timeout) ✅ `fatigue_score` giảm sau P09 |
| **Mock Setup** | `P08` trả `{"status": "success", "payload": {"fatigue": 0.82}}`. `P09` mock WS send. `P05` mock timeout → trigger fallback template. |

---

### 🔹 `F03: Plan Repair (AltMethod & Retry)`
| Thành phần | Giá trị |
|------------|---------|
| **Context** | `{"entropy": 0.6, "fatigue": 0.4, "M03_info_gain_drill_retries": 0}` |
| **Kịch bản** | `P04_select_next_question` fail lần 1 → `Repairing` → swap sang `M03_q_policy_drill` → retry → success |
| **Step-by-Step State** | `Executing` (P04) → `EvaluateOutcome` (`Unexpected`) → `Repairing` → `DiagnoseFailure` → `SelectStrategy(AltMethod)` → `ApplyRepair` → `RetryNode` → `Pending` → `Executing` (P04 với q_policy) → `Success` |
| **Assertions** | ✅ `repair_log` có 1 entry: `{"retry": 1, "strategy": "AltMethod", "reason": "Unexpected"}` ✅ `current_method == "M03_q_policy_drill"` ✅ Node kết thúc `SUCCESS` ✅ Không trigger HITL |
| **Mock Setup** | Counter mock: `call 1 → fail`, `call 2+ → success`. Patch `FALLBACK_METHOD_MAP["M03_info_gain_drill"] = "M03_q_policy_drill"`. |

---

### 🔹 `F04: Max Retry → HITL Escalation`
| Thành phần | Giá trị |
|------------|---------|
| **Context** | `{"entropy": 0.6, "fatigue": 0.4, "max_retries": 2}` |
| **Kịch bản** | `P04` fail liên tiếp 3 lần → vượt `max_retries` → `Escalate` → `HITL_Request` → timeout 3s → fallback `P09` |
| **Step-by-Step State** | `Executing` → fail ×3 → `Repairing` → `Escalate` → `HITL_Request` → `UserDecision` (mock 3s sleep) → `ResolveHITL` → `ApplyRepair(Fallback)` → `P09_trigger_de_stress` |
| **Assertions** | ✅ `hitl_queue` có record với `failed_task: "P04_select_next_question"` ✅ `timeout_sec == 3` ✅ `fallback_used == True` ✅ `repair_log.length == 2` (max retries) ✅ Session state chuyển `HITL_PENDING → RESOLVED` |
| **Mock Setup** | `P04` always fail. Mock `SupabaseClient.hitl.push()` verify payload. Mock `asyncio.sleep(3)`. |

---

### 🔹 `F05: Belief Shift Dynamic Reroute`
| Thành phần | Giá trị |
|------------|---------|
| **Context** | `{"entropy": 0.5, "fatigue": 0.3}` → Giữa luồng `P03_update_beliefs` trả về `entropy: 0.88` |
| **Kịch bản** | `C02` chạy → `P03` cập nhật belief → entropy vượt ngưỡng `0.85` → node tiếp theo `CheckPreconditions` fail → trigger `BeliefShift` → chuyển sang `M01_crisis_flow` |
| **Step-by-Step State** | `Executing` (C02) → `P03` → `EvaluateOutcome` (`BeliefShift`) → `Repairing` → `DiagnoseFailure` → `Re-check Precondition` → `SelectStrategy(AltMethod/Crisis)` → `ApplyRepair` → `Resume` |
| **Assertions** ✅ `plan_tree` có node `BeliefShift` log ✅ Method chuyển từ `M01_standard` sang `M01_crisis` ngay bước tiếp theo ✅ Không restart từ root, chỉ reroute từ current depth ✅ Dashboard hiển thị `event: "belief_shift_reroute"` |
| **Mock Setup** | `P03` trả `{"status": "success", "payload": {"entropy": 0.88, "belief_dist": {...}}}`. |

---
## 🧪 PYTEST SKELETON (Ready-to-Run)
```python
import pytest, asyncio, json
from unittest.mock import AsyncMock, patch
from agents.academic_agent.htn_planner import HTNPlanner, HTNNode, NodeState

@pytest.mark.asyncio
async def test_f01_happy_path():
    context = {"entropy": 0.5, "fatigue": 0.3, "confusion": 0.4}
    with patch("agents.academic_agent.htn_executor.PRIMITIVE_REGISTRY", new_callable=dict) as mock_reg:
        for k in mock_reg.keys(): mock_reg[k] = AsyncMock(return_value={"status": "success", "payload": {}})
        
        planner = HTNPlanner("configs/htn_rules.yaml")
        result = await planner.run_step("C02_assess_baseline", context)
        
        assert result["status"] == "success"
        assert len(planner.repair_log) == 0
        assert result["payload"]["node_state"] == NodeState.SUCCESS

@pytest.mark.asyncio
async def test_f04_hitl_escalation():
    context = {"entropy": 0.6, "fatigue": 0.4}
    mock_hitl = AsyncMock()
    with patch("agents.academic_agent.htn_executor.PRIMITIVE_REGISTRY") as mock_reg:
        for k in mock_reg.keys(): mock_reg[k] = AsyncMock(return_value={"status": "failed", "error": "mock"})
        mock_reg["P12_trigger_hitl"] = mock_hitl
        
        planner = HTNPlanner("configs/htn_rules.yaml", max_retries=2)
        result = await planner.run_step("C03_pinpoint_misconception", context)
        
        mock_hitl.assert_called_once()
        assert result["status"] == "hitl_escalated"
        assert "fallback" in result["payload"]
```

---
## 📊 VALIDATION VỚI INSPECTION DASHBOARD
| Dữ liệu WS cần kiểm tra | Flow áp dụng | Cách verify |
|------------------------|--------------|-------------|
| `plan_tree.nodes[].state` | F01, F03 | Màu sắc: `success=green`, `failed=red`, `repaired=yellow` |
| `repair_log[]` | F03, F04 | Count = 1 (F03) hoặc 2 + `hitl_escalated` (F04) |
| `belief_shift_detected` | F05 | `event: "belief_shift"` + `new_entropy > 0.85` |
| `hitl_queue.pushed` | F04 | Dashboard có badge `"👨‍🏫 Expert Review"` + timer 3s |
| `llm_fallback_used` | F02 | `hint_payload.source == "template"` thay vì `"llm"` |

---
## ✅ DEFINITION OF DONE (HTN TESTING)
- [ ] 5 flow trên chạy `pytest` pass 100%, không warning `RuntimeWarning: coroutine was never awaited`
- [ ] `coverage ≥ 80%` cho `htn_planner.py`, `htn_executor.py`, `state_manager.py`
- [ ] State diagram `HTN_MODEL.md` được verify bằng log: mỗi transition in ra `[HTN] {task_id} {old_state} → {new_state}`
- [ ] Mock Supabase & WS không crash khi gọi đồng thời 50 session
- [ ] `repair_log` và `hitl_queue` đồng bộ realtime lên dashboard < 1s
- [ ] Không có `eval()` injection risk: test với `context={"entropy": "0.5; import os; os.system('rm -rf /')"}` → trả `False` hoặc raise `ValueError`

---
## 🛡️ RỦI RO TEST & MITIGATION
| Rủi ro | Xác suất | Mitigation |
|--------|----------|------------|
| Mock primitive không khớp signature thực tế | Cao | Dùng `Pydantic` validate input/output của mock, fail fast nếu sai schema |
| Async timeout trong test làm flaky CI | Trung bình | Đặt `pytest-timeout`, mock `asyncio.sleep`, dùng `anyio` nếu cần |
| State leak giữa các test case | Trung bình | Dùng `fixture` tạo instance `HTNPlanner` mới mỗi test, clear `PRIMITIVE_REGISTRY` cache |
| Dashboard không render tree đúng JSON | Thấp | Export `plan_tree.json` sau mỗi flow, validate bằng `fl_chart` unit test |

---
💡 **Hướng dẫn execute nhanh:**
1. Copy 5 flow context vào `tests/data/htn_contexts.json`
2. Chạy `pytest tests/htn_flows/ -v --cov=agents.academic_agent`
3. Nếu fail tại `CheckPreconditions`, kiểm tra `safe_eval_precondition()` với context thực tế
4. Nếu fail tại `Repairing`, debug `retry_count` và `FALLBACK_METHOD_MAP`
5. Gắn hook vào CI: `pytest` pass → merge `develop` → deploy staging
