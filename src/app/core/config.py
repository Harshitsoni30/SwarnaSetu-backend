from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.logging import ALLOWED_LOG_LEVELS


class Settings(BaseSettings):
    app_name: str = "api"
    environment: str = "local"
    log_level: str = "INFO"

    database_url: str = Field(default="", validation_alias="APP_DATABASE_URL")
    token_secret: str = Field(default="", validation_alias="APP_TOKEN_SECRET")
    smtp_host: str = Field(default="", validation_alias="APP_SMTP_HOST")
    smtp_port: int = Field(default=587, validation_alias="APP_SMTP_PORT")
    smtp_username: str = Field(default="", validation_alias="APP_SMTP_USERNAME")
    smtp_password: str = Field(default="", validation_alias="APP_SMTP_PASSWORD")
    smtp_from: str = Field(default="", validation_alias="APP_SMTP_FROM")
    sms_api_url: str = Field(default="", validation_alias="APP_SMS_API_URL")
    sms_api_token: str = Field(default="", validation_alias="APP_SMS_API_TOKEN")
    google_client_ids: str = Field(default="", validation_alias="APP_GOOGLE_CLIENT_IDS")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator("app_name", "environment")
    @classmethod
    def must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be blank")
        return stripped

    @field_validator("log_level")
    @classmethod
    def must_be_known_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in ALLOWED_LOG_LEVELS:
            raise ValueError(f"Unsupported log level: {value}")
        return normalized

    def google_audiences(self) -> list[str]:
        return [item.strip() for item in self.google_client_ids.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
