# Plan Chi Tiết Phân Công Nhiệm Vụ Nhóm

> Dựa trên 12 góp ý Mentor — Ngày 15/04/2026
> Thành viên: **Huy** (Frontend) · **Hưng** (Data) · **Đức** (LLM) · **Khang** (Agent)

---

## Tổng Quan Phân Công Theo Vai Trò

| Thành viên | Vai trò chính | Phạm vi phụ trách |
|------------|--------------|-------------------|
| **Huy** | Frontend (UI/UX + Logic) | Flutter screens, animations, theme, BLoC/Cubit, repositories, API integration, state management, LaTeX rendering, STT |
| **Hưng** | Data Engineering | Supabase schemas/tables, data files (JSON/CSV), soạn câu hỏi, data import/export, API endpoints CRUD, database administration |
| **Đức** | LLM & NLP | LLM service, system prompts, policy/guardrails, intent classifier, template responses, token management, RAG chunking/embedding, MANIM, question generation AI |
| **Khang** | Agent & Orchestration | Bayesian tracker, HTN planner, Empathy agent (Particle Filter), Strategy agent (Q-Learning), Orchestrator engine, reward engine, user classifier, spam detection |

---

## PHASE 1 — P0: Nền Tảng (Tuần 1-2)

### Mục 1: Thu Hẹp Scope Toán Học

#### Khang — Agent
- [ ] **Thu gọn hypotheses**: Cập nhật `backend/data/derivative_priors.json`, giảm từ 8 hypotheses (H01-H08) xuống còn **4 hypotheses** cho 1 chủ đề "Đạo hàm cơ bản":
  ```
  H01: Đạo hàm lượng giác (sin, cos, tan)
  H02: Đạo hàm mũ & logarit (eˣ, ln x)
  H03: Chain Rule (hàm hợp)
  H04: Quy tắc tính (tổng, hiệu, tích, thương)
  ```
- [ ] **Cập nhật Bayesian tracker**: Sửa `backend/agents/academic_agent/bayesian_tracker.py` — cập nhật prior probabilities, likelihood matrix cho 4 hypotheses mới
- [ ] **Cập nhật HTN rules**: Sửa `backend/configs/htn_rules.yaml` — thiết kế learning path mới gồm 8-10 primitive tasks (thay vì 12) phù hợp với scope thu hẹp
- [ ] **Cập nhật HTN planner**: Sửa `backend/agents/academic_agent/htn_planner.py` cho matching với rules mới

**Tiêu chí hoàn thành**: Chạy test `backend/tests/` pass hết, belief converge nhanh hơn (< 5 câu hỏi thay vì 10)

#### Hưng — Data
- [ ] **Soạn 50-80 câu hỏi chất lượng cao**: Tạo file CSV/JSON theo format `quiz_question_template`, chỉ cho chủ đề "Đạo hàm cơ bản"
  - 15 câu dễ (Beginner)
  - 25 câu trung bình (Intermediate)
  - 20 câu khó (Advanced)
  - Mỗi câu có: question, 4 options, correct_answer, hypothesis_tag, difficulty, explanation
- [ ] **Import vào Supabase**: Cập nhật table `quiz_question_template` với dataset mới
- [ ] **Cập nhật diagnosis scenarios**: Sửa `backend/data/diagnosis/diagnosis_scenarios.json` cho khớp 4 hypotheses mới

**Tiêu chí hoàn thành**: 50+ câu hỏi trong DB, đủ coverage cho 4 hypotheses, mỗi hypothesis có ít nhất 10 câu

#### Huy — Frontend
- [ ] **Cập nhật Roadmap UI**: Sửa `lib/features/roadmap/` — hiển thị chỉ 1 chủ đề "Đạo hàm cơ bản" thay vì nhiều topic
- [ ] **Redesign Today page**: Sửa `lib/features/today/` — thông điệp tập trung vào chủ đề duy nhất, hiển thị tiến trình rõ ràng hơn
- [ ] **Cập nhật quiz data models**: Sửa `lib/features/quiz/data/models/` — đảm bảo models khớp với 4 hypotheses mới từ backend
- [ ] **Cập nhật mock data**: Sửa mock API service nếu cần test offline

**Tiêu chí hoàn thành**: UI chỉ hiện 1 chủ đề, quiz flow hoạt động end-to-end với dataset mới

#### Đức — LLM
- [ ] *(Không có task trực tiếp ở mục này — hỗ trợ Khang review hypothesis mapping nếu cần)*

---

### Mục 2: Xác Định Chức Năng Chatbot + Policy

#### Đức — LLM
- [ ] **Viết system prompt**: Tạo file `backend/configs/chatbot_system_prompt.txt` chứa:
  ```
  Bạn là GrowMate AI, trợ lý học toán cho học sinh THPT Việt Nam.
  BẠN CHỈ ĐƯỢC:
  - Giải thích lời giải, gợi ý phương pháp
  - Trả lời về công thức đạo hàm
  - Động viên, nhắc nhở lịch học
  BẠN KHÔNG ĐƯỢC:
  - Đưa đáp án trực tiếp (chỉ gợi ý)
  - Bàn luận chính trị, game, tình cảm
  - Trả lời về môn khác
  - Tư vấn tâm lý chuyên sâu
  ```
- [ ] **Tích hợp system prompt vào LLM service**: Sửa `backend/core/llm_service.py` — inject system prompt vào mọi LLM call
- [ ] **Tạo policy middleware**: Tạo file `backend/core/policy.py`:
  ```python
  FORBIDDEN_KEYWORDS = ["chính trị", "bạo lực", "tình dục", ...]
  MAX_INPUT_LENGTH = 300
  MAX_OUTPUT_LENGTH = 500
  
  def pre_check(user_input: str) -> str | None:
      """Return template response if off-topic, None if OK"""
      
  def post_check(response: str) -> str:
      """Truncate, sanitize output"""
  ```
- [ ] **Tích hợp middleware vào routes**: Sửa `backend/api/routes/orchestrator.py` — gọi `pre_check()` trước khi forward tới agents, gọi `post_check()` trước khi trả response

**Tiêu chí hoàn thành**: LLM từ chối trả lời off-topic, API reject off-topic input với latency < 50ms (không gọi LLM), output luôn ≤ 500 ký tự

#### Hưng — Data
- [ ] **Xây dựng bảng công thức tra cứu**: Tạo `backend/data/formula_lookup.json` chứa 30+ công thức đạo hàm phổ biến để dùng cho fast-path if-else

**Tiêu chí hoàn thành**: 30+ công thức có đầy đủ LaTeX, explanation, dùng được cho intent lookup

#### Khang — Agent
- [ ] *(Không có task trực tiếp — hỗ trợ Đức review policy tích hợp vào orchestrator flow)*

#### Huy — Frontend
- [ ] *(Không có task trực tiếp ở mục này — chờ backend hoàn thành policy để tích hợp)*

---

### Mục 3c-3e: If-Else Fast Path + Token Management

#### Đức — LLM
- [ ] **Xây dựng intent classifier**: Tạo `backend/core/intent_classifier.py`:
  ```python
  class Intent(Enum):
      FORMULA_LOOKUP = "formula_lookup"      # → tra bảng, không gọi LLM
      EXPLAIN_LAST_QUIZ = "explain_quiz"     # → template + context
      STUDY_TIP = "study_tip"               # → template cố định
      GENERAL_MATH = "general_math"          # → gọi LLM
      OFF_TOPIC = "off_topic"               # → reject
  
  def classify(user_input: str) -> Intent:
      """Regex + keyword matching → phân loại intent"""
  ```
- [ ] **Xây dựng template responses**: Tạo `backend/data/template_responses.json` — 50+ câu trả lời mẫu cho các intent phổ biến (công thức, mẹo học, động viên)
- [ ] **Token counter middleware**: Thêm vào `backend/core/llm_service.py`:
  ```python
  MAX_TOKENS_PER_CALL = 500
  MAX_CONTEXT_MESSAGES = 5
  DAILY_QUOTA_FREE = 20  # lượt/ngày/user
  
  async def check_quota(user_id: str) -> bool:
      """Check Supabase counter, return False if exceeded"""
  ```

**Tiêu chí hoàn thành**: 60%+ câu hỏi test được trả lời bằng template (không gọi LLM), latency < 200ms, user bị block sau 20 lượt chat/ngày

#### Hưng — Data
- [ ] **Tạo Supabase table `user_token_usage`**: Schema:
  ```sql
  CREATE TABLE user_token_usage (
    user_id UUID,
    date DATE,
    call_count INT DEFAULT 0,
    total_tokens INT DEFAULT 0,
    PRIMARY KEY (user_id, date)
  );
  ```
- [ ] **API endpoint `/api/v1/quota`**: Trả về `{used: 15, limit: 20, remaining: 5}` cho frontend hiển thị

**Tiêu chí hoàn thành**: Counter reset lúc 00:00, API `/quota` hoạt động chính xác

#### Huy — Frontend
- [ ] **Tích hợp quota API**: Gọi `/api/v1/quota` khi mở chat, hiển thị counter
- [ ] **Design & build quota indicator**: Badge nhỏ trên icon chat hiện số lượt còn lại (ví dụ: 💬 15)
- [ ] **Giới hạn input**: Thêm `maxLength: 300` vào TextField chat, hiển thị counter ký tự
- [ ] **Xử lý quota exceeded**: Khi hết lượt → hiện popup thân thiện "Bạn đã dùng hết 20 lượt hôm nay, quay lại ngày mai nhé!" với animation nhẹ

**Tiêu chí hoàn thành**: UI hiện đúng số lượt còn lại, block input khi hết quota, UI match design system (soft gray, rounded, blue accent)

---

## PHASE 2 — P1: Gamification (Tuần 3-4)

### Mục 4d + 5: Leaderboard, Vinh Danh & Học Cùng Nhau

#### Hưng — Data
- [ ] **Tạo Supabase tables**:
  ```sql
  -- Bảng XP
  CREATE TABLE user_xp (
    user_id UUID PRIMARY KEY,
    weekly_xp INT DEFAULT 0,
    total_xp INT DEFAULT 0,
    current_streak INT DEFAULT 0,
    longest_streak INT DEFAULT 0,
    last_active_date DATE,
    updated_at TIMESTAMPTZ
  );
  
  -- Bảng badges
  CREATE TABLE user_badges (
    id UUID PRIMARY KEY,
    user_id UUID,
    badge_type TEXT,        -- 'streak_7', 'top_10', 'mastery_chain_rule'
    badge_name TEXT,        -- 'Chiến thần Đạo hàm'
    earned_at TIMESTAMPTZ
  );
  ```
- [ ] **API endpoints**:
  - `GET /api/v1/leaderboard?period=weekly&limit=20` — Top users theo tuần
  - `GET /api/v1/leaderboard/me` — Vị trí của user hiện tại
  - `POST /api/v1/xp/add` — Cộng XP sau mỗi quiz (gọi internal)
  - `GET /api/v1/badges` — Danh sách badges của user
- [ ] **XP calculation logic**: Tạo `backend/core/xp_engine.py`:
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
- [ ] **Badge awarding logic**: Auto-check sau mỗi session:
  - Streak 7 ngày → badge "Kiên trì"
  - Top 10 tuần → badge "Siêu sao tuần"
  - Mastery 100% 1 topic → badge "Chiến thần [Topic]"

**Tiêu chí hoàn thành**: API trả đúng leaderboard data, XP tính đúng, badges auto-award

#### Khang — Agent
- [ ] **Tích hợp XP vào reward engine**: Sửa `backend/agents/strategy_agent/reward_engine.py` — thêm XP signal vào reward calculation để Q-learning biết user đang engage hay không

**Tiêu chí hoàn thành**: Q-learning nhận được XP signal, điều chỉnh strategy phù hợp

#### Huy — Frontend
- [ ] **Design & build LeaderboardPage**: Tạo `lib/features/leaderboard/`
  ```
  leaderboard/
  ├── presentation/
  │   ├── pages/
  │   │   └── leaderboard_page.dart
  │   ├── cubit/
  │   │   └── leaderboard_cubit.dart
  │   └── widgets/
  │       ├── leaderboard_card.dart      — mỗi user 1 card
  │       ├── top_three_podium.dart      — 🥇🥈🥉 animation
  │       ├── my_rank_banner.dart        — highlight vị trí user
  │       └── period_tab_bar.dart        — Tuần / Tháng / Tổng
  ```
- [ ] **Tạo LeaderboardCubit**:
  ```dart
  class LeaderboardCubit extends Cubit<LeaderboardState> {
    Future<void> loadWeeklyLeaderboard();
    Future<void> loadMyRank();
    Future<void> switchPeriod(LeaderboardPeriod period);
  }
  ```
- [ ] **Tạo LeaderboardRepository**: Gọi API `/leaderboard`, `/badges`, cache local
- [ ] **Design badge showcase**: Trong `lib/features/achievement/` — grid hiển thị badges đã có + badges chưa unlock (greyed out)
- [ ] **Notification vinh danh**: Toast/snackbar animation khi user đạt badge mới hoặc lọt top
- [ ] **Cập nhật BottomNavBar**: Thêm tab Leaderboard hoặc gắn vào ProgressPage
- [ ] **Tích hợp XP vào quiz flow**: Sau khi submit quiz → gọi add XP → refresh leaderboard
- [ ] **Push notification logic**: Dùng `lib/features/notification/` — tạo notification khi đạt badge

**Tiêu chí hoàn thành**: Leaderboard UI hoạt động, có animation podium top 3, badge grid hiển thị đúng, data flow API → Repository → Cubit → UI hoàn chỉnh, XP cộng đúng sau quiz

#### Đức — LLM
- [ ] *(Không có task trực tiếp ở mục này)*

---

### Mục 7b: Hệ Thống Tim (Lives)

#### Hưng — Data
- [ ] **Tạo Supabase table**:
  ```sql
  CREATE TABLE user_lives (
    user_id UUID PRIMARY KEY,
    current_lives INT DEFAULT 3 CHECK (current_lives >= 0 AND current_lives <= 3),
    last_life_lost_at TIMESTAMPTZ,
    last_regen_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
  );
  ```
- [ ] **API endpoints**:
  - `GET /api/v1/lives` — `{current: 2, max: 3, next_regen_in_seconds: 14400}`
  - `POST /api/v1/lives/lose` — Trừ 1 tim khi sai (gọi internal sau quiz)
  - `POST /api/v1/lives/regen` — Cron job hồi sinh +1 tim mỗi 8 giờ
- [ ] **Business logic**: Tạo `backend/core/lives_engine.py`:
  ```python
  MAX_LIVES = 3
  REGEN_HOURS = 8
  
  async def can_play(user_id: str) -> bool:
      """Return False if lives == 0"""
  
  async def lose_life(user_id: str) -> int:
      """Decrement, return remaining lives"""
  
  async def check_regen(user_id: str) -> int:
      """Auto-regen if enough time passed"""
  ```
- [ ] **Guard quiz endpoint**: Sửa quiz route — check `can_play()` trước khi cho làm quiz

**Tiêu chí hoàn thành**: User không thể làm quiz khi hết tim, tim hồi sinh tự động sau 8h

#### Huy — Frontend
- [ ] **Design & build lives indicator**: Widget ❤️❤️❤️ ở góc trên quiz page
  ```
  lib/features/quiz/presentation/widgets/
  └── lives_indicator.dart   — 3 tim, animation khi mất tim (tim vỡ)
  ```
- [ ] **Design & build "hết tim" screen**: Full-screen overlay:
  - Countdown timer đến lần hồi sinh tiếp theo
  - Nút "Xem lại bài sai" (để nhận +1 tim)
  - Nút "Mời bạn bè" (để nhận +1 tim)
  - Style: soft, không gây frustration (tone động viên)
- [ ] **Animation mất tim**: Tim vỡ + rơi, màn hình rung nhẹ
- [ ] **Tạo LivesCubit**: Quản lý state lives, tích hợp vào quiz flow
  ```dart
  class LivesCubit extends Cubit<LivesState> {
    Future<void> loadLives();
    Future<void> loseLife();
    bool get canPlay => state.currentLives > 0;
    Duration get nextRegenIn => ...;
  }
  ```
- [ ] **Guard quiz navigation**: Nếu `canPlay == false` → navigate tới "hết tim" screen thay vì quiz
- [ ] **Countdown timer**: Stream timer đếm ngược tới hồi sinh

**Tiêu chí hoàn thành**: Animation mượt, "hết tim" screen thân thiện, countdown chính xác, flow hoàn chỉnh: mất tim → block quiz → countdown → hồi sinh → unblock

---

### Mục 11: Sổ Tay Công Thức Trong Progress

#### Hưng — Data
- [ ] **Tạo formula database**: Tạo `backend/data/formula_handbook.json`:
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
- [ ] **API endpoint**: `GET /api/v1/formulas?category=basic_trig&user_id=xxx`
  - Trả về formulas + trạng thái mastery của user cho mỗi formula
  - Mastery = dựa trên quiz performance cho hypothesis liên quan

**Tiêu chí hoàn thành**: 30+ formulas có đầy đủ LaTeX, explanation, example, mapping hypothesis. API trả đúng data, mastery tính đúng từ quiz history

#### Khang — Agent
- [ ] **Liên kết formula với hypothesis**: Khi user yếu H01 → agent gợi ý highlight các formula thuộc H01 cần ôn. Tích hợp vào orchestrator decision

**Tiêu chí hoàn thành**: Agent biết recommend đúng formula group khi belief cho hypothesis thấp

#### Huy — Frontend
- [ ] **Redesign ProgressPage**: Cập nhật `lib/features/progress/` — thêm tab/section "Sổ tay công thức"
  ```
  progress/
  └── presentation/
      ├── pages/
      │   └── progress_page.dart        — thêm tab "Sổ tay"
      └── widgets/
          ├── formula_handbook_tab.dart  — NEW
          ├── formula_category_card.dart — NEW: card cho mỗi nhóm CT
          ├── formula_detail_card.dart   — NEW: hiển thị LaTeX + ví dụ
          └── mastery_indicator.dart     — ✅ đã thuộc / 🔄 đang học / 🔒 chưa mở
  ```
- [ ] **LaTeX rendering**: Tích hợp `flutter_math_fork` để render công thức đẹp
- [ ] **Search bar**: Cho user tìm kiếm công thức nhanh
- [ ] **Tạo FormulaHandbookCubit**: Load formulas từ API, filter theo category, search
- [ ] **Tạo FormulaRepository**: Cache formulas local cho offline access (user tra cứu không cần internet)
- [ ] **Tích hợp offline storage**: Dùng `lib/features/offline/` — save formulas vào local DB

**Tiêu chí hoàn thành**: Sổ tay hiển thị đẹp, LaTeX render chính xác, search hoạt động, mastery indicator đúng, offline accessible

---

## PHASE 3 — P2: Nâng Cao (Tuần 5-6)

### Mục 3a: Onboarding Quiz + Phân Loại Cá Nhân

#### Khang — Agent
- [ ] **Classification algorithm**: Tạo `backend/core/user_classifier.py`:
  ```python
  class UserLevel(Enum):
      BEGINNER = "beginner"         # < 40% đúng
      INTERMEDIATE = "intermediate" # 40-70% đúng
      ADVANCED = "advanced"         # > 70% đúng
  
  def classify(onboarding_results: dict) -> UserLevel:
      """Phân loại dựa trên accuracy + thời gian trả lời"""
  
  def get_study_plan(level: UserLevel) -> StudyPlan:
      """Trả về plan phù hợp: duration/ngày, nội dung, difficulty"""
  ```
- [ ] **Tích hợp classification vào orchestrator**: Sau onboarding → set initial belief priors theo level, điều chỉnh HTN starting point

**Tiêu chí hoàn thành**: Onboarding quiz phân loại chính xác 80%+, mỗi level có plan khác nhau, agent nhận đúng initial state

#### Đức — LLM
- [ ] **Prompt template theo level**: Mỗi UserLevel có system prompt khác nhau:
  - Beginner: ngôn ngữ đơn giản, nhiều ví dụ, giải thích từng bước
  - Intermediate: ngôn ngữ bình thường, gợi ý phương pháp
  - Advanced: ngôn ngữ chuyên sâu, thách thức, mẹo giải nhanh
- [ ] **Dynamic prompt injection**: Sửa `backend/core/llm_service.py` — load prompt template phù hợp với user level trước mỗi LLM call

**Tiêu chí hoàn thành**: Chatbot nói khác nhau rõ rệt giữa 3 level, test 10 câu hỏi mỗi level

#### Hưng — Data
- [ ] **Thiết kế 10 câu hỏi onboarding**: Soạn câu hỏi chẩn đoán trình độ ban đầu
  - Câu 1-3: Dễ (kiểm tra kiến thức cơ bản)
  - Câu 4-6: Trung bình (áp dụng quy tắc)
  - Câu 7-10: Khó (bài tổng hợp)
- [ ] **API endpoints**:
  - `POST /api/v1/onboarding/submit` — Nhận kết quả → phân loại → trả StudyPlan
  - `GET /api/v1/user/profile` — Trả về level, plan, preferences
  - `PUT /api/v1/user/profile` — Cập nhật goal, available_time
- [ ] **Supabase table update**: Thêm columns vào user profile:
  ```sql
  ALTER TABLE user_profiles ADD COLUMN
    user_level TEXT DEFAULT 'beginner',
    study_goal TEXT,             -- 'exam_prep' | 'explore'
    daily_minutes INT DEFAULT 15,
    onboarded_at TIMESTAMPTZ;
  ```

**Tiêu chí hoàn thành**: Onboarding flow hoạt động end-to-end, profile lưu đúng, 10 câu hỏi chất lượng

#### Huy — Frontend
- [ ] **Design & build OnboardingPage**: Tạo `lib/features/onboarding/`
  ```
  onboarding/
  └── presentation/
      ├── pages/
      │   ├── onboarding_welcome_page.dart  — "Chào mừng! Mình tìm hiểu bạn nhé"
      │   ├── onboarding_goal_page.dart     — Chọn: Luyện thi / Trải nghiệm
      │   ├── onboarding_quiz_page.dart     — 10 câu chẩn đoán
      │   └── onboarding_result_page.dart   — "Bạn ở level X! Đây là plan của bạn"
      ├── cubit/
      │   └── onboarding_cubit.dart
      └── widgets/
          ├── goal_selection_card.dart
          ├── level_result_animation.dart
          └── study_plan_preview.dart
  ```
- [ ] **Animation kết quả**: Reveal animation khi hiện level (confetti cho Advanced, encouraging cho Beginner)
- [ ] **Tạo OnboardingCubit**: Quản lý state 4 bước onboarding
- [ ] **Tạo OnboardingRepository**: Submit results → nhận classification + plan
- [ ] **Cập nhật app_router**: Nếu user chưa onboard → redirect tới OnboardingPage trước khi vào main app
- [ ] **Lưu level local**: Cache user level để adjust UI behavior (hint visibility, timer, v.v.)

**Tiêu chí hoàn thành**: First-time user bắt buộc qua onboarding, returning user skip, level persist, animation phù hợp từng level

---

### Mục 4c: Xử Lý User Bỏ Dở / Không Nghiêm Túc

#### Khang — Agent
- [ ] **Spam detection logic**: Thêm vào `backend/agents/empathy_agent/particle_filter.py`:
  ```python
  def detect_spam(signals: list[BehavioralSignal]) -> bool:
      """True if: answer_time < 2s for 3+ consecutive, accuracy < 20%"""
  
  def detect_afk(last_signal_time: datetime) -> bool:
      """True if idle > 180 seconds"""
  ```
- [ ] **Tích hợp vào orchestrator**: Khi detect spam → orchestrator pause quiz + gửi warning message
- [ ] **Off-topic counter**: Track số lần user hỏi off-topic trong session → sau 3 lần → gentle redirect

**Tiêu chí hoàn thành**: Spam detected trong < 5 giây, AFK detected chính xác, off-topic redirect hoạt động

#### Hưng — Data
- [ ] **Session recovery endpoint**: `GET /api/v1/session/pending` — trả về session dở dang (nếu có)
- [ ] **Auto-save session state**: Sửa `backend/core/state_manager.py` — save state mỗi 30 giây + khi user idle

**Tiêu chí hoàn thành**: User quay lại → thấy "Bạn còn bài dở, tiếp tục nhé!", resume đúng chỗ

#### Huy — Frontend
- [ ] **Design & build spam warning dialog**: "Bạn ơi, chậm lại suy nghĩ kỹ nhé! 🤔" — tone nhẹ nhàng
- [ ] **Design & build resume banner**: Banner trên TodayPage khi có session dở
- [ ] **Design & build AFK overlay**: Overlay mờ khi idle > 3 phút, nhấn để tiếp tục
- [ ] **Session recovery flow**: Khi mở app → check `/session/pending` → nếu có → hiện resume banner
- [ ] **AFK timer**: Timer client-side, khi idle 3 phút → auto-pause quiz → notify backend
- [ ] **Spam detection client-side**: Track answer time, nếu < 2s liên tiếp → hiện warning trước khi submit

**Tiêu chí hoàn thành**: Các dialog/overlay match tone app (thân thiện, không aggressive), resume flow hoàn chỉnh, AFK/spam detected cả client + server

#### Đức — LLM
- [ ] *(Không có task trực tiếp — hỗ trợ Khang nếu cần LLM generate warning messages)*

---

### Mục 6: Chống Leak Nội Dung

#### Hưng — Data
- [ ] **Server-side answer validation**: Đảm bảo API `POST /api/v1/quiz/submit` KHÔNG trả `correct_answer` trong response ban đầu — chỉ trả `is_correct: true/false` + explanation
- [ ] **Shuffle logic**: Khi serve quiz → shuffle thứ tự câu hỏi + thứ tự options mỗi lần
- [ ] **Rate limiting**: Giới hạn 5 quiz sessions / ngày / user (chống crawl)
- [ ] **Request signing**: Thêm HMAC signature cho quiz-related requests

**Tiêu chí hoàn thành**: Không thể extract đáp án từ API response, rate limit enforce đúng

#### Huy — Frontend
- [ ] **FLAG_SECURE trên Android**: Sửa `android/app/src/main/kotlin/.../MainActivity.kt`:
  ```kotlin
  import android.view.WindowManager
  
  override fun onCreate(savedInstanceState: Bundle?) {
      super.onCreate(savedInstanceState)
      window.setFlags(
          WindowManager.LayoutParams.FLAG_SECURE,
          WindowManager.LayoutParams.FLAG_SECURE
      )
  }
  ```
- [ ] **Disable text selection** trên quiz content: Ngăn copy/paste câu hỏi
- [ ] **Xóa local cache đáp án**: Đảm bảo quiz data trong memory KHÔNG chứa correct_answer
- [ ] **Obfuscate quiz state**: Không log quiz data ra console/debug

**Tiêu chí hoàn thành**: Screenshot bị block trên Android khi đang làm quiz, text không select được, inspect app memory → không thấy đáp án

---

### Mục 7a: Chia Chế Độ Học (Luyện Thi vs Trải Nghiệm)

#### Khang — Agent
- [ ] **Điều chỉnh strategy theo mode**:
  - Exam Prep: timer enabled, difficulty auto-scale, strict scoring
  - Explore: no timer, more hints, lenient scoring
- [ ] **Cập nhật Q-learning states**: Thêm mode vào state vector → agent biết đang ở chế độ nào

**Tiêu chí hoàn thành**: Agent hành xử khác nhau rõ rệt giữa 2 mode

#### Hưng — Data
- [ ] **Thêm `mode` param**: Tất cả quiz/session endpoints nhận `mode: 'exam_prep' | 'explore'`

**Tiêu chí hoàn thành**: API xử lý đúng theo mode

#### Huy — Frontend
- [ ] **Design & build mode selection screen**: 2 card lớn trước khi vào quiz:
  - 🎓 "Luyện thi" — icon nghiêm túc, timer displayed
  - 🎮 "Trải nghiệm" — icon vui nhộn, "Học chậm, hiểu sâu"
- [ ] **Mode state management**: Lưu mode đã chọn, pass vào API calls
- [ ] **Conditional UI**: Timer hiện/ẩn, hint button hiện/ẩn theo mode

**Tiêu chí hoàn thành**: UI phân biệt rõ 2 mode, Exam mode có timer + strict, Explore mode có hints + relaxed

#### Đức — LLM
- [ ] **Điều chỉnh LLM tone theo mode**: Exam mode → concise, đi thẳng vào vấn đề. Explore mode → giải thích kỹ, nhiều ví dụ

**Tiêu chí hoàn thành**: LLM response style phù hợp với mode

---

## PHASE 4 — P3: Premium Features (Tuần 7-8)

### Mục 3b: ChatVoice (Speech-to-Text)

#### Huy — Frontend (Lead)
- [ ] **Tích hợp STT package**: Thêm `speech_to_text` vào `pubspec.yaml`
- [ ] **Tạo SpeechService**: `lib/core/services/speech_service.dart`
  ```dart
  class SpeechService {
    Future<void> startListening({required String locale}); // 'vi-VN'
    Future<String> stopListening();
    Stream<String> get onPartialResult;
    bool get isListening;
  }
  ```
- [ ] **Tích hợp vào chat input**: Nút mic bên cạnh TextField, nhấn giữ để nói
- [ ] **Permission handling**: Request microphone permission, handle denied gracefully
- [ ] **Design mic button**: Button tròn, animation pulse khi đang nghe
- [ ] **Design listening overlay**: Hiển thị waveform + text đang transcribe real-time

**Tiêu chí hoàn thành**: Nói tiếng Việt → text chính xác 80%+, UX mượt mà

---

### Mục 5b: Kahoot-Style Multiplayer Quiz

#### Hưng — Data
- [ ] **Tạo Supabase tables cho multiplayer**:
  ```sql
  CREATE TABLE quiz_rooms (
    room_id TEXT PRIMARY KEY,
    host_user_id UUID,
    state TEXT DEFAULT 'waiting',  -- waiting | in_progress | finished
    current_question INT DEFAULT 0,
    created_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
  );
  
  CREATE TABLE quiz_room_players (
    room_id TEXT,
    user_id UUID,
    score INT DEFAULT 0,
    answers_correct INT DEFAULT 0,
    joined_at TIMESTAMPTZ,
    PRIMARY KEY (room_id, user_id)
  );
  ```
- [ ] **WebSocket room management**: Mở rộng `backend/api/ws/`:
  ```python
  # ws/multiplayer.py
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
- [ ] **Scoring**: Điểm = đúng (100) + speed bonus (max 50, giảm theo thời gian)
- [ ] **Room lifecycle**: Create → Join → Start → Question loop → Results → Close

**Tiêu chí hoàn thành**: Room CRUD hoạt động, WS broadcast đúng, scoring chính xác

#### Khang — Agent
- [ ] **Question selection cho multiplayer**: Chọn câu hỏi phù hợp với average level của room (không quá dễ, không quá khó)

**Tiêu chí hoàn thành**: Câu hỏi phù hợp level trung bình players trong room

#### Huy — Frontend
- [ ] **Design & build multiplayer screens**:
  ```
  lib/features/multiplayer/
  ├── presentation/
  │   ├── pages/
  │   │   ├── create_room_page.dart
  │   │   ├── waiting_room_page.dart      — hiển thị avatar players
  │   │   ├── battle_quiz_page.dart       — countdown + 4 options
  │   │   └── battle_results_page.dart    — podium animation
  │   ├── cubit/
  │   │   └── multiplayer_cubit.dart
  │   └── widgets/
  │       ├── player_avatar_row.dart
  │       ├── countdown_timer.dart
  │       ├── answer_reveal_animation.dart
  │       └── podium_widget.dart
  ```
- [ ] **WebSocket integration**: Connect tới multiplayer WS, handle real-time events
- [ ] **MultiplayerCubit**: State management cho room lifecycle
- [ ] **Invite link generation**: Deep link để bạn bè join room

**Tiêu chí hoàn thành**: 2-4 người chơi cùng lúc, real-time scoring, kết quả chính xác

#### Đức — LLM
- [ ] *(Không có task trực tiếp ở mục này)*

---

### Mục 8b: Linh Vật (Mascot System)

#### Huy — Frontend (Lead)
- [ ] **Design 4 mascot characters**: SVG/Lottie animations
  - 🐱 Mèo Toán (Beginner) — biểu cảm: vui, buồn, ngạc nhiên, ngủ
  - 🦊 Cáo Thông Minh (Advanced) — biểu cảm: cool, thách thức, ăn mừng
  - 🐢 Rùa Kiên Trì (hay bỏ dở) — biểu cảm: cổ vũ, kiên nhẫn
  - 🦉 Cú Đêm (học khuya) — biểu cảm: tỉnh táo, buồn ngủ, pha cà phê
- [ ] **Mascot widget**: Widget hiển thị mascot với animation phù hợp context
- [ ] **Mascot selection page**: Cho user chọn mascot khi onboarding
- [ ] **MascotCubit**: Quản lý mascot đã chọn, expression state
- [ ] **Auto-assign logic**: Dựa vào behavior → suggest mascot phù hợp (nếu user không chọn)
- [ ] **Expression triggers**: Map events → expressions:
  ```dart
  quizCorrect → mascot.happy()
  quizWrong → mascot.sad()
  idle3min → mascot.sleep()
  streak5 → mascot.celebrate()
  ```

#### Đức — LLM
- [ ] **Nhân cách hóa chatbot**: Sửa system prompt để chatbot nói theo personality của mascot đã chọn:
  - Mèo Toán: dùng ngôi "mình", dịu dàng, hay khen
  - Cáo Thông Minh: dùng ngôi "tớ", nhanh nhẹn, thách thức
  - Rùa Kiên Trì: dùng ngôi "mình", kiên nhẫn, hay nhắc "từ từ"
  - Cú Đêm: dùng ngôi "tui", casual, hay nói về cà phê

**Tiêu chí hoàn thành**: 4 mascots có animation, auto-switch expression, chatbot personality match

---

### Mục 9: LaTeX + MANIM + AI Chain Lỗi

#### Huy — Frontend
- [ ] **Tích hợp LaTeX**: Thêm `flutter_math_fork` vào pubspec, render tất cả công thức trong quiz + sổ tay + chat
- [ ] **Video player cho MANIM**: Widget play video animation giải thích
- [ ] **Error chain UI**: Hiển thị chuỗi lỗi dạng tree/flow diagram trong DiagnosisPage

**Tiêu chí hoàn thành**: LaTeX đẹp trên mọi screen, video player hoạt động, error chain visualization rõ ràng

#### Đức — LLM (Lead)
- [ ] **AI error chain generation**: Khi user sai → LLM trace ngược chuỗi lỗi, output format:
  ```json
  {
    "error_chain": [
      {"level": "surface", "description": "Quên nhân hệ số 2"},
      {"level": "root", "description": "Chưa hiểu Chain Rule"},
      {"level": "foundation", "description": "Chưa nắm hàm hợp"}
    ],
    "recommendation": "Ôn lại khái niệm hàm hợp trước"
  }
  ```
- [ ] **Pre-render MANIM clips**: Tạo 10-15 animation clips bằng MANIM cho các dạng phổ biến nhất, lưu MP4 trên CDN
- [ ] **Map clips to hypotheses**: Tạo `backend/data/manim_mapping.json`

**Tiêu chí hoàn thành**: Error chain output chính xác, ít nhất 10 MANIM clips

#### Hưng — Data
- [ ] **Serve MANIM clips**: CDN/storage URL cho mỗi clip, API trả URL khi cần
- [ ] **Lưu error chain history**: Supabase table để track error patterns theo user

**Tiêu chí hoàn thành**: API trả đúng clip URL, error history lưu đúng

#### Khang — Agent
- [ ] **Tích hợp error chain vào Bayesian tracker**: Kết quả error chain → update belief distribution chính xác hơn (biết root cause, không chỉ surface error)

**Tiêu chí hoàn thành**: Belief update chính xác hơn dựa trên error chain depth

---

### Mục 10: Google Calendar Integration

#### Huy — Frontend (Lead)
- [ ] **Thêm dependencies**: `google_sign_in`, `googleapis` vào pubspec
- [ ] **Google OAuth flow**: Login with Google → request Calendar scope
- [ ] **CalendarService**: `lib/core/services/calendar_service.dart`
  ```dart
  class CalendarService {
    Future<void> syncStudyPlan(StudyPlan plan);
    Future<void> createEvent({
      required String title,
      required DateTime start,
      required Duration duration,
      String? description,
    });
    Future<void> deleteAllGrowMateEvents();
  }
  ```
- [ ] **Auto-sync**: Khi AI tạo/update study plan → auto create Calendar events
- [ ] **Design Calendar sync toggle**: Trong Settings/Profile — switch "Đồng bộ Google Calendar"
- [ ] **Design sync confirmation**: "Đã thêm 5 sự kiện vào Calendar!" với preview

**Tiêu chí hoàn thành**: Study plan tự động xuất hiện trong Google Calendar, có reminder 15 phút trước

#### Hưng — Data
- [ ] **Study plan generation endpoint**: `GET /api/v1/plan/weekly` — trả về plan tuần dạng structured data cho Calendar sync

**Tiêu chí hoàn thành**: API trả plan tuần đúng format, đủ data cho Calendar event creation

---

### Mục 12: AI Chain Câu Hỏi + Chunking

#### Đức — LLM (Lead)
- [ ] **Question generator**: Tạo `backend/scripts/generate_questions.py`:
  ```python
  # 1. Load template pool
  # 2. Fill variables randomly
  # 3. Calculate answer using SymPy
  # 4. Generate 3 distractors (common mistakes)
  # 5. Validate & output to JSON/CSV
  ```
- [ ] **SymPy verification**: Mỗi câu hỏi generated → verify đáp án bằng symbolic math
- [ ] **RAG chunking**: Tạo `backend/core/chunking_service.py`:
  ```python
  def chunk_textbook(content: str, chunk_size: int = 500) -> list[Chunk]:
      """Split content into semantic chunks"""
  
  def embed_chunks(chunks: list[Chunk]) -> list[EmbeddedChunk]:
      """Generate embeddings via Gemini API"""
  
  def search_chunks(query: str, top_k: int = 3) -> list[Chunk]:
      """Retrieve most relevant chunks for query"""
  ```

**Tiêu chí hoàn thành**: Generate 100+ câu hỏi verified, RAG search trả kết quả relevant

#### Hưng — Data
- [ ] **Embedding storage**: Supabase pgvector extension cho storing embeddings
- [ ] **API endpoint**: `POST /api/v1/rag/query` — nhận query → search chunks → return relevant context
- [ ] **Import generated questions**: Validate & import câu hỏi AI-generated vào quiz_question_template

**Tiêu chí hoàn thành**: Embeddings lưu đúng, API query hoạt động, câu hỏi import thành công

---

## PHASE 5 — Bonus / Stretch Goals (Tuần 9+)

### Mục 4a-4b: Session Analytics + Âm Thanh
- **Hưng**: Tạo analytics Supabase tables, API endpoints cho session time tracking
- **Huy**: Design & implement analytics visualization trong Progress page, client-side tracking
- **Khang**: Tích hợp analytics signals vào Empathy agent quyết định

### Mục 8a: Feature "Tương Lai Của Bạn" (Avatar AI)
- **Huy**: Design avatar template gallery (20+ pre-made avatars), camera integration + avatar selection flow
- **Đức**: (Nếu có thời gian) AI image generation API integration

---

## Tổng Hợp Khối Lượng Theo Người

### Huy — Frontend (UI/UX + Logic)
| Phase | Nhiệm vụ chính | Files chính |
|-------|----------------|-------------|
| P1 | Roadmap/Today/quiz model update, quota UI + logic | `roadmap/`, `today/`, `quiz/data/models/`, cubits |
| P2 | LeaderboardPage + cubit, LivesCubit + lives UI, badge showcase | `leaderboard/`, `quiz/widgets/`, achievements |
| P2 | Sổ tay công thức UI + cubit + offline cache, LaTeX integration | `progress/`, `formula_handbook_cubit.dart` |
| P2 | OnboardingPage 4 bước + cubit, mode selection, spam/AFK/resume dialogs | `onboarding/`, quiz pages, `app_router.dart` |
| P2 | FLAG_SECURE, text selection disable, obfuscate quiz state | `MainActivity.kt`, quiz widgets |
| P3 | STT integration + mic UI, multiplayer screens + WS + cubit | `speech_service.dart`, `multiplayer/` |
| P3 | 4 mascots design + animation + MascotCubit | Mascot assets, cubit |
| P3 | LaTeX rendering, MANIM video player, error chain UI | `flutter_math_fork`, video widget |
| P3 | Google Calendar sync + OAuth + CalendarService | `calendar_service.dart`, settings |

### Hưng — Data Engineering
| Phase | Nhiệm vụ chính | Files chính |
|-------|----------------|-------------|
| P1 | Soạn 50-80 câu hỏi, import Supabase, diagnosis scenarios | Quiz CSV/JSON, `diagnosis_scenarios.json` |
| P1 | Formula lookup data, token usage table, quota API | `formula_lookup.json`, Supabase, routes |
| P2 | XP/badges/lives Supabase tables + API endpoints + engines | `xp_engine.py`, `lives_engine.py`, routes |
| P2 | Formula handbook data + API, onboarding questions + API + profile schema | `formula_handbook.json`, routes, Supabase |
| P2 | Session recovery API, auto-save state, shuffle logic, rate limiting | `state_manager.py`, routes |
| P2 | Anti-leak: server-side validation, HMAC signing, mode param | Routes, `security.py` |
| P3 | Multiplayer Supabase tables + WS rooms, MANIM clip serving | `ws/multiplayer.py`, Supabase |
| P3 | Weekly plan API, RAG embedding storage, generated question import | Routes, Supabase pgvector |

### Đức — LLM & NLP
| Phase | Nhiệm vụ chính | Files chính |
|-------|----------------|-------------|
| P1 | System prompt, policy middleware, LLM service integration | `chatbot_system_prompt.txt`, `policy.py`, `llm_service.py` |
| P1 | Intent classifier, template responses, token counter | `intent_classifier.py`, `template_responses.json` |
| P2 | Prompt templates theo level (Beginner/Intermediate/Advanced) | `llm_service.py`, prompt configs |
| P2 | LLM tone theo mode (Exam/Explore) | `llm_service.py` |
| P3 | Mascot personality prompts (4 nhân cách khác nhau) | `chatbot_system_prompt.txt` |
| P3 | AI error chain generation, MANIM clips (pre-render 10-15 clips) | `generate_questions.py`, MANIM scripts |
| P3 | Question generator (SymPy verification), RAG chunking service | `chunking_service.py` |

### Khang — Agent & Orchestration
| Phase | Nhiệm vụ chính | Files chính |
|-------|----------------|-------------|
| P1 | Thu gọn hypotheses, Bayesian tracker, HTN rules + planner | `bayesian_tracker.py`, `htn_rules.yaml`, `htn_planner.py` |
| P2 | XP signal → reward engine, formula → hypothesis linking | `reward_engine.py`, orchestrator |
| P2 | User classifier (onboarding), initial belief setting | `user_classifier.py`, `bayesian_tracker.py` |
| P2 | Spam/AFK detection, off-topic counter, orchestrator integration | `particle_filter.py`, `engine.py` |
| P2 | Q-learning mode adjustment (Exam/Explore states) | `q_learning.py` |
| P3 | Multiplayer question selection, error chain → belief update | Academic agent, orchestrator |

---

## Timeline Tổng Quan

```
Tuần 1-2  ████████████████  PHASE 1 — P0: Nền tảng (scope, policy, token)
Tuần 3-4  ████████████████  PHASE 2 — P1: Gamification (XP, lives, formulas)
Tuần 5-6  ████████████████  PHASE 3 — P2: Nâng cao (onboarding, anti-leak, modes)
Tuần 7-8  ████████████████  PHASE 4 — P3: Premium (STT, multiplayer, mascots, MANIM)
Tuần 9+   ████████          PHASE 5 — Bonus (analytics, avatar AI)
```

---

## Quy Tắc Làm Việc

1. **Daily standup**: Mỗi ngày mỗi người update 3 dòng: Hôm qua làm gì / Hôm nay làm gì / Blocker
2. **PR review**: Mỗi PR cần ít nhất 1 người review trước khi merge
3. **Testing**: Khang + Đức + Hưng viết unit tests cho backend, Huy viết widget tests cho frontend
4. **Demo cuối phase**: Mỗi 2 tuần demo cho nhau (và Mentor nếu có) để nhận feedback sớm
5. **Dependency**: Nếu task A phụ thuộc task B (ví dụ Huy cần API từ Hưng) → Hưng ưu tiên hoàn thành API contract/mock trước để Huy unblock
6. **Cross-team sync**:
   - **Huy ↔ Hưng**: Sync API contract (request/response schema) trước khi code
   - **Đức ↔ Khang**: Sync khi LLM output cần đi qua agent orchestrator
   - **Hưng ↔ Đức**: Sync khi cần data format cho LLM (template, formula, chunking)
