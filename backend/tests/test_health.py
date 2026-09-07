def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Rooman Billing"
    assert "health" in data


def test_health_endpoint(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in {"healthy", "degraded"}
    assert data["project_name"] == "Rooman Billing"
    assert "version" in data
    assert "timestamp" in data
    assert "database" in data
    assert data["database"]["status"] in {"connected", "disconnected"}
    # Overall status must reflect database connectivity
    expected = "healthy" if data["database"]["status"] == "connected" else "degraded"
    assert data["status"] == expected
