"""Pytest fixtures and configuration."""

import os
from typing import Generator
import pytest
from fastapi.testclient import TestClient

# Set testing environment before importing app
os.environ["ENVIRONMENT"] = "testing"

from app.main import app


@pytest.fixture(scope="session")
def client() -> Generator[TestClient, None, None]:
    """Test client fixture for invoking API endpoints."""
    with TestClient(app) as test_client:
        yield test_client
