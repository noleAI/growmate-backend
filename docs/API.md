# GrowMate Backend API - Frontend Integration Guide

Cập nhật: 2026-04-17  
Mục tiêu: Tài liệu API thực tế để frontend tích hợp trực tiếp với backend hiện tại.

## 1) Base URL và Authentication

Base REST API:
- `/api/v1`

Base WebSocket:
- `/ws/v1`

Tất cả endpoint protected yêu cầu JWT Supabase:

```http
Authorization: Bearer <SUPABASE_JWT>
```

### 1.1 HMAC cho quiz requests

Khi backend bật `QUIZ_HMAC_SECRET`, các request quiz sau cần thêm header:
- `POST /api/v1/quiz/submit`
- `POST /api/v1/sessions/{session_id}/interact` khi `action_type` là `submit_quiz` hoặc `submit_answer`

Headers:

```http
X-Growmate-Timestamp: <unix_seconds>
X-Growmate-Signature: <sha256_hex>  # hoặc format sha256=<sha256_hex>
```

Payload ký:
- method (uppercase)
- path
- timestamp
- sha256(body)

Nối bằng ký tự xuống dòng `\n` theo thứ tự trên.

Lỗi phổ biến:
- `401 missing_signature_headers`
- `401 invalid_signature_timestamp`
- `401 invalid_signature`
- `401 signature_expired`

Lưu ý resume grace:
- Với `POST /sessions/{session_id}/interact`, nếu request là resume flow (`resume=true`) thì backend có cơ chế grace TTL cho `signature_expired` để tránh reset trải nghiệm.

---

## 2) Session APIs

### 2.1 Tạo hoặc reuse session

`POST /api/v1/sessions`

Request:

```json
{
  "subject": "math",
  "topic": "derivative",
  "mode": "explore",
  "classification_level": "intermediate",
  "onboarding_results": {}
}
```

Response:

```json
{
  "session_id": "<uuid>",
  "status": "active",
  "start_time": "2026-04-17T10:00:00Z",
  "initial_state": {}
}
```

Ghi chú:
- Backend có behavior idempotent: nếu user đang có active session, API sẽ trả lại session đang active thay vì tạo session mới.

### 2.2 Cập nhật trạng thái session

`PATCH /api/v1/sessions/{session_id}`

Request:

```json
{
  "status": "completed"
}
```

`status` hợp lệ: `active`, `completed`, `abandoned`.

### 2.3 Lấy pending session (recommended)

`GET /api/v1/sessions/pending`

Response:

```json
{
  "has_pending": true,
  "session": {
    "session_id": "<uuid>",
    "status": "active",
    "last_question_index": 3,
    "next_question_index": 3,
    "total_questions": 10,
    "progress_percent": 30,
    "mode": "exam_prep",
    "pause_state": false,
    "pause_reason": null,
    "resume_context_version": 1,
    "last_active_at": "...",
    "abandoned_at": null
  }
}
```

Compat route vẫn hỗ trợ:
- `GET /api/v1/session/pending`

### 2.4 Gửi tương tác học tập

`POST /api/v1/sessions/{session_id}/interact`

Request:

```json
{
  "action_type": "submit_answer",
  "quiz_id": "MATH_DERIV_1",
  "response_data": {
    "answer": "A",
    "behavior_signals": {
      "response_time_ms": 3800,
      "idle_time_ratio": 0.08
    }
  },
  "xp_data": {},
  "mode": "exam_prep",
  "classification_level": "intermediate",
  "onboarding_results": {},
  "analytics_data": {},
  "is_off_topic": false,
  "resume": false
}
```

Response:

```json
{
  "next_node_type": "show_hint",
  "content": "...",
  "plan_repaired": false,
  "belief_entropy": 0.41,
  "data_driven": null
}
```

Lỗi business quan trọng:
- `403 no_lives_remaining` khi action quiz ở `exam_prep` và user hết tim.

---

## 3) Quiz APIs

### 3.1 Lấy câu hỏi kế tiếp

`GET /api/v1/quiz/next?session_id=<id>&index=0&total_questions=10&mode=explore`

Response:

```json
{
  "status": "ok",
  "mode": "explore",
  "timer_sec": null,
  "next_question": {}
}
```

Nếu hết câu:

```json
{
  "status": "completed",
  "session_id": "<id>",
  "next_question": null
}
```

### 3.2 Nộp bài quiz

`POST /api/v1/quiz/submit`  
Yêu cầu HMAC nếu bật `QUIZ_HMAC_SECRET`.

Request:

```json
{
  "session_id": "<id>",
  "question_id": "MATH_DERIV_1",
  "selected_option": "A",
  "answer": null,
  "answers": null,
  "time_taken_sec": 12.4,
  "mode": "exam_prep",
  "question_index": 0,
  "total_questions": 10
}
```

Response:

```json
{
  "session_id": "<id>",
  "question_id": "MATH_DERIV_1",
  "is_correct": true,
  "explanation": "...",
  "score": 1.0,
  "max_score": 1.0,
  "progress_percent": 10,
  "last_question_index": 1,
  "total_questions": 10,
  "quiz_summary": {
    "answered_count": 1,
    "correct_count": 1,
    "total_score": 1.0,
    "max_score": 1.0,
    "accuracy_percent": 100
  }
}
```

Khi sai ở mode khác `explore`, response có thể kèm:
- `lives_remaining`
- `can_play`
- `next_regen_in_seconds`

### 3.3 Kết quả chi tiết theo session

`GET /api/v1/quiz/sessions/{session_id}/result`

Response:

```json
{
  "status": "ok",
  "session_id": "<id>",
  "session_status": "completed",
  "progress_percent": 100,
  "last_question_index": 10,
  "total_questions": 10,
  "summary": {
    "answered_count": 10,
    "correct_count": 8,
    "total_score": 8.0,
    "max_score": 10.0,
    "accuracy_percent": 80
  },
  "attempts": [
    {
      "question_id": "MATH_DERIV_1",
      "question_template_id": "<uuid>",
      "question_type": "MULTIPLE_CHOICE",
      "is_correct": true,
      "score": 1.0,
      "max_score": 1.0,
      "explanation": "...",
      "user_answer": {},
      "submitted_at": "...",
      "time_taken_sec": 12.4
    }
  ],
  "started_at": "...",
  "ended_at": "..."
}
```

### 3.4 Lịch sử quiz

`GET /api/v1/quiz/history?limit=20&offset=0`

Response:

```json
{
  "status": "ok",
  "total": 2,
  "limit": 20,
  "offset": 0,
  "items": [
    {
      "session_id": "<id>",
      "status": "completed",
      "start_time": "...",
      "end_time": "...",
      "progress_percent": 100,
      "last_question_index": 10,
      "total_questions": 10,
      "summary": {}
    }
  ]
}
```

---

## 4) Progression APIs (Quota/XP/Leaderboard/Badges/Lives)

### 4.1 Quota

- `GET /api/v1/quota`
- Response fields: `used`, `limit`, `remaining`, `reset_at`

### 4.2 Leaderboard

- `GET /api/v1/leaderboard?period=weekly&limit=20`
- `GET /api/v1/leaderboard/me?period=weekly`

`period` hợp lệ: `weekly`, `monthly`, `all_time`.

### 4.3 XP

- `POST /api/v1/xp/add`

Request:

```json
{
  "event_type": "correct_answer",
  "extra_data": {
    "time_taken_sec": 8,
    "consecutive_correct": 2
  }
}
```

### 4.4 Badges

- `GET /api/v1/badges`

### 4.5 Lives

- `GET /api/v1/lives`
- `POST /api/v1/lives/lose`
- `POST /api/v1/lives/regen`

---

## 5) Onboarding, Profile, Formula APIs

### 5.1 Onboarding

- `GET /api/v1/onboarding/questions`
- `POST /api/v1/onboarding/submit`

Request submit:

```json
{
  "answers": [
    {
      "question_id": "onb_01",
      "selected": "A",
      "time_taken_sec": 5
    }
  ],
  "study_goal": "exam_prep",
  "daily_minutes": 20
}
```

### 5.2 User profile

- `GET /api/v1/user/profile`
- `PUT /api/v1/user/profile`

Request update:

```json
{
  "display_name": "Hung",
  "avatar_url": "https://...",
  "study_goal": "explore",
  "daily_minutes": 25
}
```

### 5.3 Formula handbook

- `GET /api/v1/formulas?category=all&search=chain`

`category` hợp lệ:
- `all`
- `basic_derivatives`
- `arithmetic_rules`
- `basic_trig`
- `exp_log`
- `chain_rule`

---

## 6) Orchestrator API

### 6.1 Run orchestrator step

`POST /api/v1/orchestrator/step`

Request:

```json
{
  "session_id": "<id>",
  "question_id": "MATH_DERIV_1",
  "response": {},
  "behavior_signals": {},
  "xp_data": {},
  "mode": "explore",
  "classification_level": "intermediate",
  "onboarding_results": {},
  "analytics_data": {},
  "is_off_topic": false,
  "resume": false
}
```

Response:

```json
{
  "status": "ok",
  "result": {
    "action": "show_hint",
    "payload": {},
    "dashboard_update": {},
    "reasoning_mode": "agentic",
    "reasoning_trace": [],
    "reasoning_content": "...",
    "reasoning_confidence": 0.8,
    "llm_steps": 2,
    "tool_count": 3,
    "fallback_used": false,
    "latency_ms": 900
  }
}
```

---

## 7) Inspection APIs (Ops / Debug)

- `GET /api/v1/inspection/belief-state/{session_id}`
- `GET /api/v1/inspection/particle-state/{session_id}`
- `GET /api/v1/inspection/q-values`
- `GET /api/v1/inspection/audit-logs/{session_id}`
- `GET /api/v1/inspection/runtime-metrics`
- `GET /api/v1/inspection/runtime-alerts`
- `GET /api/v1/inspection/runtime-alerts?dispatch=true`

---

## 8) Config APIs (Internal/Admin)

- `GET /api/v1/configs/{category}`
- `POST /api/v1/configs/{category}`

---

## 9) WebSocket Endpoints

### 9.1 Behavior telemetry stream

- `WS /ws/v1/behavior/{session_id}`

Client gửi JSON behavior signals liên tục. Server có thể push event:

```json
{
  "event": "intervention_proposed",
  "type": "recovery_mode",
  "confidence": 0.88,
  "session_id": "<id>",
  "state_summary": {
    "confusion": 0.4,
    "fatigue": 0.6,
    "uncertainty": 0.9
  }
}
```

### 9.2 Dashboard stream

- `WS /ws/v1/dashboard/stream` (global)
- `WS /ws/v1/dashboard/stream/{session_id}` (theo session)

---

## 10) Ghi Chú Tích Hợp Frontend

- Ưu tiên dùng `GET /api/v1/sessions/pending` cho flow resume; `GET /api/v1/session/pending` là route tương thích.
- Để render review sau quiz, dùng `GET /api/v1/quiz/sessions/{session_id}/result`.
- Để render lịch sử bài làm, dùng `GET /api/v1/quiz/history`.
- Khi xử lý mode `exam_prep`, frontend cần handle `403 no_lives_remaining` và countdown từ `next_regen_in_seconds`.
- Khi bật HMAC, frontend bắt buộc ký request quiz theo đúng format timestamp/signature.
