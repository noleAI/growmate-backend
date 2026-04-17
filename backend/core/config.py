from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    supabase_url: str
    supabase_key: str
    supabase_jwt_issuer: str | None = None
    supabase_jwks_url: str | None = None
    supabase_jwt_audience: str | None = "authenticated"
    environment: str = "development"
    debug: bool = False
    quiz_daily_session_limit: int = 5
    quiz_hmac_secret: str | None = None
    quiz_signature_ttl_seconds: int = 300

    # Internal thresholds
    hitl_uncertainty_threshold: float = 0.75
    exhaustion_threshold: float = 0.80
    orchestrator_max_sessions: int = 1024

    # Agentic reasoning
    use_llm_reasoning: bool = False
    agentic_max_steps: int = 5
    agentic_timeout_ms: int = 8000
    agentic_fallback: str = "adaptive"

    # RAG
    embedding_model: str = "text-embedding-004"

    # Reflection
    reflection_interval: int = 5
    reflection_enabled: bool = True

    # Ignore unknown env keys for forward-compatibility (e.g., future GCP/LLM vars).
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache()
def get_settings():
    return Settings()
