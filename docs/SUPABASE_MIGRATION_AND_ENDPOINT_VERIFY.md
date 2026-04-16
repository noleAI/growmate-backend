# Hướng Dẫn Chạy Migration SQL Trên Supabase Và Verify Nhanh Endpoint

Cập nhật: 2026-04-16  
Phạm vi: Migration và smoke test cho P0/P1/P2.  
Lưu ý: P3 (premium) đã được team quyết định tạm hoãn, chưa triển khai trong đợt này.

---

## 1) Chuẩn Bị Trước Khi Migrate

Cần có:
- Quyền truy cập Supabase Project (Dashboard + SQL Editor)
- JWT hợp lệ để test endpoint (Bearer token)
- URL backend của môi trường thật (staging/prod)

Biến môi trường gợi ý:

```powershell
$env:BASE_URL = "https://<YOUR_DOMAIN>/api/v1"
$env:TOKEN = "<SUPABASE_JWT_TOKEN>"
```

---

## 2) Thứ Tự Migration Để Tránh Lỗi Dependency

Chạy trong Supabase SQL Editor theo đúng thứ tự:

1. `sql/user_token_usage.sql`
2. `sql/user_xp.sql`
3. `sql/user_badges.sql`
4. `sql/user_lives.sql`
5. `sql/user_profiles.sql`
6. `sql/session_recovery.sql`

Ghi chú:
- Các file dùng `create table if not exists` và `drop policy if exists`, có thể chạy lại an toàn.
- Sau khi chạy xong, lưu execution logs để truy vết.

---

## 3) Kiểm Tra Schema Sau Migration

Chạy query nhanh trong SQL Editor:

```sql
select to_regclass('public.user_token_usage') as user_token_usage,
       to_regclass('public.user_xp') as user_xp,
       to_regclass('public.user_badges') as user_badges,
       to_regclass('public.user_lives') as user_lives,
       to_regclass('public.user_profiles') as user_profiles;
```

Kỳ vọng: 5 cột đều trả về tên table, không phải `null`.

Kiểm tra cột session recovery trong `learning_sessions`:

```sql
select column_name
from information_schema.columns
where table_schema = 'public'
  and table_name = 'learning_sessions'
  and column_name in (
    'last_question_index',
    'total_questions',
    'progress_percent',
    'last_interaction_at',
    'state_snapshot',
    'updated_at'
  )
order by column_name;
```

Kỳ vọng: trả về đủ 6 cột.

Kiểm tra RLS:

```sql
select schemaname, tablename, rowsecurity
from pg_tables
where schemaname = 'public'
  and tablename in (
    'user_token_usage',
    'user_xp',
    'user_badges',
    'user_lives',
    'user_profiles'
  )
order by tablename;
```

Kỳ vọng: `rowsecurity = true` cho tất cả bảng.

---

## 4) Cấu Hình Weekly Reset Cho XP (Production)

File `sql/user_xp.sql` đã tạo function:
- `public.reset_weekly_xp()`

Nếu đã bật `pg_cron`, cấu hình lịch:

```sql
select cron.schedule(
  'growmate-reset-weekly-xp',
  '0 0 * * 1',
  $$select public.reset_weekly_xp();$$
);
```

Kiểm tra job:

```sql
select jobid, jobname, schedule, active
from cron.job
where jobname = 'growmate-reset-weekly-xp';
```

Nếu chưa dùng `pg_cron`, cần có external scheduler gọi function vào thứ 2, 00:00.

---

## 5) Smoke Test Endpoint Trên Môi Trường Thật

Thay `BASE_URL` và `TOKEN` bằng giá trị thật.

### 5.1 Quota

```powershell
curl.exe -s -X GET "$env:BASE_URL/quota" `
  -H "Authorization: Bearer $env:TOKEN"
```

Kỳ vọng:
- Có `used`, `limit`, `remaining`, `reset_at`

### 5.2 Leaderboard

```powershell
curl.exe -s -X GET "$env:BASE_URL/leaderboard?period=weekly&limit=20" `
  -H "Authorization: Bearer $env:TOKEN"
```

Kỳ vọng:
- Có `period`, `total_players`, `leaderboard[]`

### 5.3 My Rank

```powershell
curl.exe -s -X GET "$env:BASE_URL/leaderboard/me?period=weekly" `
  -H "Authorization: Bearer $env:TOKEN"
```

Kỳ vọng:
- Có `rank`, `weekly_xp`, `total_xp`, `current_streak`

### 5.4 Add XP

```powershell
curl.exe -s -X POST "$env:BASE_URL/xp/add" `
  -H "Authorization: Bearer $env:TOKEN" `
  -H "Content-Type: application/json" `
  -d '{"event_type":"correct_answer","extra_data":{"time_taken_sec":8,"consecutive_correct":2}}'
```

Kỳ vọng:
- Có `xp_added`, `weekly_xp`, `total_xp`, `new_badges`

### 5.5 Badges

```powershell
curl.exe -s -X GET "$env:BASE_URL/badges" `
  -H "Authorization: Bearer $env:TOKEN"
```

Kỳ vọng:
- Có danh sách badge (`badges` hoặc `earned`)

### 5.6 Lives - Read

```powershell
curl.exe -s -X GET "$env:BASE_URL/lives" `
  -H "Authorization: Bearer $env:TOKEN"
```

Kỳ vọng:
- Có `current`, `max`, `can_play`, `next_regen_in_seconds`

### 5.7 Lives - Lose

```powershell
curl.exe -s -X POST "$env:BASE_URL/lives/lose" `
  -H "Authorization: Bearer $env:TOKEN"
```

Kỳ vọng:
- `remaining` giảm 1 (nếu trước đó > 0)
- Khi `remaining = 0`, `can_play = false`

### 5.8 Lives - Regen

```powershell
curl.exe -s -X POST "$env:BASE_URL/lives/regen" `
  -H "Authorization: Bearer $env:TOKEN"
```

Kỳ vọng:
- `current` tăng +1, tối đa 3

### 5.9 Onboarding Submit

```powershell
curl.exe -s -X POST "$env:BASE_URL/onboarding/submit" `
  -H "Authorization: Bearer $env:TOKEN" `
  -H "Content-Type: application/json" `
  -d '{"answers":[{"question_id":"onb_01","selected":"A","time_taken_sec":5}],"study_goal":"exam_prep","daily_minutes":20}'
```

Kỳ vọng:
- Có `user_level`, `accuracy_percent`, `study_plan`, `onboarding_summary`

### 5.10 User Profile - Read

```powershell
curl.exe -s -X GET "$env:BASE_URL/user/profile" `
  -H "Authorization: Bearer $env:TOKEN"
```

Kỳ vọng:
- Có `user_level`, `study_goal`, `daily_minutes`, `onboarded_at`

### 5.11 User Profile - Update

```powershell
curl.exe -s -X PUT "$env:BASE_URL/user/profile" `
  -H "Authorization: Bearer $env:TOKEN" `
  -H "Content-Type: application/json" `
  -d '{"study_goal":"explore","daily_minutes":25}'
```

Kỳ vọng:
- Có `status = "updated"`
- Giá trị profile được cập nhật đúng theo request

### 5.12 Session Pending

```powershell
curl.exe -s -X GET "$env:BASE_URL/session/pending" `
  -H "Authorization: Bearer $env:TOKEN"
```

Kỳ vọng:
- Có `has_pending`
- Nếu `has_pending = true`, payload có `session.session_id`, `last_question_index`, `progress_percent`

### 5.13 Quiz Next

```powershell
curl.exe -s -X GET "$env:BASE_URL/quiz/next?session_id=<SESSION_ID>&index=0&total_questions=10&mode=explore" `
  -H "Authorization: Bearer $env:TOKEN"
```

Kỳ vọng:
- Có `next_question`
- Không có `correct_option_id` trong response
- `mode` phản hồi đúng `explore` hoặc `exam_prep`

### 5.14 Quiz Submit

```powershell
curl.exe -s -X POST "$env:BASE_URL/quiz/submit" `
  -H "Authorization: Bearer $env:TOKEN" `
  -H "Content-Type: application/json" `
  -d '{"session_id":"<SESSION_ID>","question_id":"MATH_DERIV_1","selected_option":"A","mode":"exam_prep"}'
```

Kỳ vọng:
- Có `is_correct`, `explanation`
- Không có `correct_answer` hoặc `correct_option_id`

### 5.15 HMAC Verify Cho Quiz Requests

Khi đã bật `QUIZ_HMAC_SECRET`, kỳ vọng:
- Thiếu signature headers -> `401 missing_signature_headers`
- Signature sai -> `401 invalid_signature`
- Timestamp quá hạn -> `401 signature_expired`

---

## 6) Verify Guard Khi Hết Tim

Mục tiêu: endpoint session interact trả 403 nếu user hết tim và action là quiz submit.

```powershell
$sessionId = "<SESSION_ID>"
curl.exe -s -X POST "$env:BASE_URL/sessions/$sessionId/interact" `
  -H "Authorization: Bearer $env:TOKEN" `
  -H "Content-Type: application/json" `
  -d '{"action_type":"submit_answer","response_data":{"answer":"A"}}'
```

Kỳ vọng:
- HTTP 403
- Body có `detail = "no_lives_remaining"`
- Có `next_regen_in_seconds` để frontend hiển thị countdown

---

## 7) Checklist Sign-off Trước Khi Handoff Frontend

- [ ] Đã apply đủ 6 migration SQL trên đúng project
- [ ] Đã verify tồn tại table + RLS
- [ ] Đã test đủ các endpoint smoke test ở mục 5
- [ ] Đã test 403 `no_lives_remaining` cho quiz submit
- [ ] Đã cấu hình lịch weekly reset cho XP trên production

Nếu tất cả đã check, frontend có thể tích hợp trực tiếp theo `docs/HANDOFF_FRONTEND.md`.
