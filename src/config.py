from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings."""

    # Bot settings
    bot_token: str = Field(..., description="Telegram Bot Token")
    log_level: str = Field("INFO", description="Level of logging")

    # API settings
    api_base_url: str = Field(
        default="http://localhost:8000",
        description="Base URL for Task Manager API"
    )

    # Redis settings
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL"
    )

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()