"""Tests for health check and diagnostics API endpoints."""


def test_root_endpoint(client):
    """Test that root endpoint returns service online banner."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "JARVIS Assistant Core Online" in data["message"]
    assert "version" in data


def test_system_info_endpoint(client):
    """Test the /api/info metadata endpoint."""
    response = client.get("/api/info")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "JARVIS Desktop Assistant"
    assert data["status"] == "online"
    assert data["api_prefix"] == "/api/v1"


def test_system_health_endpoint(client):
    """Test the /api/health endpoint structure and diagnostics."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()

    # Core metadata
    assert data["status"] == "operational"
    assert data["service"] == "JARVIS Assistant Core"
    assert data["uptime_seconds"] >= 0.0
    assert "timestamp" in data

    # System telemetry
    assert "os" in data["system"]
    assert "python" in data["system"]
    assert data["system"]["host"] == "127.0.0.1"

    # Subsystems verification
    subsystems = data["subsystems"]
    assert "database" in subsystems
    assert subsystems["database"]["status"] in ("operational", "healthy")
    assert "security" in subsystems
    assert subsystems["security"]["status"] == "enforced"
    assert "automation" in subsystems
    assert "ai_provider" in subsystems

    # Capabilities
    capabilities = data["capabilities"]
    assert "diagnostics_monitoring" in capabilities
    assert "sqlite_persistence" in capabilities

