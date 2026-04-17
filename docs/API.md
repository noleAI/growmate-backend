# GrowMate API Design

## 1. Overview & Architecture

The GrowMate backend API is designed for a cloud-native, serverless environment (e.g., Cloud Run with FastAPI, scaling to zero) to support the Multi-Agent AI architecture. It leverages stateless RESTful endpoints for standard operations and WebSockets for real-time behavioral data ingestion to power the Agentic workflows natively.

### Core Principles
- **Stateless & Serverless-Ready**: Agent states (Belief Distribution, HTN Plan Tree, Particle Filter States) are loaded from the database or in-memory stores (e.g., Redis) per request to allow seamless horizontal scaling.
- **Real-Time Agentic Flow**: Uses WebSockets to ingest high-frequency behavioral signals, enabling the **Empathy Agent** to perform online Particle Filter state estimation without HTTP overhead.
- **Data Privacy & Ephemerality**: High-volume telemetry (`behavioral_signals`, `episodic_memory`) is strictly temporary (TTL 24h as per `supabase.sql`), decoupled from the long-term `q_table`.
- **Transparency-First**: Every significant algorithmic decision writes to `audit_logs`, enabling the Inspection Dashboard.
- **Authentication**: All endpoints expect a valid Supabase JWT in the `Authorization: Bearer <token>` header to respect Row Level Security (RLS).

---

## 2. API Endpoints

### 2.1. Session Management
Manages the lifecycle of a learning session (`learning_sessions` table).

*   **`POST /api/v1/sessions`**
    *   **Description**: Initializes a new learning session. Bootstraps the Academic Agent's prior beliefs and the Empathy Agent's initial particles.
    *   **Request Body**: `{ "subject": "math", "topic": "derivative" }`
    *   **Response**: `{ "session_id": "uuid", "status": "active", "start_time": "...", "initial_state": {...} }`
*   **`PATCH /api/v1/sessions/{session_id}`**
    *   **Description**: Updates session status (e.g., completing or abandoning the session).
    *   **Request Body**: `{ "status": "completed" }`
    *   **Response**: `200 OK`

### 2.2. Academic Agent (HTN & Bayesian Tracking)
Handles learning interactions, hypothesis updates, and plan adjustments.

*   **`POST /api/v1/academic/{session_id}/interact`**
    *   **Description**: Receives a student's answer or request for a hint. Triggers **Bayesian Hypothesis Tracking**.
    *   **Request Body**: 
        ```json
        {
          "action_type": "submit_quiz",
          "quiz_id": "uuid",
          "response_data": { "selected_option": "A", "time_taken_sec": 45 }
        }
        ```
    *   **Agentic Flow**: 
        1. Calculate likelihood of the response given the current concepts.
        2. Perform Bayesian Belief Update.
        3. If failure detected, trigger HTN Plan Repair.
        4. Log to `episodic_memory` and conditionally to `audit_logs`.
    *   **Response**:
        ```json
        {
          "next_node_type": "hint",
          "content": "...",
          "plan_repaired": true,
          "belief_entropy": 0.85
        }
        ```

### 2.3. Empathy Agent (Particle Filter)
Tracks the user's emotional/cognitive state using real-time signals.

*   **`WS /ws/v1/behavior/{session_id}`**
    *   **Description**: WebSocket connection for real-time telemetry. Ingests raw `behavioral_signals` to feed the Particle Filter.
    *   **Client Payload (Frequent)**: 
        `{ "typing_speed": 120, "correction_rate": 0.15, "idle_time": 2.5 }`
    *   **Server Processing**:
        - Buffers and calculates moving averages.
        - Runs **Particle Filter State Estimation** to update distribution of hidden states (e.g., focused, confused, exhausted).
    *   **Server Push (On Demand)**:
        - If Uncertainty Score > Threshold -> Push HITL trigger.
        - If Exhausted state likelihood > Threshold -> Push Recovery Mode intervention.
        `{ "event": "intervention_proposed", "type": "recovery_mode", "confidence": 0.88 }`

### 2.4. Orchestrator & Human-in-the-Loop (HITL)
Coordinates fallback when algorithms detect high uncertainty.

*   **`POST /api/v1/orchestrator/hitl/{session_id}/respond`**
    *   **Description**: Called when the student (or parent) responds to a system-triggered HITL prompt (e.g., "You seem tired. Want to switch to a mini-game?").
    *   **Request Body**: `{ "intervention_type": "recovery_mode", "accepted": true }`
    *   **Agentic Flow**: Consolidates decision, updates Q-Learning parameters via reward proxy, logs confirmation in `audit_logs`.

### 2.5. Transparency & Inspection Dashboard
Provides insights strictly for monitoring, debugging, and providing transparency to stakeholders.

*   **`GET /api/v1/inspection/belief-state/{session_id}`**
    *   **Response**: Array of current probabilities mapped across the Knowledge Graph nodes.
*   **`GET /api/v1/inspection/particle-state/{session_id}`**
    *   **Response**: Representation of the current 100 particles to visualize the Empathy model's distribution.
*   **`GET /api/v1/inspection/q-values`**
    *   **Response**: Paginated view of the `q_table` for RL Strategy policy transparency.
*   **`GET /api/v1/inspection/audit-logs/{session_id}`**
    *   **Response**: Sequence of all `audit_logs` entries (e.g., plan repairs, belief updates, entropy changes) for the session.

### 2.6. Expert Configuration 
Manages the abstraction layer's payload (KG, Prior parameters).

*   **`GET /api/v1/configs/{category}`**
    *   **Description**: Fetches the `is_active=TRUE` config (e.g., `knowledge_graph`).
*   **`POST /api/v1/configs/{category}`** (Admin Role Only)
    *   **Description**: Uploads a new JSONB configuration, deprecating the old one.

---

## 3. Implementation Details & Cloud Dynamics

### Scalability and Background Tasks
- **Q-Learning Updates**: Updating the `q_table` offline. Instead of blocking the HTTP response on `POST /interact`, the backend should queue a background job (e.g., via Cloud Tasks or a Celery/Redis worker) to compute Q-values and persist to the database.
- **Data Cleanup**: Supabase currently handles deleting short-lived data (`behavioral_signals`, `episodic_memory`) via `pg_cron` and the `cleanup_old_detailed_data()` function.

### Dealing with Concurrency
- Because state may change rapidly, updating `learning_sessions` or the user's trajectory requires optimistic locking or atomic JSONB updates to avoid race conditions. 

### Latency Optimization (Flutter Mobile)
- To ensure p95 < 3s, the API merges multiple smaller calls. For example, `POST /interact` returns *both* the diagnosis result and the next immediately actionable step defined by the HTN Planner, mitigating round-trip delays over potentially slow mobile networks.

---

## 4. Agentic Step Response (Optional Fields)

Endpoint: `POST /api/v1/orchestrator/step`

The response is backward-compatible. Existing fields remain unchanged. The fields below are optional and appear when agentic reasoning is enabled or when metadata is available.

### Optional reasoning fields
- `reasoning_mode`: `"adaptive" | "agentic"`
- `reasoning_trace`: list of tool-call steps used by the decision process
- `reasoning_content`: short textual rationale for the chosen action
- `reasoning_confidence`: floating-point confidence score in range `[0.0, 1.0]`

### Optional observability fields
- `llm_steps`: number of LLM reasoning iterations in the current decision
- `tool_count`: number of tools called during the current decision
- `fallback_used`: whether agentic flow fell back before finalizing output

### Example
```json
{
    "action": "show_hint",
    "payload": {
        "text": "Hay thu tach bai toan thanh 2 buoc nho.",
        "fallback_used": false
    },
    "dashboard_update": {},
    "reasoning_mode": "agentic",
    "reasoning_trace": [
        {
            "step": 1,
            "tool": "get_academic_beliefs",
            "args": {"session_id": "sess_123"},
            "result_summary": "Top weakness: Quy tac chain rule"
        }
    ],
    "reasoning_content": "Entropy cao va confusion tang nen uu tien hint.",
    "reasoning_confidence": 0.82,
    "llm_steps": 2,
    "tool_count": 1,
    "fallback_used": false,
    "latency_ms": 820
}
```
