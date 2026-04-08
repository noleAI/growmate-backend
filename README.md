# growmate-backend

Backend for the GrowMate app – a plant-growth tracking service built with **FastAPI**, **asyncpg**, and **Supabase**.

---

## Tech Stack

| Layer | Technology |
|---|---|
| API framework | FastAPI 0.115 |
| Async database driver | asyncpg 0.30 (PostgreSQL / Supabase) |
| Auth | Supabase JWT (verified server-side) |
| Validation | Pydantic v2 |
| Testing | pytest + pytest-asyncio |
| Linting | Ruff |
| Container | Docker (multi-stage) |
| Cloud | Google Cloud Run |

---

## Project Structure

```
app/
├── core/               # Config, DB pool, security / JWT utilities
├── models/schemas/     # Pydantic request & response models
├── repositories/       # Raw SQL data-access layer (asyncpg)
├── services/           # Business logic
├── api/
│   ├── deps.py         # FastAPI dependency providers
│   └── v1/
│       ├── router.py   # Aggregates all v1 routes
│       └── endpoints/  # Thin route controllers
└── exceptions/         # Domain exceptions & centralised handlers
db/migrations/          # Raw SQL migration scripts
tests/
├── unit/               # Service-layer tests (mocked repos)
└── api/                # Endpoint tests (mocked services)
```

---

## API Endpoints

All endpoints require a valid Supabase Bearer JWT in the `Authorization` header.

### Auth
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/auth/me` | Upsert user profile from JWT |
| `GET` | `/api/v1/auth/me` | Get current user profile |

### Plants
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/plants` | Add a new plant |
| `GET` | `/api/v1/plants` | List all plants |
| `GET` | `/api/v1/plants/{plant_id}` | Get a single plant |
| `PATCH` | `/api/v1/plants/{plant_id}` | Partially update a plant |
| `DELETE` | `/api/v1/plants/{plant_id}` | Delete a plant |

### Growth Logs
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/plants/{plant_id}/logs` | Add a growth log entry |
| `GET` | `/api/v1/plants/{plant_id}/logs` | List growth logs for a plant |
| `GET` | `/api/v1/plants/{plant_id}/logs/{log_id}` | Get a single log entry |
| `PATCH` | `/api/v1/plants/{plant_id}/logs/{log_id}` | Partially update a log entry |
| `DELETE` | `/api/v1/plants/{plant_id}/logs/{log_id}` | Delete a log entry |

Interactive docs are available at `/docs` and `/redoc` in non-production environments.

---

## Getting Started

### 1. Copy and fill in environment variables

```bash
cp .env.example .env
# Edit .env with your Supabase project credentials
```

### 2. Apply database migrations

Run `db/migrations/001_initial_schema.sql` against your Supabase project database.

### 3a. Run locally (without Docker)

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
```

### 3b. Run with Docker Compose

```bash
docker compose up --build
```

---

## Development

```bash
pip install -r requirements.txt -r requirements-dev.txt

# Run tests
pytest

# Lint
ruff check app/ tests/
```

---

## Authentication Flow

1. Client authenticates with **Supabase Auth** and receives a JWT.
2. Client includes the JWT as a `Bearer` token in every request.
3. The backend verifies the JWT signature using `SUPABASE_JWT_SECRET` and extracts the `sub` (user UUID) claim.
4. No passwords or credentials are ever handled by this service.
