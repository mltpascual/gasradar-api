"""
GasRadar API Configuration
Loads settings from environment variables with sensible defaults for local development.
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/gasradar"

    # Admin
    ADMIN_API_KEY: str = "dev_admin_key_change_me"

    # CORS
    CORS_ORIGINS: str = "*"

    # Rate Limiting
    RATE_LIMIT_STORAGE: str = "memory"  # "memory" for MVP, "redis" later

    # Logging
    LOG_LEVEL: str = "INFO"

    # App
    APP_NAME: str = "GasRadar API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
