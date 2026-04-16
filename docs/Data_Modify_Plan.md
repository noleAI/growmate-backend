# 🔍 Data_Modify_Plan — Rà Soát & Chỉnh Sửa Sau P2

> Ngày rà soát: 16/04/2026  
> Phạm vi: Tất cả hạng mục P0 → P2 trong `Data_Plan.md` + `HANDOFF_FRONTEND.md`  
> Phương pháp: Cross-check từng task trong plan vs. code thực tế + phân tích sai lệch giữa HANDOFF và implementation  

---

## Mục Lục

1. [Tổng Kết Rà Soát Data_Plan.md](#1-tổng-kết-rà-soát-data_planmd)
2. [Vấn Đề Phát Hiện Trong Code](#2-vấn-đề-phát-hiện-trong-code)
3. [Sai Lệch HANDOFF_FRONTEND.md vs. Code Thực Tế](#3-sai-lệch-handoff_frontendmd-vs-code-thực-tế)
4. [Danh Sách Hành Động Cần Làm](#4-danh-sách-hành-động-cần-làm)
5. [Các Hạng Mục ĐÃ ĐẠT — Không Cần Sửa](#5-các-hạng-mục-đã-đạt--không-cần-sửa)

---

## 1. Tổng Kết Rà Soát Data_Plan.md

### Kết quả tổng quan

| Phase | Tổng task (checkbox) | Đã hoàn thành ✅ | Chưa hoàn thành ☐ | Ghi chú |
|-------|---------------------|-------------------|--------------------|---------|
| P0 (Mục 1-3) | ~25 | 23 | 2 | 2 task import Supabase bị block bởi env |
| P1 (Mục 4-6) | ~30 | 29 | 1 | 1 task cron job chưa schedule production |
| P2 (Mục 7-10) | ~25 | 25 | 0 | Hoàn thành code |

### Các task chưa hoàn thành (cần action)

| Task ID | Mô tả | Lý do | Mức độ |
|---------|--------|-------|--------|
| **1.2.3** | Chạy import 73 câu hỏi lên Supabase | Thiếu env `SUPABASE_URL`/`SUPABASE_KEY` trên máy local | 🔴 **Blocker** — Dữ liệu quiz chưa có trên production |
| **1.2.4** | Verify dữ liệu trên Supabase Dashboard | Phụ thuộc 1.2.3 | 🔴 **Blocker** |
| **4.1.5** | Schedule cron reset `weekly_xp = 0` trên Supabase | Hàm SQL `reset_weekly_xp()` đã viết nhưng chưa schedule `pg_cron` | 🟠 **Quan trọng** — XP tuần sẽ không reset tự động |

---

## 2. Vấn Đề Phát Hiện Trong Code

### 🔴 C-01: `hypothesis_tag` field không tồn tại trong NDJSON (0/73 records)

**Vị trí**: `backend/data/quiz_question_template_normalized.ndjson`  
**Data_Plan task**: 1.1.9 đánh dấu `[x]` — ghi "đã tự động gán qua script normalize khi thiếu"  
**Thực tế**: Chạy phân tích file hiện tại:
```
Has hypothesis_tag: 0/73
```

**Nhưng đây KHÔNG phải vấn đề nghiêm trọng** vì:
- Code `quiz_service.py` không sử dụng field `hypothesis_tag` — nó dùng `metadata.tags` để lọc
- Code `question_selector.py` sử dụng `metadata.tags` 
- `formula_handbook_service.py` dùng `related_hypothesis` từ `formula_lookup.json`

**Đánh giá**: ⚠️ **Nhẹ** — field không gây lỗi runtime, nhưng Data_Plan ghi nhận sai trạng thái. Nên cập nhật plan cho chính xác hoặc thêm field vào NDJSON cho consistency.

---

### 🟠 C-02: Leaderboard `display_name` luôn trả `null`

**Vị trí**: `backend/api/routes/leaderboard.py` line 83, line 179  
**Code**:
```python
"display_name": None,  # Hardcoded None
```

**Nguyên nhân**: Route `leaderboard.py` không join/lookup `user_profiles.display_name` — chỉ đọc từ `user_xp` table (không chứa `display_name`).

**Ảnh hưởng**: Frontend hiển thị leaderboard mà tên user luôn là `null`. Đây là trải nghiệm UX kém.

**Đề xuất sửa**: Sau khi lấy xp rows, lookup `user_profiles` để lấy `display_name` + `avatar_url` cho mỗi user.

---

### 🟠 C-03: Leaderboard `/me` có field trùng: `badge_count` và `badges_count`

**Vị trí**: `backend/api/routes/leaderboard.py` line 184-185  
**Code**:
```python
"badge_count": len(badges),
"badges_count": len(badges),   # Duplicate field
```

**Ảnh hưởng**: Frontend không biết nên dùng field nào.

**Đề xuất sửa**: Chỉ giữ 1 field (`badge_count`), bỏ `badges_count`.

---

### 🟠 C-04: Badges API thiếu `description` và `icon`

**Vị trí**: `backend/api/routes/leaderboard.py` line 313-314  
**Code**:
```python
"description": None,
"icon": None,
```

**Nguyên nhân**: Table `user_badges` không có cột `description`/`icon`. Các giá trị này cần lookup từ badge catalog (hiện không tồn tại).

**Ảnh hưởng**: Frontend nhận badge mà không biết mô tả hay icon hiển thị.

**Đề xuất sửa**: Tạo static badge catalog (`BADGE_CATALOG` dict trong code hoặc file JSON) chứa `description` + `icon`/`emoji` cho mỗi `badge_type`, rồi merge vào response.

---

### 🟠 C-05: Badges API `available` luôn trả `[]`

**Vị trí**: `backend/api/routes/leaderboard.py` line 323  
**Code**:
```python
"available": [],
```

**Nguyên nhân**: Không có logic để liệt kê badges chưa đạt + progress.

**Ảnh hưởng**: Frontend không thể hiển thị "các badge sắp đạt" (motivation feature).

**Đề xuất sửa**: Tạo logic `get_available_badges()` đối chiếu earned vs. catalog, tính progress cho mỗi badge.

---

### ⚠️ C-06: `GET /onboarding/questions` endpoint không tồn tại

**Vị trí**: `backend/api/routes/onboarding.py`  
**HANDOFF_FRONTEND.md gốc (version cũ)** từng mô tả endpoint `GET /api/v1/onboarding/questions`.
**HANDOFF_FRONTEND.md hiện tại (version P2)** đã loại bỏ endpoint này.

**Thực tế code**: Chỉ có `POST /onboarding/submit`. Không có `GET /onboarding/questions`.

**Ảnh hưởng**: Frontend không có API để lấy danh sách câu hỏi onboarding. Hiện tại chỉ có file JSON local `backend/data/onboarding_questions.json`, frontend không thể truy cập.

**Đề xuất**: 
- Nếu Flutter hardcode 10 câu → không cần endpoint (nhưng sẽ khó maintain khi đổi câu)
- Nếu muốn dynamic → cần thêm `GET /onboarding/questions` endpoint
- **Ít nhất cần ghi rõ trong HANDOFF** cho Huy biết flow sử dụng onboarding

---

### ⚠️ C-07: `user_profile` response thiếu `email` field

**Vị trí**: `backend/api/routes/user_profile.py` function `_serialize_profile()`  
**HANDOFF cũ (version gốc)** ghi response có `email`. 
**HANDOFF hiện tại (P2)** đã không ghi `email` trong response.

**Thực tế code**: `_serialize_profile()` không trả `email`. Table `user_profiles` cũng không có cột `email` (email nằm ở `auth.users`).

**Đánh giá**: ✅ HANDOFF P2 đã đúng — không có `email`. Không cần sửa.

---

### ⚠️ C-08: `quiz_service.py` dùng NDJSON file trực tiếp, không dùng Supabase

**Vị trí**: `backend/core/quiz_service.py` line 14-16  
**Code**:
```python
self.dataset_path = dataset_path or (
    base_dir / "data" / "quiz_question_template_normalized.ndjson"
)
```

**Nguyên nhân**: Quiz service đọc file NDJSON local thay vì query từ Supabase.

**Ảnh hưởng hiện tại**: Không ảnh hưởng — dữ liệu cùng source. Nhưng nếu admin cập nhật câu hỏi trên Supabase Dashboard, quiz service sẽ không nhận thay đổi cho đến khi restart server.

**Đánh giá**: Đây là design decision có chủ đích (fast-path, không phụ thuộc network lúc serve quiz). Ghi nhận vào HANDOFF để Huy biết.

---

### ⚠️ C-09: `lives/regen` endpoint tồn tại nhưng HANDOFF không document vùng `POST /lives/regen`

**Vị trí**: `backend/api/routes/lives.py` line 62-77  
**Code**: Có endpoint `POST /lives/regen` (cho admin/debug hoặc khi user xem lại bài sai để nhận +1 tim).
**HANDOFF_FRONTEND.md P2 Section 6.3**: Chỉ ghi tiêu đề `POST /lives/regen` nhưng **không có request/response example**.

**Đề xuất**: Bổ sung response example cho `POST /lives/regen`.

---

### ⚠️ C-10: Learning mode mapping: `"normal"` → `"explore"`

**Vị trí**: `backend/core/learning_mode.py` line 19-20  
**Code**:
```python
if normalized == "normal":
    return "explore"
```

**HANDOFF_FRONTEND.md hiện tại nói**: `mode` hợp lệ: `exam_prep`, `explore`. Nếu bỏ trống → mặc định `explore`.

**Ảnh hưởng**: Nếu frontend cũ gửi `mode: "normal"`, backend vẫn chấp nhận (map sang `explore`). Đây là backward-compat.

**Đánh giá**: ✅ OK — HANDOFF đã đúng, chỉ document `exam_prep` và `explore`. Backward-compat cho `normal` không cần expose.

---

## 3. Sai Lệch HANDOFF_FRONTEND.md vs. Code Thực Tế

### 3.1 Sai lệch cần sửa trong HANDOFF

| # | Section | Sai lệch | Chi tiết |
|---|---------|----------|----------|
| **H-01** | 5.3 (`POST /xp/add`) | Request example thiếu `mastery_topics` | Code thực tế hỗ trợ `extra_data.mastery_topics` (dict) để kích hoạt mastery badge. HANDOFF không nói gì. |
| **H-02** | 5.4 (`GET /badges`) | Response `description` và `icon` luôn `null` | HANDOFF ghi đúng `null` nhưng không giải thích tại sao. Frontend cần biết rằng hiện tại chưa có badge catalog, nên cần hardcode icon/description ở client. |
| **H-03** | 6.3 (`POST /lives/regen`) | Thiếu response example | Chỉ có tiêu đề, Frontend không biết response format. |
| **H-04** | 8.1 (`POST /onboarding/submit`) | Thiếu `GET /onboarding/questions` endpoint | Frontend không biết lấy câu hỏi onboarding từ đâu. Cần clarify: hardcode hay API? |
| **H-05** | 4.2 (`POST /quiz/submit`) | Thiếu field `answer` cho SHORT_ANSWER và `answers` cho TRUE_FALSE_CLUSTER | HANDOFF chỉ show `selected_option` cho MCQ. Nhưng `QuizSubmitRequest` accept 3 loại input: `selected_option`, `answer`, `answers`. |
| **H-06** | 5.2 (`GET /leaderboard/me`) | Response có cả `badge_count` và `badges_count` | HANDOFF chỉ ghi `badge_count` + `badges_count`. Cần clarify dùng field nào. |
| **H-07** | 7.1 (`GET /formulas`) | Response format khi `category != all` khác document | HANDOFF show `categories: [...]`. Code thực tế trả `{ "category": "...", "formulas": [...], "categories": [...] }` — có thêm field `formulas` flatten. |

### 3.2 Sai lệch KHÔNG cần sửa (HANDOFF P2 đã chính xác)

| Section | Nội dung | Xác nhận |
|---------|----------|----------|
| Session APIs (2.x) | Request/response format | ✅ Khớp code |
| Quota API (3.x) | Response format | ✅ Khớp code |
| Quiz next question (4.1) | Response format | ✅ Khớp code |
| Lives GET (6.1) | Response format | ✅ Khớp code |
| User Profile (8.2) | GET/PUT format | ✅ Khớp code |
| Session Recovery (2.4) | Response format | ✅ Khớp code |
| HMAC Signature (4.3) | Headers + payload format | ✅ Khớp code |
| Error Handling (9) | HTTP status codes | ✅ Khớp code |

---

## 4. Danh Sách Hành Động Cần Làm

### 🔴 Ưu tiên cao (Blockers)

- [ ] **A-01**: Import 73 câu hỏi lên Supabase production (`task 1.2.3`, `1.2.4`)
  - Setup env `SUPABASE_URL`, `SUPABASE_KEY`
  - Chạy `python backend/scripts/import_quiz_questions.py --dry-run` rồi `--chunk-size 50`
  - Verify trên Dashboard: `select count(*) from quiz_question_template;` → expect 73

- [ ] **A-02**: Schedule `pg_cron` cho `reset_weekly_xp()` trên Supabase (`task 4.1.5`)
  - Chạy trên Supabase SQL Editor:
  ```sql
  select cron.schedule(
    'growmate-reset-weekly-xp',
    '0 0 * * 1',  -- Thứ 2 00:00 UTC
    $$select public.reset_weekly_xp();$$
  );
  ```

### 🟠 Ưu tiên trung bình (Nên sửa trước khi giao Frontend)

- [ ] **A-03**: Fix `display_name` trong Leaderboard response (`C-02`)
  - Trong `leaderboard.py`, sau khi lấy `user_xp` rows, batch-lookup `user_profiles` để lấy `display_name` + `avatar_url`
  - Hoặc tạo DB view join `user_xp` + `user_profiles`

- [ ] **A-04**: Bỏ field trùng `badges_count` trong `GET /leaderboard/me` (`C-03`)
  - Xóa dòng `"badges_count": len(badges)` trong `leaderboard.py`

- [ ] **A-05**: Tạo badge catalog cho `description`/`icon` (`C-04`)
  - Tạo dict `BADGE_CATALOG` hoặc file `backend/data/badge_catalog.json`:
  ```json
  {
    "streak_7": { "name": "Kiên trì", "description": "Học 7 ngày liên tiếp", "icon": "🔥" },
    "top_10_weekly": { "name": "Siêu sao tuần", "description": "Lọt Top 10 tuần", "icon": "⭐" }
  }
  ```
  - Merge vào response trong `GET /badges` và `POST /xp/add` (new_badges)

- [ ] **A-06**: Cập nhật HANDOFF section `POST /quiz/submit` cho 3 loại câu hỏi (`H-05`)
  - Thêm ví dụ request cho `SHORT_ANSWER` (field `answer`) và `TRUE_FALSE_CLUSTER` (field `answers`)

- [ ] **A-07**: Cập nhật HANDOFF section `POST /lives/regen` response example (`H-03`)
  - Response format giống `GET /lives`:
  ```json
  {
    "current": 2,
    "max": 3,
    "can_play": true,
    "next_regen_in_seconds": 14400,
    "next_regen_at": "2026-04-16T18:00:00+00:00"
  }
  ```

- [ ] **A-08**: Clarify onboarding questions flow trong HANDOFF (`H-04`)
  - Hai option:
    1. **Frontend hardcode 10 câu** (từ file JSON) — đơn giản, phù hợp MVP
    2. **Tạo `GET /onboarding/questions`** endpoint — linh hoạt hơn
  - Cần team quyết định approach, rồi update HANDOFF

### ⚠️ Ưu tiên thấp (Nice to have)

- [ ] **A-09**: Thêm `hypothesis_tag` vào 73 records NDJSON cho consistency (`C-01`)
  - Hoặc cập nhật Data_Plan.md task 1.1.9 thành `[ ]` cho chính xác

- [ ] **A-10**: Implement `available` badges list trong `GET /badges` (`C-05`)
  - Liệt kê badges chưa đạt + progress bar data
  - Cần badge catalog (A-05) trước

- [ ] **A-11**: Cập nhật HANDOFF thêm note về `mastery_topics` trong `POST /xp/add` (`H-01`)
  - Ghi rõ: để kích hoạt mastery badge, frontend gửi:
  ```json
  {
    "event_type": "correct_answer",
    "extra_data": {
      "mastery_topics": { "chain_rule": 100.0 }
    }
  }
  ```

- [ ] **A-12**: Cập nhật HANDOFF section `GET /formulas?category=basic_trig` response (`H-07`)
  - Ghi chú thêm: khi `category != all`, response có thêm field `formulas` (flatten) bên cạnh `categories`

---

## 5. Các Hạng Mục ĐÃ ĐẠT — Không Cần Sửa

### Data / Quiz Questions ✅
- [x] 73 câu hỏi trong NDJSON, đủ fields bắt buộc
- [x] `grade_level: "11"` đã có 73/73 records
- [x] Phân bố difficulty hợp lý: Easy=18, Medium=30, Hard=25
- [x] Phân bố types: MCQ=42, SA=19, TFC=12
- [x] Hypothesis coverage ≥ 10 câu/hypothesis (H01=10, H02=10, H03=10, H04=43)
- [x] Diagnosis scenarios cập nhật đúng 4 hypotheses

### SQL Migrations ✅  
- [x] `sql/quiz_question_template_TableSchema.sql` — schema + indexes + trigger
- [x] `sql/user_token_usage.sql` — table + trigger + RLS
- [x] `sql/user_xp.sql` — table + trigger + indexes + RLS + reset function
- [x] `sql/user_badges.sql` — table + unique index + RLS
- [x] `sql/user_lives.sql` — table + trigger + RLS
- [x] `sql/user_profiles.sql` — table + constraints + trigger + RLS
- [x] `sql/session_recovery.sql` — ALTER columns + constraints + index

### API Routes ✅
- [x] `quota.py` — GET /quota (daily token quota)
- [x] `leaderboard.py` — GET /leaderboard, /leaderboard/me, POST /xp/add, GET /badges
- [x] `lives.py` — GET /lives, POST /lives/lose, POST /lives/regen
- [x] `formulas.py` — GET /formulas (w/ category, search, mastery)
- [x] `onboarding.py` — POST /onboarding/submit
- [x] `user_profile.py` — GET /user/profile, PUT /user/profile
- [x] `session_recovery.py` — GET /session/pending
- [x] `quiz.py` — GET /quiz/next, POST /quiz/submit (w/ HMAC, lives, rate limit)
- [x] Tất cả routes registered trong `main.py`

### Core Engines ✅
- [x] `xp_engine.py` — XP calc + streak + badge candidates
- [x] `lives_engine.py` — 3 lives + 8h regen + can_play check
- [x] `quiz_service.py` — NDJSON loader + shuffle + submit + sanitize (no answer leak)
- [x] `formula_handbook_service.py` — Catalog + mastery lookup + search
- [x] `onboarding_service.py` — Evaluate + classify + study plan
- [x] `security.py` — JWT + HMAC signature verify
- [x] `learning_mode.py` — exam_prep / explore normalize
- [x] `state_manager.py` — Auto-save 30s + idle detection + session progress sync

### Data Files ✅
- [x] `formula_lookup.json` — 32 formulas (all categories covered)
- [x] `formula_handbook.json` — 5 category mappings
- [x] `onboarding_questions.json` — 10 questions (3 easy, 3 medium, 4 hard), 4 hypotheses
- [x] `derivative_priors.json` — Bayesian hypotheses config

### Unit Tests ✅
- [x] `test_quota_route.py`
- [x] `test_xp_engine.py`
- [x] `test_leaderboard_route.py`
- [x] `test_lives_engine.py`
- [x] `test_lives_route.py`
- [x] `test_formula_handbook_service.py`
- [x] `test_formulas_route.py`
- [x] `test_onboarding_service.py`
- [x] `test_onboarding_route.py`
- [x] `test_user_profile_route.py`
- [x] `test_quiz_route.py`
- [x] `test_security_signature.py`
- [x] `test_session_mode_rate_limit.py`
- [x] `test_session_recovery_route.py`
- [x] `test_user_classifier.py`

### Supporting Docs ✅
- [x] `IMPORT_DATA.md` — Hướng dẫn import đầy đủ (script + CSV fallback)
- [x] `SUPABASE_MIGRATION_AND_ENDPOINT_VERIFY.md` — Verify checklist

---

## Tóm tắt nhanh

| Metric | Con số |
|--------|--------|
| Tổng vấn đề phát hiện (code) | 10 (C-01 → C-10) |
| Sai lệch HANDOFF vs code | 7 (H-01 → H-07) |
| **Hành động cần làm** | **12** (A-01 → A-12) |
| Trong đó 🔴 Blocker | 2 (A-01, A-02) |
| Trong đó 🟠 Nên sửa | 6 (A-03 → A-08) |
| Trong đó ⚠️ Nice to have | 4 (A-09 → A-12) |
| Hạng mục đạt chuẩn | Đại đa số P0-P2 |
