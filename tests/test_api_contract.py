"""API contract tests (directive §15): schemas, status codes, error format."""

from __future__ import annotations

ERROR_FIELDS = {
    "code",
    "message",
    "category",
    "severity",
    "source",
    "recoverable",
    "recommended_action",
    "details",
}


async def test_health_contract(api_client):
    resp = await api_client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    assert body["environment"] == "testing"
    assert body["source_kind"] == "SIMULATED"
    assert body["protocol_version"] == 1
    assert body["database"] == "ok"
    assert "server_time" in body


async def test_nodes_empty_contract(api_client):
    resp = await api_client.get("/api/v1/nodes")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_unknown_node_404_with_error_envelope(api_client):
    resp = await api_client.get("/api/v1/nodes/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert "error" in body
    assert set(ERROR_FIELDS) <= set(body["error"])
    assert body["error"]["code"] == "NOT_FOUND"
    assert body["error"]["category"] == "USER_ERROR"
    assert body["error"]["recoverable"] is True


async def test_unknown_node_telemetry_404(api_client):
    resp = await api_client.get("/api/v1/nodes/does-not-exist/telemetry")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_events_and_faults_empty_contracts(api_client):
    assert (await api_client.get("/api/v1/events")).json() == []
    assert (await api_client.get("/api/v1/faults")).json() == []


async def test_validation_error_422_contract(api_client):
    resp = await api_client.get("/api/v1/events", params={"limit": "not-a-number"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "VALIDATION_FAILED"
    assert body["error"]["category"] == "USER_ERROR"
    assert "errors" in body["error"]["details"]


async def test_unknown_route_404_contract(api_client):
    resp = await api_client.get("/api/v1/nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


async def test_frontend_index_served(api_client):
    resp = await api_client.get("/")
    assert resp.status_code == 200
    assert "MEDIROVER" in resp.text.upper()
    assert 'src="/js/src/main.js"' in resp.text
