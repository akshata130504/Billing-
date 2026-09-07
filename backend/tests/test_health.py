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
    assert data["status"] == "healthy"
    assert data["project_name"] == "Rooman Billing"
    assert "version" in data
    assert "timestamp" in data
    assert "database" in data
    assert "status" in data["database"]
