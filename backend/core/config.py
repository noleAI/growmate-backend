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
    quiz_signature_resume_grace_seconds: int = 1800

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

    # Runtime alerting
    runtime_alert_webhook_url: str | None = None
    runtime_alert_min_interval_seconds: int = 300
    runtime_alert_signature_expired_threshold: int = 20
    runtime_alert_result_fetch_failure_threshold: int = 10
    runtime_alert_resume_grace_usage_threshold: int = 15

    # Ignore unknown env keys for forward-compatibility (e.g., future GCP/LLM vars).
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache()
def get_settings():
    return Settings()
