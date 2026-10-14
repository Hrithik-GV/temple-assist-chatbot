"""FastAPI dependencies for JWT authentication and temple-level authorization."""

from typing import Any, Dict, Optional
from fastapi import Depends, Path, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import ForbiddenException, UnauthorizedException
from app.core.security import decode_access_token
from app.models.admin import AdminRole
from app.services.auth_service import auth_service

# Bearer token extractor
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_admin(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
) -> Dict[str, Any]:
    """Extract and validate the JWT Bearer token from the request.

    Args:
        credentials: HTTPAuthorizationCredentials extracted by FastAPI.

    Returns:
        Dict: Authenticated administrator record.

    Raises:
        UnauthorizedException: If token is missing, invalid, expired, or admin is deactivated.
    """
    if not credentials or not credentials.credentials:
        raise UnauthorizedException(
            message="Authorization token is missing. Please provide a Bearer token in the Authorization header.",
        )

    # Decode and validate JWT
    payload = decode_access_token(credentials.credentials)
    admin_id = payload.get("sub")
    if not admin_id:
        raise UnauthorizedException("Invalid token payload: missing subject identifier.")

    # Retrieve and verify admin in database
    admin = await auth_service.get_admin_by_id(admin_id)
    if not admin:
        raise UnauthorizedException("Administrator account not found.")

    if not admin.get("isActive", True):
        raise UnauthorizedException("Administrator account has been deactivated.")

    return admin


async def require_superadmin(
    current_admin: Dict[str, Any] = Depends(get_current_admin),
) -> Dict[str, Any]:
    """Ensure the authenticated admin has system-wide SUPERADMIN privileges.

    Raises:
        ForbiddenException: If administrator does not have the SUPERADMIN role.
    """
    if current_admin.get("role") != AdminRole.SUPERADMIN.value:
        raise ForbiddenException("Superadmin privileges required for this action.")
    return current_admin


class RequireTempleAccess:
    """Dependency enforcing strict temple-level multi-tenancy authorization.

    Rules:
    1. SUPERADMIN accounts have platform-wide access across all temples.
    2. TEMPLE_ADMIN and other roles may ONLY access their assigned templeId.
    3. Accessing any other temple immediately raises ForbiddenException (HTTP 403).
    """

    def __init__(self, allowed_roles: Optional[list[AdminRole]] = None) -> None:
        self.allowed_roles = allowed_roles

    async def __call__(
        self,
        temple_id: str = Path(..., alias="templeId", description="Target temple identifier"),
        current_admin: Dict[str, Any] = Depends(get_current_admin),
    ) -> Dict[str, Any]:
        target_temple = (temple_id or "").strip()
        admin_role = current_admin.get("role")
        admin_temple = current_admin.get("templeId")

        # 1. Check role restriction if specified
        if self.allowed_roles:
            role_values = [r.value for r in self.allowed_roles]
            if admin_role not in role_values and admin_role != AdminRole.SUPERADMIN.value:
                raise ForbiddenException("Insufficient role privileges for this operation.")

        # 2. Superadmins have unrestricted access across all temples
        if admin_role == AdminRole.SUPERADMIN.value:
            return current_admin

        # 3. Cross-temple multi-tenant barrier: enforce admin_temple == target_temple
        if not admin_temple or admin_temple != target_temple:
            raise ForbiddenException(
                f"Access denied: You are assigned to '{admin_temple or 'None'}' and cannot access temple '{target_temple}'."
            )

        return current_admin


def verify_admin_can_access_temple(admin: Dict[str, Any], temple_id: str) -> None:
    """Imperative check verifying an admin has authority over a specific temple."""
    if admin.get("role") == AdminRole.SUPERADMIN.value:
        return
    admin_temple = admin.get("templeId")
    if not admin_temple or admin_temple != temple_id.strip():
        raise ForbiddenException(
            f"Access denied: You cannot access temple '{temple_id}'."
        )
