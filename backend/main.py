from dotenv import load_dotenv
load_dotenv()  # Populate os.environ from .env BEFORE any service initialization

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import (
    chatbot,
    config,
    formulas,
    inspection,
    leaderboard,
    lives,
    onboarding,
    orchestrator,
    quota,
    quiz,
    session,
    session_recovery,
    user_profile,
)
from api.routes.orchestrator_runtime import set_shared_data_packages
from api.ws import behavior, dashboard
from core.config import get_settings
from core.data_packages import DataPackagesService

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize connections (Supabase, Redis if applicable)
    print(f"Starting GrowMate Backend in {settings.environment} mode.")
    data_packages_service = DataPackagesService.from_default_paths()
    if not data_packages_service.load():
        raise RuntimeError(
            "Data package validation failed at startup. "
            "Please fix Package 2/3/4 files before launching the API."
        )
    app.state.data_packages_service = data_packages_service
    set_shared_data_packages(data_packages_service)
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
app.include_router(quota.router, prefix="/api/v1", tags=["Quota"])
app.include_router(quiz.router, prefix="/api/v1", tags=["Quiz"])
app.include_router(session_recovery.router, prefix="/api/v1", tags=["SessionRecovery"])
app.include_router(leaderboard.router, prefix="/api/v1", tags=["Leaderboard"])
app.include_router(lives.router, prefix="/api/v1", tags=["Lives"])
app.include_router(formulas.router, prefix="/api/v1", tags=["Formulas"])
app.include_router(onboarding.router, prefix="/api/v1/onboarding", tags=["Onboarding"])
app.include_router(user_profile.router, prefix="/api/v1", tags=["UserProfile"])
app.include_router(chatbot.router, prefix="/api/v1/chatbot", tags=["Chatbot"])
app.include_router(
    orchestrator.router,
    prefix="/api/v1/orchestrator",
    tags=["Orchestrator"],
)

# WebSockets
app.include_router(behavior.router, prefix="/ws/v1/behavior", tags=["WebSockets"])
app.include_router(dashboard.router, prefix="/ws/v1/dashboard", tags=["WebSockets"])


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
