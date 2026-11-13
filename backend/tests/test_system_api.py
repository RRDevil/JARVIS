"""Tests for the System Lifecycle and Shutdown API."""

import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_shutdown_endpoint_returns_success():
    """Verify POST /api/v1/system/shutdown accepts request and triggers background shutdown."""
    with patch("app.api.system._execute_process_shutdown") as mock_shutdown:
        response = client.post("/api/v1/system/shutdown")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "shutting_down"
        assert "JARVIS shutdown sequence initiated" in data["message"]
        # Background task runs
        mock_shutdown.assert_called_once()

