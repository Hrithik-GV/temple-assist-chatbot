"""Tests for Admin Authentication, Password Hashing, JWT Tokens, and Temple-Level Authorization Isolation."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.core.auth import RequireTempleAccess, get_current_admin
from app.core.config import settings
from app.core.errors import BadRequestException, ConflictException, ForbiddenException, UnauthorizedException
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.models.admin import AdminRole
from app.models.auth import AdminCreateRequest
from app.services.auth_service import AuthService, auth_service
from app.services.database_service import database_service


# ==============================================================================
# 1. Cryptography & Password Hashing Tests (Requirements 1 & 2)
# ==============================================================================


def test_hash_password_produces_bcrypt_hash() -> None:
    """Password hashing generates salted bcrypt strings that differ for each execution."""
    pwd = "TempleSecurePassword2026!"
    hash1 = hash_password(pwd)
    hash2 = hash_password(pwd)

    assert hash1.startswith("$2b$")
    assert hash2.startswith("$2b$")
    # Due to random salt, the two hashes must differ
    assert hash1 != hash2


def test_verify_password_matches_correct_password() -> None:
    """verify_password returns True for matching password and False for incorrect ones."""
    pwd = "SacredDevotion108#"
    hashed = hash_password(pwd)

    assert verify_password(pwd, hashed) is True
    assert verify_password("WrongPassword123", hashed) is False
    assert verify_password("", hashed) is False
    assert verify_password(pwd, "") is False


# ==============================================================================
# 2. JWT Generation & Validation Tests (Requirement 3)
# ==============================================================================


def test_create_and_decode_access_token() -> None:
    """JWT tokens encode claims properly and decode correctly before expiration."""
    payload = {
        "sub": "admin_tirupati_01",
        "username": "tirupati_admin",
        "role": AdminRole.TEMPLE_ADMIN.value,
        "templeId": "temple-tirupati",
    }

    token = create_access_token(data=payload, expires_delta=timedelta(minutes=30))
    decoded = decode_access_token(token)

    assert decoded["sub"] == "admin_tirupati_01"
    assert decoded["username"] == "tirupati_admin"
    assert decoded["role"] == "temple_admin"
    assert decoded["templeId"] == "temple-tirupati"
    assert "exp" in decoded


def test_expired_token_raises_unauthorized() -> None:
    """Expired JWT tokens raise UnauthorizedException."""
    payload = {"sub": "admin_expired"}
    expired_token = create_access_token(data=payload, expires_delta=timedelta(minutes=-10))

    with pytest.raises(UnauthorizedException) as exc_info:
        decode_access_token(expired_token)

    assert "expired" in str(exc_info.value).lower()


def test_tampered_token_signature_raises_unauthorized() -> None:
    """Tokens signed with a different key or tampered with raise UnauthorizedException."""
    payload = {"sub": "admin_hacked"}
    import jwt
    fake_token = jwt.encode(payload, "wrong_secret_key_123456789012345678", algorithm="HS256")

    with pytest.raises(UnauthorizedException) as exc_info:
        decode_access_token(fake_token)

    assert "invalid" in str(exc_info.value).lower() or "failed" in str(exc_info.value).lower()


# ==============================================================================
# 3. Admin Account Lifecycle & Temple Tenancy (Requirements 5 & 8)
# ==============================================================================


@pytest.mark.anyio
async def test_create_admin_hashes_password_and_assigns_temple() -> None:
    """Creating an admin saves hashed password (never plain) and verifies temple."""
    service = AuthService()

    mock_admins_col = MagicMock()
    mock_admins_col.find_one = AsyncMock(return_value=None)  # No duplicate
    mock_admins_col.insert_one = AsyncMock()

    mock_temples_col = MagicMock()
    # Temple exists
    mock_temples_col.find_one = AsyncMock(return_value={"_id": "somnath-01", "name": "Somnath Temple"})

    with patch.object(AuthService, "admins_collection", new=mock_admins_col), \
         patch.object(AuthService, "temples_collection", new=mock_temples_col):

        req = AdminCreateRequest(
            email="manager@somnath.org",
            username="somnath_mgr",
            password="SecurePassword2026!",
            fullName="Somnath Manager",
            templeId="somnath-01",
            role=AdminRole.TEMPLE_ADMIN,
        )

        admin = await service.create_admin(req)

        assert admin["username"] == "somnath_mgr"
        assert admin["email"] == "manager@somnath.org"
        assert admin["templeId"] == "somnath-01"
        assert admin["role"] == "temple_admin"
        assert admin["isActive"] is True
        # Plaintext password must NEVER be in stored document
        assert "SecurePassword2026!" not in str(admin)
        assert admin["passwordHash"].startswith("$2b$")
        mock_admins_col.insert_one.assert_called_once()


@pytest.mark.anyio
async def test_create_temple_admin_without_temple_id_fails() -> None:
    """Creating a temple_admin without templeId raises BadRequestException."""
    service = AuthService()
    mock_admins_col = MagicMock()
    mock_admins_col.find_one = AsyncMock(return_value=None)

    with patch.object(AuthService, "admins_collection", new=mock_admins_col):
        req = AdminCreateRequest(
            email="orphan@temple.org",
            username="orphan_admin",
            password="SecurePassword2026!",
            templeId=None,
            role=AdminRole.TEMPLE_ADMIN,
        )

        with pytest.raises(BadRequestException) as exc_info:
            await service.create_admin(req)

        assert "templeId is required" in str(exc_info.value)


@pytest.mark.anyio
async def test_duplicate_email_or_username_raises_conflict() -> None:
    """Registering with an existing email raises ConflictException."""
    service = AuthService()
    mock_admins_col = MagicMock()
    # Simulate existing email
    mock_admins_col.find_one = AsyncMock(return_value={"_id": "admin_1", "email": "exists@temple.org"})

    with patch.object(AuthService, "admins_collection", new=mock_admins_col):
        req = AdminCreateRequest(
            email="exists@temple.org",
            username="new_user",
            password="SecurePassword2026!",
            templeId="temple-01",
            role=AdminRole.TEMPLE_ADMIN,
        )

        with pytest.raises(ConflictException) as exc_info:
            await service.create_admin(req)

        assert "already exists" in str(exc_info.value)


# ==============================================================================
# 4. Authentication Login Endpoint Tests (Requirements 1, 3, 4)
# ==============================================================================


def test_admin_login_success(client: TestClient) -> None:
    """POST /api/v1/admin/auth/login validates credentials and returns JWT bearer token."""
    plain_pwd = "MySecretPassword123!"
    hashed_pwd = hash_password(plain_pwd)

    mock_admin_doc = {
        "_id": "admin_tirupati_99",
        "email": "priest@tirupati.org",
        "username": "tirupati_priest",
        "fullName": "Head Priest",
        "templeId": "tirupati-01",
        "role": "temple_admin",
        "isActive": True,
        "passwordHash": hashed_pwd,
        "createdAt": datetime.now(timezone.utc),
    }

    with patch.object(auth_service, "get_admin_by_username_or_email", new=AsyncMock(return_value=mock_admin_doc)):
        response = client.post(
            "/api/v1/admin/auth/login",
            json={"username": "tirupati_priest", "password": plain_pwd},
        )

    assert response.status_code == 200
    data = response.json()
    assert "accessToken" in data
    assert data["tokenType"] == "bearer"
    assert data["expiresIn"] > 0
    assert data["admin"]["username"] == "tirupati_priest"
    assert data["admin"]["templeId"] == "tirupati-01"


def test_admin_login_invalid_password_returns_401(client: TestClient) -> None:
    """POST /api/v1/admin/auth/login with wrong password returns 401 Unauthorized."""
    mock_admin_doc = {
        "_id": "admin_tirupati_99",
        "email": "priest@tirupati.org",
        "username": "tirupati_priest",
        "passwordHash": hash_password("CorrectPassword"),
        "isActive": True,
    }

    with patch.object(auth_service, "get_admin_by_username_or_email", new=AsyncMock(return_value=mock_admin_doc)):
        response = client.post(
            "/api/v1/admin/auth/login",
            json={"username": "tirupati_priest", "password": "WrongPassword!"},
        )

    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "UNAUTHORIZED"


def test_admin_me_endpoint_with_valid_bearer_token(client: TestClient) -> None:
    """GET /api/v1/admin/auth/me returns admin profile when valid JWT is supplied."""
    admin_id = "admin_auth_user_123"
    token = create_access_token({"sub": admin_id, "username": "admin_user", "templeId": "somnath-01"})

    mock_admin = {
        "_id": admin_id,
        "email": "admin@somnath.org",
        "username": "admin_user",
        "fullName": "Somnath Admin",
        "templeId": "somnath-01",
        "role": "temple_admin",
        "isActive": True,
    }

    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)):
        response = client.get(
            "/api/v1/admin/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == admin_id
    assert data["username"] == "admin_user"
    assert data["templeId"] == "somnath-01"


def test_admin_endpoint_missing_token_returns_401(client: TestClient) -> None:
    """Accessing protected admin endpoints without Authorization header returns 401."""
    response = client.get("/api/v1/admin/auth/me")
    assert response.status_code == 401
    data = response.json()
    assert data["success"] is False
    assert "token is missing" in data["error"]["message"].lower()


# ==============================================================================
# 5. Temple-Level Authorization & Cross-Temple Isolation Tests (Req 6 & 7)
# ==============================================================================


def test_temple_admin_can_access_own_temple_details(client: TestClient) -> None:
    """Temple admin can access details for their own assigned temple."""
    admin_id = "admin_alpha_1"
    temple_alpha = "temple-alpha"
    token = create_access_token({"sub": admin_id, "role": "temple_admin", "templeId": temple_alpha})

    mock_admin = {
        "_id": admin_id,
        "email": "alpha@temple.org",
        "username": "alpha_admin",
        "role": "temple_admin",
        "templeId": temple_alpha,
        "isActive": True,
    }

    mock_temple = {
        "_id": "t_alpha_id",
        "name": "Temple Alpha",
        "slug": temple_alpha,
        "isActive": True,
    }

    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)), \
         patch.object(database_service, "get_temple_by_id", new=AsyncMock(return_value=mock_temple)):

        response = client.get(
            f"/api/v1/admin/temples/{temple_alpha}",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json()["name"] == "Temple Alpha"


def test_temple_admin_CANNOT_access_other_temple_data(client: TestClient) -> None:
    """CRITICAL: Temple admin assigned to Temple A CANNOT access Temple B (403 Forbidden)."""
    admin_id = "admin_alpha_1"
    temple_alpha = "temple-alpha"
    temple_beta = "temple-beta"

    token = create_access_token({"sub": admin_id, "role": "temple_admin", "templeId": temple_alpha})

    mock_admin = {
        "_id": admin_id,
        "email": "alpha@temple.org",
        "username": "alpha_admin",
        "role": "temple_admin",
        "templeId": temple_alpha,
        "isActive": True,
    }

    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)):
        # Attempting to access Temple Beta's data
        response = client.get(
            f"/api/v1/admin/temples/{temple_beta}",
            headers={"Authorization": f"Bearer {token}"},
        )

    # Must be 403 Forbidden
    assert response.status_code == 403
    data = response.json()
    assert data["success"] is False
    assert data["error"]["code"] == "FORBIDDEN"
    assert "cannot access temple 'temple-beta'" in data["error"]["message"].lower()


def test_temple_admin_CANNOT_access_other_temple_knowledge_documents(client: TestClient) -> None:
    """CRITICAL: Temple admin assigned to Temple A CANNOT view or manage Temple B's knowledge documents."""
    admin_id = "admin_alpha_1"
    temple_alpha = "temple-alpha"
    temple_beta = "temple-beta"

    token = create_access_token({"sub": admin_id, "role": "temple_admin", "templeId": temple_alpha})

    mock_admin = {
        "_id": admin_id,
        "email": "alpha@temple.org",
        "username": "alpha_admin",
        "role": "temple_admin",
        "templeId": temple_alpha,
        "isActive": True,
    }

    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)):
        response = client.get(
            f"/api/v1/admin/knowledge/{temple_beta}/documents",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 403
    data = response.json()
    assert data["error"]["code"] == "FORBIDDEN"


def test_superadmin_can_access_any_temple(client: TestClient) -> None:
    """Superadmins have platform-wide access across all temples."""
    superadmin_id = "superadmin_001"
    token = create_access_token({"sub": superadmin_id, "role": "superadmin", "templeId": None})

    mock_superadmin = {
        "_id": superadmin_id,
        "email": "super@platform.org",
        "username": "superadmin",
        "role": "superadmin",
        "templeId": None,
        "isActive": True,
    }

    mock_temple = {
        "_id": "t_beta_id",
        "name": "Temple Beta",
        "slug": "temple-beta",
        "isActive": True,
    }

    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_superadmin)), \
         patch.object(database_service, "get_temple_by_id", new=AsyncMock(return_value=mock_temple)):

        response = client.get(
            "/api/v1/admin/temples/temple-beta",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json()["name"] == "Temple Beta"


def test_temple_admin_cannot_create_temple(client: TestClient) -> None:
    """Temple admins cannot create new temples (Superadmin privileges required)."""
    admin_id = "admin_alpha_1"
    token = create_access_token({"sub": admin_id, "role": "temple_admin", "templeId": "temple-alpha"})

    mock_admin = {
        "_id": admin_id,
        "email": "alpha@temple.org",
        "username": "alpha_admin",
        "role": "temple_admin",
        "templeId": "temple-alpha",
        "isActive": True,
    }

    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)):
        response = client.post(
            "/api/v1/admin/temples",
            json={"name": "New Temple", "slug": "new-temple"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 403
    assert "superadmin" in response.json()["error"]["message"].lower()


# ==============================================================================
# 6. Protected Knowledge Management Operations Tests
# ==============================================================================


def test_admin_add_faq_success(client: TestClient) -> None:
    """Temple admin can add FAQ for their temple."""
    admin_id = "admin_alpha_1"
    temple_alpha = "temple-alpha"
    token = create_access_token({"sub": admin_id, "role": "temple_admin", "templeId": temple_alpha})

    mock_admin = {
        "_id": admin_id,
        "email": "alpha@temple.org",
        "username": "alpha_admin",
        "role": "temple_admin",
        "templeId": temple_alpha,
        "isActive": True,
    }

    mock_result = MagicMock(
        document_id="doc_faq_123",
        chunks_created=1,
        status=MagicMock(value="processed"),
    )

    from app.services.ingestion_service import ingestion_service

    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)), \
         patch.object(ingestion_service, "ingest_text", new=AsyncMock(return_value=mock_result)):

        response = client.post(
            f"/api/v1/admin/knowledge/{temple_alpha}/faq",
            json={
                "question": "What are special pooja charges?",
                "answer": "Special pooja is 500 rupees.",
                "category": "rituals",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["success"] is True
    assert data["documentId"] == "doc_faq_123"
    assert data["chunksCreated"] == 1


def test_admin_trigger_crawl_success(client: TestClient) -> None:
    """Temple admin can trigger website crawl for their temple."""
    admin_id = "admin_alpha_1"
    temple_alpha = "temple-alpha"
    token = create_access_token({"sub": admin_id, "role": "temple_admin", "templeId": temple_alpha})

    mock_admin = {
        "_id": admin_id,
        "email": "alpha@temple.org",
        "username": "alpha_admin",
        "role": "temple_admin",
        "templeId": temple_alpha,
        "isActive": True,
    }

    from app.models.knowledge import CrawlSummary
    mock_summary = CrawlSummary(
        temple_id=temple_alpha,
        start_url="https://temple-alpha.org",
        total_pages_visited=5,
        pages_ingested=5,
        pages_skipped=0,
        pages_failed=0,
        total_chunks_created=18,
        duration_seconds=12.4,
    )

    from app.services.crawler_service import crawler_service

    with patch.object(auth_service, "get_admin_by_id", new=AsyncMock(return_value=mock_admin)), \
         patch.object(crawler_service, "crawl_temple_website", new=AsyncMock(return_value=mock_summary)):

        response = client.post(
            f"/api/v1/admin/knowledge/{temple_alpha}/crawl",
            json={
                "startUrl": "https://temple-alpha.org",
                "maxPages": 5,
                "maxDepth": 2,
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["totalPagesVisited"] == 5
    assert data["totalChunksCreated"] == 18
