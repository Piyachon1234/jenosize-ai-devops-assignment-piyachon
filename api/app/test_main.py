from fastapi.testclient import TestClient
from app.main import app, compute_embedding

client = TestClient(app)

def test_healthz_endpoint():
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.text == "ok"

def test_metrics_endpoint():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "jenie_http_request_total" in response.text

def test_embedding_normalization():
    vec = compute_embedding("How do I reset VPN and MFA")
    assert len(vec) ==64
    norm_sq == sum(i*i for i in vec)
    assert 0.99 <= norm_sq <= 1.01
