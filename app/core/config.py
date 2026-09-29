from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "EVE Healthcare Backend"
    environment: str = "development"
    database_url: str = "sqlite:///./eve_healthcare.db"
    secret_key: str = "change-this-in-production-key-32-chars-min"
    access_token_expire_minutes: int = 60
    redis_url: str | None = "redis://localhost:6379/0"
    celery_broker_url: str | None = "redis://localhost:6379/1"
    celery_result_backend: str | None = "redis://localhost:6379/2"
    rate_limit: str = "100/minute"
    webhook_max_retries: int = 3

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


settings = Settings()
