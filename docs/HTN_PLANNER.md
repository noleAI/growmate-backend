Dưới đây là danh sách chi tiết **Primitive → Compound Tasks** cho HTN Planner, được thiết kế đúng chuẩn `HTN Planning` (có preconditions, methods, và execution sequence), đồng thời **tối ưu cho MVP 12 ngày** (dùng template-driven + dynamic method selection thay vì symbolic planning từ đầu).

---
## 📦 1. PRIMITIVE TASKS (Leaf Nodes – Executable Actions)
Là các hàm/backend call thực thi trực tiếp. Mỗi task trả về `{status: "success"|"failed", metadata}`.

| ID | Task Name | Mô tả | Input từ Context | Output/Effect | Backend Mapping |
|----|-----------|-------|------------------|---------------|-----------------|
| `P01` | `serve_mcq` | Đẩy câu hỏi MCQ sang Flutter, chờ response | `question_pool`, `topic` | `user_answer`, `response_time` | `POST /api/question/serve` |
| `P02` | `record_response` | Log đáp án, đúng/sai, thời gian | `answer`, `correct_key`, `time` | `result: correct/incorrect` | `DB: decision_log` |
| `P03` | `update_beliefs` | Gọi Bayesian tracker cập nhật posterior | `response`, `confidence` | `new_belief_dist`, `entropy` | `BayesianTracker.update()` |
| `P04` | `select_next_question` | Chọn câu hỏi theo Info Gain / Q-Value | `belief_dist`, `q_table` | `question_id` | `QuestionSelector.get_best()` |
| `P05` | `generate_hint` | Sinh gợi ý cá nhân hóa (LLM/Fallback) | `misconception_tag`, `confusion` | `hint_text` | `LLMService.generate()` |
| `P06` | `deliver_hint` | Hiển thị hint, kích hoạt retry UI | `hint_text` | `user_ack` | `WS: /hint` |
| `P07` | `start_drill` | Chuyển sang chế độ luyện sub-rule | `rule_type`, `count=3` | `drill_session_id` | `POST /api/drill/start` |
| `P08` | `check_fatigue` | Đọc trạng thái kiệt sức từ Particle Filter | `particle_state` | `fatigue_score` | `PF.get_state()["fatigue"]` |
| `P09` | `trigger_de_stress` | Hiển thị UI thư giãn, tạm dừng timer | `fatigue_score`, `msg` | `pause_active` | `WS: /de_stress` |
| `P10` | `log_plan_step` | Ghi hành động + kết quả vào decision log | `action`, `status`, `latency` | `log_id` | `Supabase: decision_log` |
| `P11` | `backtrack_repair` | Đánh dấu node fail, tăng retry, swap method | `failed_node`, `current_method` | `new_method`, `retry_count` | `HTNPlanner.repair()` |
| `P12` | `trigger_hitl` | Đẩy session vào queue expert, chờ 3s | `session_state`, `reason` | `hitl_status: pending/timeout` | `Supabase: hitl_queue` |

---
## 🌳 2. COMPOUND TASKS (Abstract Goals – Hierarchical Structure)
Các mục tiêu cấp cao, được phân rã thành methods → primitives.

| ID | Compound Task | Mục tiêu trong MVP | Phụ thuộc Agent |
|----|---------------|-------------------|-----------------|
| `C01` | `diagnose_derivative_mastery` | **Root Task** – Luồng chẩn đoán & can thiệp chính | All |
| `C02` | `assess_baseline` | Đo mức hiểu biết ban đầu, cập nhật prior → posterior | Bayesian (`belief_dist`) |
| `C03` | `pinpoint_misconception` | Xác định lỗi cụ thể (chain rule, sign error, ...) | Bayesian (`entropy`), Q (`q_values`) |
| `C04` | `deliver_intervention` | Cung cấp hint/drill phù hợp trạng thái | LLM, Q-Policy, PF |
| `C05` | `monitor_cognitive_load` | Giám sát bối rối/kiệt sức, điều chỉnh pacing | PF (`fatigue`, `confusion`) |
| `C06` | `validate_improvement` | Kiểm tra tiến độ sau can thiệp | Bayesian (`delta_confidence`) |
| `C07` | `handle_execution_failure` | Meta-task cho Plan Repair & HITL | Orchestrator, HTN State |

---
## 🔗 3. DECOMPOSITION METHODS (Selection Rules & Sequences)
Mỗi Compound Task có ≥1 Method. Orchestrator chọn method dựa trên **preconditions** từ agent states.

### 🔹 `C01: diagnose_derivative_mastery`
- `M01_standard_flow` (if `entropy < 0.85`):  
  `[C02_assess_baseline → C03_pinpoint_misconception → C04_deliver_intervention → C06_validate_improvement]`
- `M01_crisis_flow` (if `entropy ≥ 0.85` or `fatigue > 0.75`):  
  `[C05_monitor_cognitive_load → C04_deliver_intervention → C07_handle_execution_failure]`

### 🔹 `C02: assess_baseline`
- `M02_quick_mcq`:  
  `[P04_select_next_question → P01_serve_mcq → P02_record_response → P03_update_beliefs]`
- `M02_deep_parse` (if `open_text == true`):  
  `[P01_serve_mcq(open_text) → LLM_parse → P03_update_beliefs]` *(MVP: dùng M02_quick_mcq)*

### 🔹 `C03: pinpoint_misconception`
- `M03_info_gain_drill` (if `max_info_gain > 0.25`):  
  `[P04_select_next_question(max_IG) → P01_serve_mcq → P02_record_response → P03_update_beliefs]`
- `M03_q_policy_drill` (if `entropy ≤ 0.25`):  
  `[P04_select_next_question(q_policy) → P01_serve_mcq → P02_record_response → P03_update_beliefs]`

### 🔹 `C04: deliver_intervention`
- `M04_hint_first` (if `confusion > 0.6`):  
  `[P05_generate_hint → P06_deliver_hint → P07_start_drill(count=2)]`
- `M04_direct_drill` (if `confusion ≤ 0.6`):  
  `[P07_start_drill(count=3)]`

### 🔹 `C05: monitor_cognitive_load`
- `M05_empathy_check`:  
  `[P08_check_fatigue → (if fatigue > 0.7) P09_trigger_de_stress → resume]`

### 🔹 `C06: validate_improvement`
- `M06_post_test`:  
  `[P04_select_next_question(similar_topic) → P01_serve_mcq → P02_record_response → P03_update_beliefs]`

### 🔹 `C07: handle_execution_failure` *(Meta-Task)*
- `M07_repair`:  
  `[P11_backtrack_repair → retry failed subtask]`
- `M07_escalate` (if `retry_count ≥ 3`):  
  `[P12_trigger_hitl → wait 3s → (if timeout) fallback to P09_trigger_de_stress]`

---
## 🛠️ 4. PLAN REPAIR & HITL LOGIC (EXPLICIT)
```python
def repair_plan(failed_task: str, current_method: str, context: Dict) -> Tuple[str, bool]:
    """
    Trả về: (new_method, should_continue)
    """
    retry_key = f"{failed_task}_retries"
    retries = context.get(retry_key, 0)
    
    if retries < 2:
        # Swap sang phương án dự phòng trong config
        new_method = FALLBACK_METHOD_MAP[current_method]
        context[retry_key] = retries + 1
        return new_method, True
    else:
        # Vượt ngưỡng → HITL
        return "hitl_escalation", False
```
**Fallback Mapping (YAML):**
```yaml
repair_fallbacks:
  M03_info_gain_drill: "M03_q_policy_drill"
  M04_hint_first: "M04_direct_drill"
  M02_quick_mcq: "M04_hint_first"
  default: "M05_empathy_check"
```

---
## 📄 5. YAML CONFIG TEMPLATE (`configs/htn_rules.yaml`)
Dán trực tiếp vào repo, team chỉ cần điền `preconditions` & `question_pool` sau.
```yaml
htn_template:
  root_task: "diagnose_derivative_mastery"
  methods:
    M01_standard_flow:
      preconditions: "entropy < 0.85 AND fatigue < 0.75"
      sequence: ["C02_assess_baseline", "C03_pinpoint_misconception", "C04_deliver_intervention", "C06_validate_improvement"]
    M01_crisis_flow:
      preconditions: "entropy >= 0.85 OR fatigue >= 0.75"
      sequence: ["C05_monitor_cognitive_load", "C04_deliver_intervention", "C07_handle_execution_failure"]
  
  compound_tasks:
    C02_assess_baseline:
      methods: ["M02_quick_mcq"]
    C03_pinpoint_misconception:
      methods: ["M03_info_gain_drill", "M03_q_policy_drill"]
    C04_deliver_intervention:
      methods: ["M04_hint_first", "M04_direct_drill"]
    C05_monitor_cognitive_load:
      methods: ["M05_empathy_check"]
    C06_validate_improvement:
      methods: ["M06_post_test"]
    C07_handle_execution_failure:
      methods: ["M07_repair", "M07_escalate"]

  primitives:
    - id: P01_serve_mcq
    - id: P02_record_response
    - id: P03_update_beliefs
    - id: P04_select_next_question
    - id: P05_generate_hint
    - id: P06_deliver_hint
    - id: P07_start_drill
    - id: P08_check_fatigue
    - id: P09_trigger_de_stress
    - id: P10_log_plan_step
    - id: P11_backtrack_repair
    - id: P12_trigger_hitl

  repair_limits:
    max_retries_per_node: 2
    max_depth: 3
    hitl_timeout_sec: 3
    fallback_on_timeout: "P09_trigger_de_stress"
```

---
💡 **Lưu ý kỹ thuật quan trọng:**
1. **Đừng implement full symbolic HTN solver.** Trong MVP, dùng **Template-Driven Execution**: load cây YAML → duyệt theo sequence → check precondition tại mỗi bước → gọi primitive. Đủ chứng minh cơ chế, nhẹ, chạy ổn định.
2. **Precondition evaluation:** Dùng `eval()` với `safe_dict` chứa `entropy`, `fatigue`, `confusion` từ agent states. Hoặc viết parser đơn giản `if-elif` cho nhanh.
3. **Plan Repair không cần backtracking phức tạp.** Chỉ cần: `current_node.status = "failed" → parent.retry_count += 1 → swap method → resume`. Log đủ cho dashboard.
4. **Dashboard visualization:** Dùng `tree_structure` JSON để render `fl_chart` hoặc `custom_painter`. Màu: `pending=gray`, `active=blue`, `success=green`, `failed=red`, `repaired=yellow`.
