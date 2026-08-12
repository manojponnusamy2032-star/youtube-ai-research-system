from fastapi.testclient import TestClient

from src.api.app import app


client = TestClient(app)


def test_health_endpoint():
    resp = client.get("/health")
    assert resp.status_code == 200


def test_metrics_endpoint():
    resp = client.get("/metrics")
    assert resp.status_code == 200


def test_research_endpoint_exists():
    resp = client.get("/research")
    assert resp.status_code == 200
    # Ensure a JSON body is returned (list or object)
    try:
        body = resp.json()
    except Exception:
        body = None
    assert body is not None
