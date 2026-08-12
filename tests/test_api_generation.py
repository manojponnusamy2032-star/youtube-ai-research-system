import pytest
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient
from src.api.app import app

client = TestClient(app)


def test_list_content_empty():
    resp = client.get("/content")
    assert resp.status_code == 200
    body = resp.json()
    assert "total" in body
    assert isinstance(body["items"], list)


def test_get_content_not_found():
    resp = client.get("/content/9999999")
    assert resp.status_code == 404


def test_generated_endpoints_empty():
    endpoints = [
        "/generated/scripts",
        "/generated/titles",
        "/generated/hooks",
        "/generated/thumbnails",
        "/generated/seo",
    ]
    for ep in endpoints:
        r = client.get(ep)
        assert r.status_code == 200
        body = r.json()
        assert "total" in body
        assert isinstance(body["items"], list)


def test_get_workflow_logs_not_found():
    resp = client.get("/research/nonexistent-workflow/logs")
    assert resp.status_code == 404
