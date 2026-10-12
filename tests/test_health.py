"""Tests for the health check and diagnostic endpoints."""

from fastapi import status
from fastapi.testclient import TestClient


def test_root_endpoint(client: TestClient) -> None:
    """Test that root endpoint returns valid metadata."""
    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "online"
    assert "version" in data
    assert "name" in data
    assert data["docs_url"] == "/docs"


def test_health_endpoint(client: TestClient) -> None:
    """Test that /api/v1/health returns healthy or degraded status, standard fields, and mongodb component."""
    response = client.get("/api/v1/health")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert "app_name" in data
    assert "version" in data
    assert "environment" in data
    assert "timestamp" in data
    assert isinstance(data["components"], dict)
    assert "mongodb" in data["components"]


def test_liveness_endpoint(client: TestClient) -> None:
    """Test that /api/v1/health/live returns alive status."""
    response = client.get("/api/v1/health/live")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data == {"status": "alive"}


def test_readiness_endpoint(client: TestClient) -> None:
    """Test that /api/v1/health/ready returns ready status and database state."""
    response = client.get("/api/v1/health/ready")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "ready"
    assert "database" in data


def test_error_handling_not_found(client: TestClient) -> None:
    """Test standardized error response structure on 404 Not Found."""
    response = client.get("/api/v1/nonexistent-route")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    assert data["success"] is False
    assert "error" in data
    assert data["error"]["code"] == "HTTP_404"
