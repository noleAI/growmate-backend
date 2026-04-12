from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import config, inspection, orchestrator, session
from api.ws import behavior
from core.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize connections (Supabase, Redis if applicable)
    print(f"Starting GrowMate Backend in {settings.environment} mode.")
    yield
    # Shutdown: Clean up connections
    print("Shutting down GrowMate Backend.")


app = FastAPI(
    title="GrowMate API",
    description="Multi-Agent AI Tutor Backend",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API Routers
app.include_router(session.router, prefix="/api/v1/sessions", tags=["Session"])
app.include_router(
    session.router, prefix="/api/v1/academic", tags=["Academic"]
)  # Merged based on interact route
app.include_router(inspection.router, prefix="/api/v1/inspection", tags=["Inspection"])
app.include_router(config.router, prefix="/api/v1/configs", tags=["Config"])
app.include_router(
    orchestrator.router,
    prefix="/api/v1/orchestrator",
    tags=["Orchestrator"],
)

# WebSockets
app.include_router(behavior.router, prefix="/ws/v1/behavior", tags=["WebSockets"])


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
