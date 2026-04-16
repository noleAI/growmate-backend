# 📋 Data Engineering — Kế Hoạch Chi Tiết Cho Hưng

> Cập nhật: 16/04/2026 — Trích xuất từ `TEAM_TASK_PLAN.md`
> Vai trò: **Data Engineering** — Supabase, Data files, API endpoints, Database administration
> Quyết định hiện tại: **dừng triển khai ở P2**, toàn bộ hạng mục P3 (premium) được tạm hoãn cho giai đoạn sau.

---

## Mục Lục

- [PHASE 1 — P0: Nền Tảng (Tuần 1-2)](#phase-1--p0-nền-tảng-tuần-1-2)
- [PHASE 2 — P1: Gamification (Tuần 3-4)](#phase-2--p1-gamification-tuần-3-4)
- [PHASE 3 — P2: Nâng Cao (Tuần 5-6)](#phase-3--p2-nâng-cao-tuần-5-6)
- [PHASE 4 — P3: Premium (Tuần 7-8, tạm hoãn)](#phase-4--p3-premium-tuần-7-8-tạm-hoãn)
- [PHASE 5 — Bonus (Tuần 9+)](#phase-5--bonus-tuần-9)

---

## PHASE 1 — P0: Nền Tảng (Tuần 1-2)

### 🔖 Mục 1: Thu Hẹp Scope Toán Học — Soạn Câu Hỏi & Import Data

#### Task 1.1: ✅ Kiểm tra file câu hỏi đã tạo `quiz_question_template_normalized.ndjson`

> **Trạng thái**: Đã curate dữ liệu lên 73 câu, normalize LaTeX, hoàn tất coverage 4 hypotheses và rà chất lượng explanation/schema.

- [x] **1.1.1** Kiểm tra tổng số câu hỏi hiện có (73 câu)
- [x] **1.1.2** Kiểm tra schema mỗi record — 73/73 record đủ các trường bắt buộc:
  - `subject`, `topic_code`, `topic_name`, `exam_year`, `question_type`
  - `part_no`, `difficulty_level`, `content`
  - `payload` (options, correct_option_id, explanation)
  - `metadata` (source_question_id, source_provider, crawl_time, quality_status, tags)
  - `is_active`, `media_url`
- [x] **1.1.3** ⚠️ **Bổ sung cột `grade_level`** — Đã chuẩn hóa `grade_level` cho 50/50 records bằng script `backend/scripts/normalize_quiz_questions.py`.
  - Viết script Python đọc file → parse mỗi dòng JSON → thêm `"grade_level": 11` → ghi lại file
  - Hoặc dùng `jq` / text editor find-replace
  - Xác nhận 50/50 dòng đều có `grade_level: 11` sau khi sửa
- [x] **1.1.4** Kiểm tra phân bố difficulty_level:
  - Mục tiêu: ~15 câu dễ (level 1), ~25 câu trung bình (level 2), ~20 câu khó (level 3)
  - Đếm thực tế sau curate: level 1 = 18, level 2 = 30, level 3 = 25
- [x] **1.1.5** Kiểm tra phân bố question_type:
  - Hiện có: `MULTIPLE_CHOICE`, `SHORT_ANSWER`, `TRUE_FALSE_CLUSTER`
  - Đếm thực tế: MCQ = 42, SA = 19, TF cluster = 12
- [x] **1.1.6** Kiểm tra coverage cho 4 hypotheses (dùng trường `tags` trong `metadata`):
  - `H01_Trig` (Đạo hàm lượng giác) — tags chứa: `trigonometry`, `trigonometric_function`
  - `H02_ExpLog` (Đạo hàm mũ & logarit) — tags chứa: `exponential_function`
  - `H03_Chain` (Chain Rule) — tags chứa: `chain_rule`
  - `H04_Rules` (Quy tắc tính) — tags chứa: `power_rule`, `product_rule`, `quotient_rule`, `rules`
  - **Mỗi hypothesis cần ít nhất 10 câu** → hiện tại: `H01=10`, `H02=10`, `H03=10`, `H04=43`
- [x] **1.1.7** Kiểm tra chất lượng explanation — đã xử lý explanation yếu/rỗng, hiện không còn explanation rỗng dưới ngưỡng kiểm tra
- [x] **1.1.8** Kiểm tra tính chính xác toán học — đã rà soát và sửa các lỗi tính toán/phát biểu phát hiện được trong đợt curate
- [x] **1.1.9** Thêm trường `hypothesis_tag` vào mỗi record nếu chưa có (đã tự động gán qua script normalize khi thiếu)

#### Task 1.2: Import vào Supabase

- [x] **1.2.1** Xác nhận schema table `quiz_question_template` trên Supabase khớp với JSON format
- [x] **1.2.2** Viết script import `backend/scripts/import_quiz_questions.py`:
  ```
  - Đọc file NDJSON
  - Validate mỗi record
  - Upsert vào Supabase (tránh duplicate)
  - Log kết quả: success/fail count
  ```
- [ ] **1.2.3** Chạy import và xác nhận 50+ câu hỏi trong DB (blocker: thiếu env `SUPABASE_URL` và `SUPABASE_KEY` trên máy local hiện tại)
- [ ] **1.2.4** Kiểm tra dữ liệu trên Supabase Dashboard — query thử vài câu (thực hiện sau khi set env và import thành công)

#### Task 1.3: Cập nhật Diagnosis Scenarios

- [x] **1.3.1** Review file `backend/data/diagnosis/diagnosis_scenarios.json` (đã rà lại và mở rộng)
- [x] **1.3.2** Xác nhận các `interventionPlan` IDs hợp lệ với catalog interventions
- [x] **1.3.3** Đảm bảo `nextSuggestedTopic` = `"derivative"` cho tất cả scenarios
- [x] **1.3.4** Đã thêm scenarios theo từng hypothesis yếu (`H01`, `H02`, `H03`, `H04`)

**📌 Tiêu chí hoàn thành:**
- ✅ 50+ câu hỏi trong DB, có `grade_level: 11`
- ✅ Đủ coverage cho 4 hypotheses, mỗi hypothesis ≥ 10 câu
- ✅ Diagnosis scenarios khớp 4 hypotheses mới

---

### 🔖 Mục 2: Xây Dựng Bảng Công Thức Tra Cứu

#### Task 2.1: Tạo `formula_lookup.json`

- [x] **2.1.1** Tạo file `backend/data/formula_lookup.json`
- [x] **2.1.2** Soạn 30+ công thức đạo hàm cơ bản, chia theo nhóm (đã có 32 công thức):
  - **Nhóm 1: Đạo hàm cơ bản** (8-10 công thức)
    - `(c)' = 0`, `(x^n)' = nx^{n-1}`, `(kx)' = k`, `(√x)' = 1/(2√x)`, ...
  - **Nhóm 2: Đạo hàm lượng giác** (6-8 công thức)
    - `(sin x)' = cos x`, `(cos x)' = -sin x`, `(tan x)' = 1/cos²x`, ...
  - **Nhóm 3: Đạo hàm mũ & logarit** (4-6 công thức)
    - `(e^x)' = e^x`, `(a^x)' = a^x·ln a`, `(ln x)' = 1/x`, ...
  - **Nhóm 4: Quy tắc tính** (4-6 công thức)
    - `(u ± v)' = u' ± v'`, `(uv)' = u'v + uv'`, `(u/v)' = (u'v - uv')/v²`
  - **Nhóm 5: Chain Rule** (3-4 công thức)
    - `[f(g(x))]' = f'(g(x))·g'(x)`, ví dụ cụ thể
- [x] **2.1.3** Mỗi công thức có đầy đủ:
  ```json
  {
    "id": "sin_derivative",
    "latex": "(\\sin x)' = \\cos x",
    "explanation": "Đạo hàm của sin x bằng cos x",
    "example": "(\\sin 3x)' = 3\\cos 3x",
    "related_hypothesis": "H01",
    "difficulty": "easy",
    "keywords": ["sin", "lượng giác", "trigonometry"]
  }
  ```
- [x] **2.1.4** Validate LaTeX syntax cho tất cả công thức (basic validation: đủ fields, cân bằng dấu `{}`)

**📌 Tiêu chí hoàn thành:**
- ✅ 30+ công thức có đầy đủ LaTeX, explanation
- ✅ Dùng được cho intent lookup (fast-path if-else)

---

### 🔖 Mục 3: Token Usage & Quota API

#### Task 3.1: Tạo Supabase table `user_token_usage`

- [x] **3.1.1** Viết migration SQL (`sql/user_token_usage.sql`):
  ```sql
  CREATE TABLE user_token_usage (
    user_id UUID,
    date DATE,
    call_count INT DEFAULT 0,
    total_tokens INT DEFAULT 0,
    PRIMARY KEY (user_id, date)
  );
  ```
- [x] **3.1.2** Thêm RLS policies (user chỉ đọc/ghi được row của mình)
- [x] **3.1.3** Áp dụng cơ chế reset theo ngày bằng primary key `(user_id, date)` + tạo row mới mỗi ngày

#### Task 3.2: API endpoint `/api/v1/quota`

- [x] **3.2.1** Tạo file `backend/api/routes/quota.py`
- [x] **3.2.2** Implement `GET /api/v1/quota`:
  ```json
  Response: {
    "used": 15,
    "limit": 20,
    "remaining": 5,
    "reset_at": "2026-04-16T00:00:00+07:00"
  }
  ```
- [x] **3.2.3** Implement logic increment counter khi LLM được gọi (orchestrator `_track_llm_usage`)
- [x] **3.2.4** Register route vào `main.py`
- [x] **3.2.5** Viết unit test cho quota endpoint (`backend/tests/test_core/test_quota_route.py`)

**📌 Tiêu chí hoàn thành:**
- ✅ Counter reset lúc 00:00
- ✅ API `/quota` hoạt động chính xác
- ✅ Frontend nhận được đúng dữ liệu

---

## PHASE 2 — P1: Gamification (Tuần 3-4)

### 🔖 Mục 4: Leaderboard, XP, Badges

#### Task 4.1: Tạo Supabase tables

- [x] **4.1.1** Tạo migration SQL cho table `user_xp` (`sql/user_xp.sql`):
  ```sql
  CREATE TABLE user_xp (
    user_id UUID PRIMARY KEY,
    weekly_xp INT DEFAULT 0,
    total_xp INT DEFAULT 0,
    current_streak INT DEFAULT 0,
    longest_streak INT DEFAULT 0,
    last_active_date DATE,
    updated_at TIMESTAMPTZ DEFAULT now()
  );
  ```
- [x] **4.1.2** Tạo migration SQL cho table `user_badges` (`sql/user_badges.sql`):
  ```sql
  CREATE TABLE user_badges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID,
    badge_type TEXT,
    badge_name TEXT,
    earned_at TIMESTAMPTZ DEFAULT now()
  );
  ```
- [x] **4.1.3** Thêm RLS policies cho cả 2 tables (đã khai báo trong SQL migrations)
- [x] **4.1.4** Tạo index cho `user_xp.weekly_xp DESC` (đã khai báo trong migration)
- [ ] **4.1.5** Tạo cron job/trigger reset `weekly_xp = 0` vào đầu tuần (Thứ 2, 00:00) trên Supabase thực tế (mới tạo helper function `reset_weekly_xp`, chưa schedule production)

#### Task 4.2: XP Calculation Logic

- [x] **4.2.1** Tạo `backend/core/xp_engine.py`:
  ```python
  XP_RULES = {
      "correct_answer": 10,
      "streak_bonus": 5,       # mỗi câu đúng liên tiếp
      "speed_bonus": 3,        # trả lời < 10 giây
      "daily_login": 20,
      "complete_quiz": 50,
      "perfect_score": 100,
  }
  ```
- [x] **4.2.2** Implement flow cộng XP trong `POST /api/v1/xp/add` (dùng `xp_engine` + `supabase_client`)
- [x] **4.2.3** Implement streak tracking logic (tính `current_streak`, `longest_streak`, `last_active_date`)
- [x] **4.2.4** Viết unit tests cho xp_engine (`backend/tests/test_core/test_xp_engine.py`)

#### Task 4.3: Badge Awarding Logic

- [x] **4.3.1** Thêm logic badge candidates trong `xp_engine.py`:
  - Streak 7 ngày → badge "Kiên trì"
  - Top 10 tuần → badge "Siêu sao tuần"
  - Mastery 100% 1 topic → badge "Chiến thần [Topic]"
- [x] **4.3.2** Auto-check badge trong `POST /api/v1/xp/add`
- [x] **4.3.3** Viết unit tests cho badge awarding (bao gồm trong `test_xp_engine.py` và `test_leaderboard_route.py`)

#### Task 4.4: API Endpoints

- [x] **4.4.1** Tạo file `backend/api/routes/leaderboard.py`
- [x] **4.4.2** `GET /api/v1/leaderboard?period=weekly&limit=20` — Top users theo tuần
  ```json
  Response: {
    "period": "weekly",
    "leaderboard": [
      { "rank": 1, "user_id": "...", "display_name": "...", "xp": 500, "avatar_url": "..." },
      ...
    ]
  }
  ```
- [x] **4.4.3** `GET /api/v1/leaderboard/me` — Vị trí của user hiện tại
  ```json
  Response: {
    "rank": 15,
    "user_id": "...",
    "weekly_xp": 230,
    "total_xp": 1500,
    "current_streak": 5,
    "badges_count": 3
  }
  ```
- [x] **4.4.4** `POST /api/v1/xp/add` — Cộng XP (internal, gọi sau quiz)
  ```json
  Request: { "event_type": "correct_answer", "extra_data": { "time_taken": 8 } }
  Response: { "xp_added": 13, "total_xp": 1513, "new_badges": [] }
  ```
- [x] **4.4.5** `GET /api/v1/badges` — Danh sách badges của user
  ```json
  Response: {
    "badges": [
      { "badge_type": "streak_7", "badge_name": "Kiên trì", "earned_at": "..." }
    ]
  }
  ```
- [x] **4.4.6** Register tất cả routes vào `main.py`
- [x] **4.4.7** Viết unit tests cho các endpoints mới (`backend/tests/test_core/test_leaderboard_route.py`)

**📌 Tiêu chí hoàn thành:**
- ✅ API trả đúng leaderboard data
- ✅ XP tính đúng theo rules
- ✅ Badges auto-award khi đạt điều kiện

---

### 🔖 Mục 5: Hệ Thống Tim (Lives)

#### Task 5.1: Tạo Supabase table

- [x] **5.1.1** Tạo table `user_lives` (`sql/user_lives.sql`):
  ```sql
  CREATE TABLE user_lives (
    user_id UUID PRIMARY KEY,
    current_lives INT DEFAULT 3 CHECK (current_lives >= 0 AND current_lives <= 3),
    last_life_lost_at TIMESTAMPTZ,
    last_regen_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ DEFAULT now()
  );
  ```
- [x] **5.1.2** Thêm RLS policies

#### Task 5.2: Lives Engine

- [x] **5.2.1** Tạo `backend/core/lives_engine.py`:
  ```python
  MAX_LIVES = 3
  REGEN_HOURS = 8

  async def can_play(user_id: str) -> bool
  async def lose_life(user_id: str) -> int
  async def check_regen(user_id: str) -> int
  ```
- [x] **5.2.2** Implement logic hồi sinh: +1 tim mỗi 8 giờ (max 3)
- [x] **5.2.3** Viết unit tests (`backend/tests/test_core/test_lives_engine.py`)

#### Task 5.3: API Endpoints

- [x] **5.3.1** Tạo file `backend/api/routes/lives.py`
- [x] **5.3.2** `GET /api/v1/lives`:
  ```json
  Response: { "current": 2, "max": 3, "next_regen_in_seconds": 14400 }
  ```
- [x] **5.3.3** `POST /api/v1/lives/lose` — Trừ 1 tim (internal, gọi khi sai)
- [x] **5.3.4** `POST /api/v1/lives/regen` — Cron job hồi sinh

#### Task 5.4: Guard Quiz Endpoint

- [x] **5.4.1** Sửa quiz route — check `can_play()` trước khi cho làm quiz (đã guard tại `sessions/{session_id}/interact` cho `submit_quiz`/`submit_answer`, trừ mode `explore`)
- [x] **5.4.2** Trả 403 + message thân thiện nếu hết tim

**📌 Tiêu chí hoàn thành:**
- ✅ User không thể làm quiz khi hết tim
- ✅ Tim hồi sinh tự động sau 8h

---

### 🔖 Mục 6: Sổ Tay Công Thức (Formula Handbook)

#### Task 6.1: Tạo Formula Database

- [x] **6.1.1** Tạo `backend/data/formula_handbook.json` (mở rộng từ `formula_lookup.json`):
  ```json
  {
    "categories": [
      {
        "id": "basic_trig",
        "name": "Đạo hàm lượng giác cơ bản",
        "formulas": [
          {
            "id": "sin_derivative",
            "latex": "(\\sin x)' = \\cos x",
            "explanation": "Đạo hàm của sin x bằng cos x",
            "example": "(\\sin 3x)' = 3\\cos 3x",
            "related_hypothesis": "H01",
            "difficulty": "easy"
          }
        ]
      }
    ]
  }
  ```
- [x] **6.1.2** Soạn 30+ formulas chia theo 5 categories (đã map 32 công thức từ `formula_lookup.json`)
- [x] **6.1.3** Validate LaTeX syntax (dùng dữ liệu chuẩn hóa từ `formula_lookup.json`)

#### Task 6.2: API Endpoint

- [x] **6.2.1** Tạo file `backend/api/routes/formulas.py`
- [x] **6.2.2** `GET /api/v1/formulas?category=basic_trig&user_id=xxx`:
  ```json
  Response: {
    "category": "basic_trig",
    "formulas": [
      {
        "id": "sin_derivative",
        "latex": "...",
        "explanation": "...",
        "mastery_status": "learned"  // "learned" | "learning" | "locked"
      }
    ]
  }
  ```
- [x] **6.2.3** Implement mastery calculation (ưu tiên `agent_state.belief_dist` theo session của user, fallback theo XP)
- [x] **6.2.4** Register route vào `main.py`

- [x] **6.2.5** Viết unit tests cho service/route (`backend/tests/test_core/test_formula_handbook_service.py`, `backend/tests/test_core/test_formulas_route.py`)

**📌 Tiêu chí hoàn thành:**
- ✅ 30+ formulas có đầy đủ LaTeX, explanation, example, mapping hypothesis
- ✅ API trả đúng data, mastery tính đúng

---

## PHASE 3 — P2: Nâng Cao (Tuần 5-6)

### 🔖 Mục 7: Onboarding Quiz & User Profile

#### Task 7.1: Thiết kế 10 câu hỏi Onboarding

- [x] **7.1.1** Soạn 10 câu hỏi chẩn đoán trình độ (`backend/data/onboarding_questions.json`):
  - Câu 1-3: Dễ (kiến thức cơ bản — đạo hàm hằng số, lũy thừa)
  - Câu 4-6: Trung bình (áp dụng quy tắc — tích, thương, lượng giác)
  - Câu 7-10: Khó (bài tổng hợp — chain rule, hàm hợp, tham số)
- [x] **7.1.2** Lưu vào file riêng `backend/data/onboarding_questions.json`
- [x] **7.1.3** Mỗi câu có đáp án + weight cho scoring

#### Task 7.2: API Endpoints

- [x] **7.2.1** `POST /api/v1/onboarding/submit`:
  ```json
  Request: {
    "answers": [
      { "question_id": "onb_1", "selected": "A", "time_taken_sec": 15 },
      ...
    ]
  }
  Response: {
    "user_level": "intermediate",
    "study_plan": {
      "daily_minutes": 15,
      "focus_areas": ["chain_rule", "trig"],
      "recommended_difficulty": 2
    }
  }
  ```
- [x] **7.2.2** `GET /api/v1/user/profile`:
  ```json
  Response: {
    "user_level": "intermediate",
    "study_goal": "exam_prep",
    "daily_minutes": 15,
    "onboarded_at": "2026-04-15T..."
  }
  ```
- [x] **7.2.3** `PUT /api/v1/user/profile` — Cập nhật goal, available_time

- [x] **7.2.4** Register routes vào `main.py` (`/api/v1/onboarding/submit`, `/api/v1/user/profile`)
- [x] **7.2.5** Viết unit tests cho onboarding/profile routes (`backend/tests/test_core/test_onboarding_route.py`, `backend/tests/test_core/test_user_profile_route.py`)

#### Task 7.3: Supabase Schema Update

- [x] **7.3.1** Thêm columns vào user profile:
  ```sql
  ALTER TABLE user_profiles ADD COLUMN
    user_level TEXT DEFAULT 'beginner',
    study_goal TEXT,
    daily_minutes INT DEFAULT 15,
    onboarded_at TIMESTAMPTZ;
  ```
- [x] **7.3.2** Cập nhật RLS policies cho các columns mới

- [x] **7.3.3** Tạo migration mới `sql/user_profiles.sql` + helper Supabase client (`get_user_profile`, `upsert_user_profile`)

**📌 Tiêu chí hoàn thành:**
- ✅ Onboarding flow end-to-end hoạt động
- ✅ Profile lưu đúng
- ✅ 10 câu hỏi chất lượng phân loại chính xác

---

### 🔖 Mục 8: Session Recovery & Auto-Save

#### Task 8.1: Session Recovery Endpoint

- [x] **8.1.1** Tạo `GET /api/v1/session/pending`:
  ```json
  Response: {
    "has_pending": true,
    "session": {
      "session_id": "...",
      "status": "active",
      "last_question_index": 5,
      "total_questions": 10,
      "progress_percent": 50,
      "last_active_at": "...",
      "abandoned_at": null
    }
  }
  ```
- [x] **8.1.2** Query Supabase: tìm session status = 'active' chưa complete (đã thêm helper `get_latest_active_learning_session` + route `backend/api/routes/session_recovery.py`)

#### Task 8.2: Auto-Save Session State

- [x] **8.2.1** Sửa `backend/core/state_manager.py`:
  - Save state mỗi 30 giây
  - Save khi user idle
  - Save khi user submit answer
- [x] **8.2.2** Đảm bảo state chứa đủ info để resume: question index, answers, beliefs, xp earned
  - Đã persist tiến độ/session snapshot vào `learning_sessions` qua helper `update_learning_session_progress`
  - Đã bổ sung migration `sql/session_recovery.sql` cho cột progress + snapshot
  - Đã cập nhật orchestrator để giữ `last_question_index`, `progress_percent`, `last_interaction_at`

**📌 Tiêu chí hoàn thành:**
- ✅ User quay lại → thấy "Bạn còn bài dở, tiếp tục nhé!"
- ✅ Resume đúng chỗ, không mất data

---

### 🔖 Mục 9: Chống Leak Nội Dung & Security

#### Task 9.1: Server-Side Answer Validation

- [x] **9.1.1** Đảm bảo `POST /api/v1/quiz/submit` KHÔNG trả `correct_answer` trong response
  - Chỉ trả: `{ "is_correct": true/false, "explanation": "..." }`
- [x] **9.1.2** Thêm sanitize layer: filter sensitive fields trước khi return
  - Đã thêm route `backend/api/routes/quiz.py` + `core/quiz_service.py` để chỉ trả payload an toàn cho frontend (không lộ `correct_option_id`/`correct_answer`)

#### Task 9.2: Shuffle Logic

- [x] **9.2.1** Khi serve quiz → shuffle thứ tự câu hỏi mỗi lần
- [x] **9.2.2** Shuffle thứ tự options (A, B, C, D) mỗi lần
- [x] **9.2.3** Mapping lại correct_option_id sau shuffle
  - Đã xử lý trong `QuizService` theo session cache + giữ mapping nội bộ server-side

#### Task 9.3: Rate Limiting

- [x] **9.3.1** Giới hạn 5 quiz sessions / ngày / user
- [x] **9.3.2** Track trong Supabase hoặc in-memory cache
- [x] **9.3.3** Trả 429 Too Many Requests khi vượt limit
  - Đã thêm helper `count_daily_learning_sessions` + guard trong `POST /api/v1/sessions`

#### Task 9.4: Request Signing (HMAC)

- [x] **9.4.1** Thêm HMAC signature cho quiz-related requests
- [x] **9.4.2** Sửa `backend/core/security.py` — thêm verify HMAC
- [x] **9.4.3** Tạo shared secret key management
  - Env mới: `QUIZ_HMAC_SECRET`, `QUIZ_SIGNATURE_TTL_SECONDS`

**📌 Tiêu chí hoàn thành:**
- ✅ Không thể extract đáp án từ API response
- ✅ Rate limit enforce đúng
- ✅ Shuffle hoạt động chính xác

---

### 🔖 Mục 10: Mode Parameter

#### Task 10.1: Thêm `mode` param

- [x] **10.1.1** Tất cả quiz/session endpoints nhận `mode: 'exam_prep' | 'explore'`
- [x] **10.1.2** Validate mode value, default = 'explore'
- [x] **10.1.3** Pass mode xuống question_selector để điều chỉnh difficulty/timer
- [x] **10.1.4** Lưu mode vào session state
  - Đã thêm `core/learning_mode.py`, cập nhật `session.py`, `orchestrator.py`, `quiz.py`, `question_selector.py`

**📌 Tiêu chí hoàn thành:**
- ✅ API xử lý đúng theo mode
- ✅ Mode persist trong session

---

## PHASE 4 — P3: Premium (Tuần 7-8, tạm hoãn)

### 🔖 Mục 11: Kahoot-Style Multiplayer Quiz

#### Task 11.1: Tạo Supabase Tables

- [ ] **11.1.1** Tạo table `quiz_rooms`:
  ```sql
  CREATE TABLE quiz_rooms (
    room_id TEXT PRIMARY KEY,
    host_user_id UUID,
    state TEXT DEFAULT 'waiting',
    current_question INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    finished_at TIMESTAMPTZ
  );
  ```
- [ ] **11.1.2** Tạo table `quiz_room_players`:
  ```sql
  CREATE TABLE quiz_room_players (
    room_id TEXT,
    user_id UUID,
    score INT DEFAULT 0,
    answers_correct INT DEFAULT 0,
    joined_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (room_id, user_id)
  );
  ```
- [ ] **11.1.3** Thêm RLS policies

#### Task 11.2: WebSocket Room Management

- [ ] **11.2.1** Tạo `backend/api/ws/multiplayer.py`:
  ```python
  class QuizRoom:
      room_id: str
      host_user_id: str
      players: list[Player]
      current_question: int
      state: RoomState  # WAITING | IN_PROGRESS | FINISHED

  async def handle_join(ws, room_id, user_id)
  async def handle_answer(ws, room_id, user_id, answer, time_ms)
  async def broadcast_results(room)
  ```
- [ ] **11.2.2** Room lifecycle: Create → Join → Start → Question loop → Results → Close
- [ ] **11.2.3** Scoring logic: đúng (100) + speed bonus (max 50)

**📌 Tiêu chí hoàn thành:**
- ✅ Room CRUD hoạt động
- ✅ WS broadcast đúng
- ✅ Scoring chính xác

---

### 🔖 Mục 12: MANIM & Error Chain

#### Task 12.1: Serve MANIM Clips

- [ ] **12.1.1** CDN/storage URL cho mỗi clip
- [ ] **12.1.2** API trả URL khi cần: `GET /api/v1/manim/{hypothesis_id}`

#### Task 12.2: Error Chain History

- [ ] **12.2.1** Tạo Supabase table `error_chain_history`:
  ```sql
  CREATE TABLE error_chain_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID,
    session_id TEXT,
    question_id TEXT,
    error_chain JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
  );
  ```
- [ ] **12.2.2** API lưu error chain khi Đức (LLM) generate

**📌 Tiêu chí hoàn thành:**
- ✅ API trả đúng clip URL
- ✅ Error history lưu đúng

---

### 🔖 Mục 13: Google Calendar — Weekly Plan

#### Task 13.1: Study Plan API

- [ ] **13.1.1** `GET /api/v1/plan/weekly`:
  ```json
  Response: {
    "week_start": "2026-04-14",
    "events": [
      {
        "title": "Ôn đạo hàm lượng giác",
        "start": "2026-04-14T18:00:00",
        "duration_minutes": 15,
        "description": "Ôn 5 công thức + làm 3 bài tập"
      }
    ]
  }
  ```
- [ ] **13.1.2** Generate plan dựa trên user_level, daily_minutes, focus areas

**📌 Tiêu chí hoàn thành:**
- ✅ API trả plan tuần đúng format
- ✅ Đủ data cho Calendar event creation

---

### 🔖 Mục 14: RAG Embedding & Question Import

#### Task 14.1: Embedding Storage

- [ ] **14.1.1** Enable pgvector extension trên Supabase
- [ ] **14.1.2** Tạo table cho embeddings:
  ```sql
  CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT,
    embedding vector(768),
    metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
  );
  ```
- [ ] **14.1.3** Tạo index HNSW cho vector search

#### Task 14.2: RAG Query API

- [ ] **14.2.1** `POST /api/v1/rag/query`:
  ```json
  Request: { "query": "chain rule là gì" }
  Response: {
    "chunks": [
      { "content": "...", "relevance_score": 0.92, "source": "..." }
    ]
  }
  ```

#### Task 14.3: Import Generated Questions

- [ ] **14.3.1** Validate câu hỏi AI-generated từ Đức
- [ ] **14.3.2** Import vào `quiz_question_template`
- [ ] **14.3.3** Quality review trước khi set `is_active: true`

**📌 Tiêu chí hoàn thành:**
- ✅ Embeddings lưu đúng
- ✅ API query hoạt động
- ✅ Câu hỏi import thành công

---

## PHASE 5 — Bonus (Tuần 9+)

### 🔖 Mục 15: Analytics

- [ ] **15.1** Tạo analytics Supabase tables (session time tracking)
- [ ] **15.2** API endpoints cho analytics data
- [ ] **15.3** Aggregate queries cho Progress page

---

## 📊 Tổng Hợp Theo Phase

| Phase | Số Tasks | Ưu tiên | Dependencies |
|-------|----------|---------|--------------|
| P0 (Tuần 1-2) | ~25 sub-tasks | 🔴 Cao nhất | Không có — bắt đầu ngay |
| P1 (Tuần 3-4) | ~30 sub-tasks | 🟠 Cao | P0 hoàn thành |
| P2 (Tuần 5-6) | ~25 sub-tasks | 🟡 Trung bình | P0 + P1 cơ bản |
| P3 (Tuần 7-8) | ~20 sub-tasks | ⏸️ Tạm hoãn | Mở lại khi team chốt scope premium |
| Bonus (Tuần 9+) | ~5 sub-tasks | ⚪ Optional | Khi có thời gian |

---

## 🔗 Dependencies Với Team Members

| Hưng cần từ | Nội dung | Khi nào |
|-------------|----------|---------|
| **Khang** | Confirm 4 hypotheses IDs (H01-H04) đã finalize | Trước khi soạn câu hỏi |
| **Khang** | Confirm interventionPlan IDs cho diagnosis | Tuần 1 |
| **Đức** | Template responses format cho intent classifier | Tuần 2 |
| **Đức** | AI-generated questions để import | Tuần 7-8 |
| **Huy** | API contract review (request/response schemas) | Mỗi khi tạo endpoint mới |

| Team cần từ Hưng | Nội dung | Khi nào |
|-------------------|----------|---------|
| **Huy** | API endpoints + response schemas | ASAP, trước khi Huy code |
| **Huy** | Quiz data trong Supabase | Tuần 1 |
| **Khang** | Diagnosis scenarios data | Tuần 1 |
| **Đức** | Formula lookup data | Tuần 2 |
