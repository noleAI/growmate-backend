from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    supabase_url: str
    supabase_key: str
    supabase_jwt_secret: str
    environment: str = "development"
    debug: bool = False

    # Internal thresholds
    hitl_uncertainty_threshold: float = 0.75
    exhaustion_threshold: float = 0.80

    model_config = SettingsConfigDict(env_file=".env")


@lru_cache()
def get_settings():
    return Settings()
