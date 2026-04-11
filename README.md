# GrowMate Backend

GrowMate is a smart and friendly study partner, built as a Multi-Agent AI system. This repository contains the backend service, which powers the agentic workflows, real-time behavioral telemetry, and integration with Supabase. 

*Built for GDGoC Hackathon Vietnam 2026 by Team noleAI.*

## 🧠 Architecture Overview

GrowMate replaces unpredictable LLM reasoning with verifiable algorithmic foundations. The core functionality is driven by **4 Core Agents**:
1. **Academic Agent**: Uses Bayesian Hypothesis Tracking & HTN Planning (Hierarchical Task Networks) with self-repair to diagnose root-cause knowledge gaps.
2. **Empathy Agent**: Streams fast telemetry via WebSockets and uses Particle Filter State Estimation to track user exhaustion or confusion. 
3. **Strategy Agent**: Uses Reinforcement Learning (Q-Learning) and long-term memory to adapt personalized learning paths.
4. **Orchestrator**: Acts as a state machine monitoring uncertainties and initiating Human-in-the-Loop (HITL) triggers when confidence drops.

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
   SUPABASE_JWT_SECRET=your-jwt-secret
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
├── api/
│   ├── routes/         # RESTful endpoints (Sessions, Configurations, Inspection)
│   └── ws/             # WebSockets for high-frequency telemetry tracking 
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
- `/belief-state`: Internal probabilities of the Bayesian Tracker.
- `/particle-state`: Current dispersion variables for the Empathy agent.
- `/q-values`: Explored states in the Q-Learning environment.
- `/audit-logs`: Immutable ledger of systemic decisions.

For further implementation details regarding endpoints, please check the [API.md](./API.md) documentation in the repository.
