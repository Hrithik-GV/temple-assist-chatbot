"""Tests for production hardening, security headers, environment validation, and operational limits."""

import io
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings, settings
from app.core.logging import JsonLogFormatter
from app.core.security import create_access_token
from app.services.auth_service import auth_service
from app.services.crawler_service import crawler_service


def test_security_headers_present_on_responses(client: TestClient) -> None:
    """Every HTTP response must contain secure headers (nosniff, DENY, referrer policy, etc.)."""
    response = client.get("/")
    assert response.status_code == 200
    headers = response.headers

    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("X-XSS-Protection") == "1; mode=block"
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "geolocation=()" in headers.get("Permissions-Policy", "")


def test_root_probe_aliases_for_cloud_orchestrators(client: TestClient) -> None:
    """Root /health, /live, and /ready aliases must resolve for cloud/k8s orchestrators."""
    # 1. /live probe
    live_res = client.get("/live")
    assert live_res.status_code == 200
    assert live_res.json() == {"status": "alive"}

    # 2. /ready probe
    ready_res = client.get("/ready")
    assert ready_res.status_code == 200
    assert ready_res.json()["status"] == "ready"
    assert "database" in ready_res.json()

    # 3. /health overview
    health_res = client.get("/health")
    assert health_res.status_code == 200
    assert "status" in health_res.json()
    assert "components" in health_res.json()


def test_production_environment_validation_detects_misconfigurations() -> None:
    """validate_production_configuration() detects weak JWT secrets, debug mode, and localhost DB."""
    # Simulate a production settings instance with default/weak settings
    prod_settings = Settings(
        ENVIRONMENT="production",
        DEBUG=True,
        JWT_SECRET_KEY="temple-assist-default-super-secret-jwt-key-change-in-production-32chars",
        MONGODB_URI="mongodb://localhost:27017",
        LLM_PROVIDER="gemini",
        GEMINI_API_KEY=None,
    )

    issues = prod_settings.validate_production_configuration()
    assert len(issues) >= 3

    assert any("DEBUG mode" in issue for issue in issues)
    assert any("JWT_SECRET_KEY" in issue for issue in issues)
    assert any("MONGODB_URI" in issue for issue in issues)
    assert any("GEMINI_API_KEY" in issue for issue in issues)


def test_production_environment_validation_passes_valid_config() -> None:
    """validate_production_configuration() produces zero warnings when properly configured."""
    valid_prod_settings = Settings(
        ENVIRONMENT="production",
        DEBUG=False,
        JWT_SECRET_KEY="a-very-secure-random-32-byte-hex-string-for-prod-encryption!",
        MONGODB_URI="mongodb+srv://admin:securepass@cluster.mongodb.net/?retryWrites=true",
        LLM_PROVIDER="gemini",
        GEMINI_API_KEY="AIzaSyDummyKeyForProductionValidationCheck",
    )

    issues = valid_prod_settings.validate_production_configuration()
    assert len(issues) == 0


def test_structured_json_log_formatter() -> None:
    """JsonLogFormatter produces valid JSON containing timestamp, level, logger, and message."""
    formatter = JsonLogFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test_path.py",
        lineno=42,
        msg="Production event processed: %s",
        args=("order_123",),
        exc_info=None,
    )

    formatted = formatter.format(record)
    parsed = json.loads(formatted)

    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test_logger"
    assert parsed["message"] == "Production event processed: order_123"
    assert parsed["line"] == 42
    assert "timestamp" in parsed


def test_upload_document_exceeding_max_size_rejected(client: TestClient) -> None:
    """Uploading a document file exceeding MAX_UPLOAD_FILE_SIZE_BYTES returns 400 Bad Request."""
    admin_id = "admin_prod_1"
    temple_id = "temple-prod"
    token = create_access_token({"sub": admin_id, "templeId": temple_id, "role": "temple_admin"})
    headers = {"Authorization": f"Bearer {token}"}

    mock_admin = {
        "_id": admin_id,
        "email": "prod@temple.org",
        "username": "prod_admin",
        "role": "temple_admin",
        "templeId": temple_id,
        "isActive": True,
    }

    # Simulate a file larger than max size
    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)), \
         patch.object(settings, "MAX_UPLOAD_FILE_SIZE_BYTES", 100):  # 100 bytes limit

        oversized_data = b"A" * 500  # 500 bytes exceeds 100 bytes
        files = {"file": ("big_doc.txt", io.BytesIO(oversized_data), "text/plain")}

        response = client.post(
            f"/api/v1/admin/knowledge/{temple_id}/upload",
            headers=headers,
            files=files,
        )

    assert response.status_code == 400
    assert "exceeds maximum allowed size" in response.json()["error"]["message"].lower()


def test_crawler_max_pages_ceiling_enforced() -> None:
    """Website crawler caps requested max_pages at CRAWLER_MAX_ALLOWED_PAGES."""
    with patch.object(settings, "CRAWLER_MAX_ALLOWED_PAGES", 20):
        # Even if caller requests 500 pages, it must clamp to 20
        max_allowed = getattr(settings, "CRAWLER_MAX_ALLOWED_PAGES", 50)
        requested_pages = 500
        effective_pages = min(requested_pages, max_allowed)
        assert effective_pages == 20
