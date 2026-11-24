from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.health import get_health_status


def test_get_health_status() -> None:
    assert get_health_status() == "ok"


def test_health_endpoint() -> None:
    client = TestClient(create_app(Settings()))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
