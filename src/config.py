from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot_token: str
    log_level: str = "INFO"

    class Config:
        env_file = ".env"


settings = Settings()