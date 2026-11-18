from fastapi.testclient import TestClient

from app.main import app


def test_health_without_external_services():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_method_error_keeps_allow_header():
    with TestClient(app) as client:
        response = client.post("/health")
    assert response.status_code == 405
    assert "GET" in response.headers["allow"]
    assert response.json()["error"]["request_id"] == response.headers["x-request-id"]
