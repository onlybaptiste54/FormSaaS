from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///./sillage.db"
    secret_key: str = "dev-secret-change-me"
    cors_origins: str = "http://localhost:3000"
    openai_api_key: str = ""
    openai_model: str = "gpt-5.4-mini"
    openai_timeout_seconds: float = 30.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
