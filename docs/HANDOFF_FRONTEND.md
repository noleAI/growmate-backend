# HANDOFF FRONTEND - API Contract (P2)

Người tạo: Hưng (Data Engineering)  
Người nhận: Huy (Frontend)  
Cập nhật: 2026-04-16  
Base URL: `https://<YOUR_DOMAIN>/api/v1`

## 0) Phạm vi bản handoff này

- Scope hiện tại: P0/P1/P2.
- P3 (premium) đã được team quyết định tạm hoãn, chưa tích hợp trong đợt này.
- Tài liệu này chỉ mô tả endpoint đang dùng được ngay cho frontend.

---

## 1) Authentication

Tất cả endpoint business cần header:

```http
Authorization: Bearer <supabase_jwt_token>
```

Lỗi thường gặp:

```json
HTTP 401
{
  "detail": "Could not validate credentials"
}
```

---

## 2) Session APIs

### 2.1 Tạo session

`POST /sessions`

Request:

```json
{
  "subject": "math",
  "topic": "derivative",
  "mode": "exam_prep",
  "classification_level": "intermediate",
  "onboarding_results": {}
}
```

Ghi chú:
- `mode` hợp lệ: `exam_prep`, `explore`.
- Nếu bỏ trống `mode`, backend mặc định `explore`.
- Nếu `mode` không hợp lệ, trả `400`.
- Có giới hạn số session/ngày: nếu vượt trả `429 detail=quiz_rate_limit`.

Response mẫu:

```json
{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "active",
  "start_time": "2026-04-16T09:30:00+00:00",
  "initial_state": {
    "subject": "math",
    "topic": "derivative",
    "beliefs": {
      "H01_Trig": 0.25,
      "H02_ExpLog": 0.25,
      "H03_Chain": 0.25,
      "H04_Rules": 0.25
    },
    "student_id": "user-uuid",
    "classification_level": "intermediate",
    "mode": "exam_prep"
  }
}
```

### 2.2 Cập nhật trạng thái session

`PATCH /sessions/{session_id}`

Request:

```json
{
  "status": "completed"
}
```

`status` hợp lệ: `active`, `completed`, `abandoned`.

### 2.3 Tương tác session

`POST /sessions/{session_id}/interact`

Request mẫu:

```json
{
  "action_type": "submit_quiz",
  "quiz_id": "MATH_DERIV_1",
  "response_data": {
    "selected_option": "B",
    "time_taken_sec": 12,
    "behavior_signals": {
      "typing_speed": 0,
      "correction_rate": 0,
      "idle_time": 1.5
    }
  },
  "mode": "exam_prep",
  "classification_level": "intermediate",
  "xp_data": null,
  "is_off_topic": false,
  "resume": false
}
```

Response mẫu:

```json
{
  "next_node_type": "hint",
  "content": "Gợi ý: Hãy bắt đầu từ quy tắc đạo hàm phù hợp.",
  "plan_repaired": false,
  "belief_entropy": 0.72,
  "data_driven": null
}
```

Trường hợp hết tim (chỉ áp dụng khi action là submit quiz/answer và mode khác `explore`):

```json
HTTP 403
{
  "detail": "no_lives_remaining",
  "message": "Bạn đã hết tim! Hãy chờ hồi sinh hoặc xem lại bài cũ nhé.",
  "next_regen_in_seconds": 14400,
  "next_regen_at": "2026-04-16T18:00:00+00:00"
}
```

### 2.4 Kiểm tra session dở dang

Có 2 endpoint tương đương:
- `GET /sessions/pending`
- `GET /session/pending`

Response khi có session dở:

```json
{
  "has_pending": true,
  "session": {
    "session_id": "uuid",
    "status": "active",
    "last_question_index": 4,
    "total_questions": 10,
    "progress_percent": 40,
    "last_active_at": "2026-04-16T09:20:00+00:00",
    "abandoned_at": null
  }
}
```

Response khi không có:

```json
{
  "has_pending": false,
  "session": null
}
```

---

## 3) Quota API

### 3.1 Lấy quota hiện tại

`GET /quota`

Response:

```json
{
  "used": 7,
  "limit": 20,
  "remaining": 13,
  "reset_at": "2026-04-17T00:00:00+07:00"
}
```

Frontend đề xuất:
- Gọi khi vào màn hình học/chat.
- Nếu `remaining == 0`, khóa hành động tương ứng và hiện thông báo nhẹ nhàng.

---

## 4) Quiz APIs

### 4.1 Lấy câu tiếp theo

`GET /quiz/next?session_id=<id>&index=0&total_questions=10&mode=explore`

Response mẫu (MCQ):

```json
{
  "status": "ok",
  "mode": "explore",
  "timer_sec": null,
  "next_question": {
    "session_id": "sess-1",
    "question_id": "MATH_DERIV_1",
    "question_type": "MULTIPLE_CHOICE",
    "difficulty_level": 1,
    "content": "...",
    "media_url": null,
    "index": 0,
    "total_questions": 10,
    "progress_percent": 10,
    "options": [
      { "id": "C", "text": "..." },
      { "id": "A", "text": "..." },
      { "id": "D", "text": "..." },
      { "id": "B", "text": "..." }
    ]
  }
}
```

Ghi chú:
- Nếu `mode=exam_prep`, có `timer_sec=45`.
- Nếu hết câu:

```json
{
  "status": "completed",
  "session_id": "sess-1",
  "next_question": null
}
```

### 4.2 Submit đáp án

`POST /quiz/submit`

Request mẫu:

```json
{
  "session_id": "sess-1",
  "question_id": "MATH_DERIV_1",
  "selected_option": "B",
  "mode": "exam_prep"
}
```

Response chuẩn:

```json
{
  "session_id": "sess-1",
  "question_id": "MATH_DERIV_1",
  "is_correct": true,
  "explanation": "..."
}
```

Nếu sai và mode khác `explore`, response có thêm trạng thái tim:

```json
{
  "session_id": "sess-1",
  "question_id": "MATH_DERIV_1",
  "is_correct": false,
  "explanation": "...",
  "lives_remaining": 1,
  "can_play": true,
  "next_regen_in_seconds": 28800
}
```

Bảo mật:
- Backend không trả `correct_option_id` hoặc `correct_answer`.

### 4.3 HMAC signature cho quiz request

Áp dụng khi backend bật `QUIZ_HMAC_SECRET`.
Áp dụng cho cả:
- `POST /quiz/submit`
- `POST /sessions/{session_id}/interact` khi `action_type` là `submit_quiz` hoặc `submit_answer`

Headers:

```http
X-Growmate-Timestamp: <unix_seconds>
X-Growmate-Signature: <hex_signature>
```

`X-Growmate-Signature` cũng chấp nhận dạng `sha256=<hex_signature>`.

Payload ký:

```text
<METHOD>\n<PATH>\n<TIMESTAMP>\n<SHA256_HEX_OF_RAW_BODY>
```

Lỗi thường gặp:
- `401 missing_signature_headers`
- `401 invalid_signature_timestamp`
- `401 signature_expired`
- `401 invalid_signature`

---

## 5) Leaderboard / XP / Badges

### 5.1 Leaderboard

`GET /leaderboard?period=weekly&limit=20`

`period` hợp lệ: `weekly`, `monthly`, `all_time`.

Response mẫu:

```json
{
  "period": "weekly",
  "total_players": 156,
  "leaderboard": [
    {
      "rank": 1,
      "user_id": "uuid-1",
      "display_name": null,
      "avatar_url": null,
      "xp": 520,
      "streak": 7,
      "badge_count": 3,
      "weekly_xp": 520,
      "total_xp": 1400,
      "current_streak": 7,
      "longest_streak": 9
    }
  ]
}
```

### 5.2 Rank của user hiện tại

`GET /leaderboard/me?period=weekly`

Response mẫu:

```json
{
  "period": "weekly",
  "rank": 15,
  "user_id": "my-uuid",
  "display_name": null,
  "avatar_url": null,
  "weekly_xp": 230,
  "total_xp": 1500,
  "current_streak": 5,
  "longest_streak": 12,
  "badge_count": 3
}
```

### 5.3 Cộng XP

`POST /xp/add`

Request:

```json
{
  "event_type": "correct_answer",
  "extra_data": {
    "time_taken_sec": 8,
    "consecutive_correct": 3
  }
}
```

`event_type` hợp lệ:
- `correct_answer`
- `daily_login`
- `complete_quiz`
- `perfect_score`

Response mẫu:

```json
{
  "xp_added": 18,
  "breakdown": {
    "base_xp": 10,
    "streak_bonus": 5,
    "speed_bonus": 3,
    "total_xp": 18
  },
  "weekly_xp": 248,
  "total_xp": 1518,
  "current_streak": 6,
  "new_badges": [
    {
      "badge_type": "streak_7",
      "badge_name": "Kiên trì",
      "earned_at": "2026-04-16T09:35:00Z"
    }
  ]
}
```

### 5.4 Danh sách badge

`GET /badges`

Response mẫu:

```json
{
  "earned": [
    {
      "badge_type": "streak_7",
      "badge_name": "Kiên trì",
      "description": "Duy trì chuỗi học 7 ngày liên tiếp.",
      "icon": "flame",
      "earned_at": "2026-04-16T09:35:00Z"
    }
  ],
  "available": [
    {
      "badge_type": "top_10_weekly",
      "badge_name": "Top 10 Tuần",
      "description": "Lọt top 10 bảng xếp hạng tuần.",
      "icon": "trophy"
    }
  ],
  "badges": [
    {
      "badge_type": "streak_7",
      "badge_name": "Kiên trì",
      "description": "Duy trì chuỗi học 7 ngày liên tiếp.",
      "icon": "flame",
      "earned_at": "2026-04-16T09:35:00Z"
    }
  ]
}
```

---

## 6) Lives APIs

### 6.1 Lấy trạng thái tim

`GET /lives`

```json
{
  "current": 2,
  "max": 3,
  "can_play": true,
  "next_regen_in_seconds": 14400,
  "next_regen_at": "2026-04-16T18:00:00+00:00"
}
```

### 6.2 Trừ tim

`POST /lives/lose`

### 6.3 Hồi tim

`POST /lives/regen`

---

## 7) Formula Handbook API

### 7.1 Lấy danh sách công thức

`GET /formulas?category=all&search=<optional>`

`category` hợp lệ:
- `all`
- `basic_derivatives`
- `arithmetic_rules`
- `basic_trig`
- `exp_log`
- `chain_rule`

Response khi `category=all`:

```json
{
  "category": "all",
  "categories": [
    {
      "id": "basic_trig",
      "name": "Đạo hàm lượng giác",
      "description": "Các công thức sin, cos, tan và biến thể hàm hợp.",
      "formula_count": 6,
      "mastery_percent": 80,
      "formulas": [
        {
          "id": "sin_derivative",
          "title": "Đạo hàm hàm sin",
          "latex": "(\\sin x)' = \\cos x",
          "explanation": "Đạo hàm của sin bằng cos.",
          "example": "...",
          "example_latex": "...",
          "related_hypothesis": "H01_Trig",
          "difficulty": "easy",
          "keywords": ["sin"],
          "mastery_percent": 80,
          "mastery_status": "learned"
        }
      ]
    }
  ]
}
```

---

## 8) Onboarding + User Profile

### 8.1 Lấy bộ câu hỏi onboarding

`GET /onboarding/questions`

Response mẫu:

```json
{
  "topic": "derivative",
  "total_questions": 10,
  "questions": [
    {
      "question_id": "onb_01",
      "question": "Đạo hàm của x^2 là gì?",
      "options": ["2x", "x", "x^2", "2"],
      "difficulty": "easy"
    }
  ]
}
```

Ghi chú:
- Endpoint này không trả đáp án đúng (`correct`), chỉ trả dữ liệu cần render cho client.

### 8.2 Submit onboarding

`POST /onboarding/submit`

Request:

```json
{
  "answers": [
    { "question_id": "onb_01", "selected": "A", "time_taken_sec": 5 }
  ],
  "study_goal": "exam_prep",
  "daily_minutes": 20
}
```

`study_goal` hợp lệ: `exam_prep`, `explore`.

Response mẫu:

```json
{
  "user_level": "intermediate",
  "accuracy_percent": 62,
  "study_plan": {
    "daily_minutes": 20,
    "focus_areas": ["chain_rule", "trig"],
    "recommended_difficulty": 2,
    "difficulty": "mixed",
    "starting_hypothesis": "H04_Rules",
    "hint_policy": "adaptive"
  },
  "message": "Bạn đang ở level Intermediate. Cùng tiếp tục để tăng tốc nhé!",
  "onboarding_summary": {
    "total_questions": 10,
    "answered_questions": 10,
    "correct_answers": 6,
    "avg_response_time_ms": 8200
  }
}
```

### 8.3 User profile

- `GET /user/profile`
- `PUT /user/profile`

Response mẫu khi đọc profile:

```json
{
  "user_id": "uuid",
  "display_name": "Hưng",
  "avatar_url": null,
  "user_level": "intermediate",
  "study_goal": "exam_prep",
  "daily_minutes": 20,
  "onboarded_at": "2026-04-16T09:20:00Z",
  "created_at": "2026-04-15T08:00:00Z",
  "updated_at": "2026-04-16T09:25:00Z"
}
```

---

## 9) Error Handling Chung

Mã lỗi thường gặp:
- `400`: dữ liệu đầu vào không hợp lệ
- `401`: thiếu/invalid token hoặc signature
- `403`: chặn theo policy (ví dụ hết tim)
- `429`: vượt quota/rate limit
- `500`: lỗi backend

Format lỗi tiêu chuẩn:

```json
{
  "detail": "error_code_or_message"
}
```

---

## 10) Checklist Tích Hợp Frontend

- [ ] Đọc profile khi mở app để quyết định có vào onboarding hay không.
- [ ] Khi bắt đầu học, tạo session với `mode` rõ ràng (`exam_prep` hoặc `explore`).
- [ ] Trước và trong quiz, gọi `GET /lives` để hiển thị trạng thái tim.
- [ ] Nếu nhận `403 no_lives_remaining`, chuyển sang màn hình chờ hồi tim.
- [ ] Dùng `GET /session/pending` để hiện banner resume khi có bài dở.
- [ ] Chỉ render dữ liệu quiz backend trả về, không tự giữ đáp án đúng ở client.
- [ ] Nếu môi trường bật HMAC, gửi đủ headers signature cho quiz submit.

---

## 11) Phần Tạm Hoãn (P3 Premium)

Các hạng mục sau chưa nằm trong scope tích hợp hiện tại:
- Multiplayer quiz (WebSocket room)
- MANIM clip API
- Weekly plan API

Khi mở lại P3, backend sẽ phát hành handoff riêng để frontend triển khai tiếp.
