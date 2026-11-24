import pytest


@pytest.fixture(autouse=True)
def clear_app_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "APP_NAME",
        "ENVIRONMENT",
        "LOG_LEVEL",
        "APP_DATABASE_URL",
        "APP_TOKEN_SECRET",
        "APP_SMTP_HOST",
        "APP_SMTP_PORT",
        "APP_SMTP_USERNAME",
        "APP_SMTP_PASSWORD",
        "APP_SMTP_FROM",
        "APP_SMS_API_URL",
        "APP_SMS_API_TOKEN",
        "APP_GOOGLE_CLIENT_IDS",
    ):
        monkeypatch.delenv(name, raising=False)
