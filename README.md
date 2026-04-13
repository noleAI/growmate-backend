# GrowMate Backend

GrowMate is a smart and friendly study partner, built as a Multi-Agent AI system. This repository contains the backend service, which powers the agentic workflows, real-time behavioral telemetry, and integration with Supabase. 

*Built for GDGoC Hackathon Vietnam 2026 by Team noleAI.*

## 🧠 Architecture Overview

GrowMate replaces unpredictable LLM reasoning with verifiable algorithmic foundations. The core functionality is driven by **4 Core Agents**:
1. **Academic Agent**: Uses Bayesian Hypothesis Tracking & HTN Planning (Hierarchical Task Networks) with self-repair to diagnose root-cause knowledge gaps.
2. **Empathy Agent**: Streams fast telemetry via WebSockets and uses Particle Filter State Estimation to track user exhaustion or confusion. 
3. **Strategy Agent**: Uses Reinforcement Learning (Q-Learning) and long-term memory to adapt personalized learning paths.
4. **Orchestrator**: Aggregates agent state, applies deterministic utility policy, monitors uncertainty, and triggers Human-in-the-Loop (HITL) escalation when confidence drops.

The orchestration layer is now split into modular components under `backend/orchestrator/`:
- `aggregator.py`: builds a normalized state embedding from academic/empathy/memory signals.
- `policy.py`: deterministic utility scoring and action distribution.
- `monitoring.py`: weighted uncertainty calculation and HITL threshold check.
- `engine.py`: composes the above into one decision output contract.

## ⚙️ Tech Stack

- **Framework**: `FastAPI` (Python 3.11+)
- **Package Manager**: `uv`
- **Database/Auth**: `Supabase` (PostgreSQL + RLS Auth)
- **Deployment**: Configured for Serverless `Cloud Run` (Scale-to-Zero)
- **Linting & Formatting**: `Ruff`

## 🚀 Getting Started

### 1. Prerequisites
- [uv](https://github.com/astral-sh/uv) (Extremely fast Python package installer and resolver)
- Supabase Project (PostgreSQL instance)

### 2. Local Setup
1. Clone the repository and initialize the virtual environment using `uv`:
   ```bash
   uv venv .venv
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   uv pip install -r backend/requirements.txt
   ```
3. Set up your environment variables by copying the example file:
   ```bash
   cp backend/.env.example backend/.env
   ```
4. Fill in the `.env` file with your Supabase credentials:
   ```env
   SUPABASE_URL=https://your-project.supabase.co
   SUPABASE_KEY=your-anon-key
   SUPABASE_JWT_ISSUER=https://your-project.supabase.co/auth/v1
   SUPABASE_JWKS_URL=https://your-project.supabase.co/auth/v1/.well-known/jwks.json
   SUPABASE_JWT_AUDIENCE=authenticated
   ENVIRONMENT=development
   ```

### 3. Run the Development Server
   ```bash
   cd backend
   uvicorn main:app --reload
   ```
   The interactive API documentation will be available at `http://localhost:8000/docs`.

## 🧪 Testing

We use `pytest` for all unit and integration testing. Ensure to run pytest through `uv` from within the `backend` folder where the virtual environment and configurations (`pyproject.toml`) live.

```bash
cd backend
uv run pytest tests/
```

Or run from repository root:

```bash
uv run pytest backend/tests/
```

This testing suite ensures that internal agent algorithms like the Bayesian Hypothesis Tracker remain strictly bounded, dynamically adapt to error traces, and converge logically.

## 📦 Project Structure

```text
backend/
├── agents/             # Logic for Core Agents
│   ├── base.py         # Interfaces (IAgent, AgentInput, AgentOutput, SessionState)
│   ├── orchestrator.py # AgenticOrchestrator pipeline loop
│   ├── academic_agent/ # Bayesian Tracker & HTN Planner
│   ├── empathy_agent/  # Particle Filter
│   └── strategy_agent/ # Q-Learning
├── orchestrator/       # Modular orchestrator components (aggregator/policy/monitoring/engine)
├── api/
│   ├── routes/         # REST endpoints (sessions, orchestrator, configs, inspection)
│   └── ws/             # WebSockets (behavior + dashboard streams)
├── configs/            # YAML Config files for agent hyperparameters
├── core/               # App configuration, LLM service, State Manager, Payload Formatter
├── models/             # Pydantic schemas for Request/Response validation
├── tests/              # Pytest unit and integration tests
├── Dockerfile          # Production Docker image (Multi-stage)
├── requirements.txt    # Dependency definitions
└── main.py             # FastAPI entrypoint
```

## 🔍 API & Inspection Dashboard

GrowMate prioritizes extreme **transparency** and **auditability**. The API features dedicated `/api/v1/inspection` endpoints, which emit raw algorithmic states for external dashboards:
- `/belief-state/{session_id}`: Internal probabilities of the Bayesian Tracker.
- `/particle-state/{session_id}`: Current dispersion variables for the Empathy agent.
- `/q-values`: Explored states in the Q-Learning environment.
- `/audit-logs/{session_id}`: Immutable ledger of systemic decisions.

Additional orchestration endpoint:
- `POST /api/v1/orchestrator/step`: Runs one orchestrator decision step using session state + behavior signals.

WebSocket channels:
- `/ws/v1/behavior/{session_id}`: behavior telemetry ingestion.
- `/ws/v1/dashboard/stream`: subscribe to all dashboard updates.
- `/ws/v1/dashboard/stream/{session_id}`: subscribe to one session dashboard stream.

For further implementation details regarding endpoints, please check the [API.md](./docs/API.md) documentation in the repository.
