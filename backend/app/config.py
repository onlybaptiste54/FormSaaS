from pydantic_settings import BaseSettings, SettingsConfigDict


# Clé de développement : refusée en production par ensure_production_secrets().
DEV_SECRET_KEY = "dev-secret-change-me"
# Longueur minimale exigée en production, soit 32 octets aléatoires en hexadécimal.
MIN_SECRET_LENGTH = 32


class Settings(BaseSettings):
    database_url: str = "sqlite:///./sillage.db"
    # "production" durcit le démarrage : voir ensure_production_secrets().
    environment: str = "development"
    secret_key: str = DEV_SECRET_KEY
    cors_origins: str = "http://localhost:3000"
    openai_api_key: str = ""
    openai_model: str = "gpt-5.4-mini"
    openai_timeout_seconds: float = 90.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()


def is_production() -> bool:
    """Mise en ligne : pas de données de démonstration, et une vraie SECRET_KEY."""
    return settings.environment.strip().lower() == "production"
