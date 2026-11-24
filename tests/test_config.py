import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_defaults() -> None:
    settings = Settings()

    assert settings.app_name == "api"
    assert settings.environment == "local"
    assert settings.log_level == "INFO"


def test_settings_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "demo-api")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("LOG_LEVEL", "debug")
    monkeypatch.setenv("UNRELATED_SETTING", "ignored")

    settings = Settings()

    assert settings.app_name == "demo-api"
    assert settings.environment == "test"
    assert settings.log_level == "DEBUG"


def test_settings_reject_blank_name() -> None:
    with pytest.raises(ValidationError):
        Settings(app_name="  ")


def test_settings_reject_unknown_log_level() -> None:
    with pytest.raises(ValidationError):
        Settings(log_level="verbose")
