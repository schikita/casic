from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DB_URL: str = "sqlite:///./chips.db"

    JWT_SECRET: str = "CHANGE_ME_DEV_SECRET"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRES_MINUTES: int = 60 * 24 * 7  # 7 days

    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    SUPERADMIN_USERNAME: str = "admin"
    SUPERADMIN_PASSWORD: str = "admin"

    def cors_list(self) -> list[str]:
        return [x.strip() for x in self.CORS_ORIGINS.split(",") if x.strip()]


settings = Settings()
