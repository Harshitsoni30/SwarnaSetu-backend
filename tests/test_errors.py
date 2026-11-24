from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.errors import sanitize_validation_errors
from app.main import create_app


def test_unknown_route_uses_error_format() -> None:
    client = TestClient(create_app(Settings()))

    response = client.get("/missing")

    assert response.status_code == 404
    assert response.json() == {
        "code": "http_error",
        "message": "Not Found",
        "details": {},
    }


def test_validation_error_uses_error_format() -> None:
    application = create_app(Settings())

    @application.get("/echo")
    def echo(name: str) -> dict[str, str]:
        return {"name": name}

    client = TestClient(application)
    response = client.get("/echo")

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["message"] == "Request validation failed"
    assert body["details"]["errors"]


def test_unhandled_error_hides_exception_detail() -> None:
    application = create_app(Settings())

    @application.get("/boom")
    def boom() -> dict[str, str]:
        raise RuntimeError("secret detail")

    client = TestClient(application, raise_server_exceptions=False)
    response = client.get("/boom")

    assert response.status_code == 500
    assert response.json() == {
        "code": "internal_error",
        "message": "An unexpected error occurred.",
        "details": {},
    }
    assert "secret detail" not in response.text


def test_sanitize_validation_errors_drops_unsafe_fields() -> None:
    sanitized = sanitize_validation_errors(
        [
            "skip-me",
            {
                "loc": ("body", "name"),
                "msg": "Field required",
                "type": "missing",
                "ctx": {"error": ValueError("hidden")},
            },
            {"loc": "name", "msg": "bad", "type": "value_error"},
        ]
    )

    assert sanitized == [
        {"loc": ["body", "name"], "msg": "Field required", "type": "missing"},
        {"loc": [], "msg": "bad", "type": "value_error"},
    ]
