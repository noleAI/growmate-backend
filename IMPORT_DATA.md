# IMPORT DATA LÊN SUPABASE

## 1) Tổng quan nhanh

Trong repo hiện tại có 2 nhóm chính:

1. Migration SQL để tạo hoặc cập nhật bảng trên Supabase.
2. Data file cần nạp vào DB (nếu muốn quản trị tập trung trên Supabase).

Ngoài ra có một số file JSON chỉ dùng local trong backend, không cần import vào Supabase.

---

## 2) Các file SQL cần chạy trên Supabase

Chạy trong SQL Editor theo thứ tự sau:

1. sql/user_token_usage.sql
2. sql/user_xp.sql
3. sql/user_badges.sql
4. sql/user_lives.sql
5. sql/user_profiles.sql
6. sql/session_recovery.sql

Nếu bảng câu hỏi chưa tồn tại thì chạy thêm:

7. sql/quiz_question_template_TableSchema.sql

Ghi chú:
- Nếu project đã có schema đầy đủ từ sql/DatabaseSchema.sql thì chỉ cần chạy các file migration mới (1-6).
- Các file migration đã viết theo hướng chạy lại an toàn tương đối (create if not exists, drop policy if exists).

---

## 3) File data cần import lên Supabase

### Bắt buộc nếu bạn muốn có dữ liệu câu hỏi trong bảng quiz_question_template

- backend/data/quiz_question_template_normalized.ndjson

Bảng đích:
- public.quiz_question_template

---

## 4) File data KHÔNG cần import Supabase (backend đọc local)

Các file dưới đây đang được code đọc trực tiếp từ filesystem:

- backend/data/formula_lookup.json
- backend/data/formula_handbook.json
- backend/data/onboarding_questions.json
- backend/data/diagnosis/diagnosis_scenarios.json
- backend/data/interventions/intervention_catalog.json
- backend/data/derivative_priors.json
- backend/configs/runtime/runtime_decision_config.json

Nghĩa là: bạn deploy backend kèm các file này là chạy được, không cần nạp vào table Supabase.

---

## 5) Cách khuyến nghị: import NDJSON trực tiếp bằng script (không cần CSV)

Repo đã có sẵn script:
- backend/scripts/import_quiz_questions.py

### 5.1 Chuẩn bị

Tạo file backend/.env với ít nhất:

SUPABASE_URL=...
SUPABASE_KEY=...

### 5.2 Chạy thử validate

Từ thư mục gốc repo:

python backend/scripts/import_quiz_questions.py --dry-run

### 5.3 Import thật

python backend/scripts/import_quiz_questions.py --chunk-size 50

Ưu điểm của cách này:
- Không cần convert CSV.
- Có validate schema trước khi ghi.
- Dùng deterministic id để upsert, tránh trùng khi chạy lại.

---

## 6) Nếu bạn chỉ import được CSV trên Supabase Dashboard

Bạn có thể convert NDJSON sang CSV rồi import thủ công.

### 6.1 Convert NDJSON -> CSV

Chạy PowerShell tại thư mục gốc repo:

$input = "backend/data/quiz_question_template_normalized.ndjson"
$output = "backend/data/quiz_question_template_import.csv"

$rows = Get-Content $input | Where-Object { $_.Trim() -ne "" } | ForEach-Object {
  $obj = $_ | ConvertFrom-Json
  [PSCustomObject]@{
    subject = $obj.subject
    topic_code = $obj.topic_code
    topic_name = $obj.topic_name
    exam_year = $obj.exam_year
    question_type = $obj.question_type
    part_no = $obj.part_no
    difficulty_level = $obj.difficulty_level
    content = $obj.content
    media_url = $obj.media_url
    payload = ($obj.payload | ConvertTo-Json -Compress -Depth 20)
    metadata = ($obj.metadata | ConvertTo-Json -Compress -Depth 20)
    is_active = $obj.is_active
    grade_level = $obj.grade_level
  }
}

$rows | Export-Csv -Path $output -NoTypeInformation -Encoding UTF8
Write-Host "Done: $output"

### 6.2 Import CSV trên Dashboard

1. Vào table public.quiz_question_template.
2. Chọn Import data từ CSV.
3. Chọn file backend/data/quiz_question_template_import.csv.
4. Map đúng các cột, đặc biệt:
   - payload -> jsonb
   - metadata -> jsonb
5. Import.

### 6.3 Verify sau import

Chạy SQL kiểm tra:

select count(*) as total_rows from public.quiz_question_template;

select
  count(*) filter (where payload is null) as payload_null,
  count(*) filter (where metadata is null) as metadata_null
from public.quiz_question_template;

---

## 7) Lưu ý quan trọng khi dùng cách CSV

- Import CSV qua Dashboard thường là insert mới, không phải upsert theo source_question_id.
- Nếu import lặp lại nhiều lần có thể phát sinh bản ghi trùng logic.
- Nếu bạn cần cập nhật nhiều lần theo kiểu đồng bộ, nên dùng script Python ở mục 5.
