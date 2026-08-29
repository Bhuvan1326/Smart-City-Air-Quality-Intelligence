from typing import Annotated

from app.core.database import get_db
from app.models.user import User, UserRole
from app.services.auth import AuthService
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    auth_service = AuthService(session)
    try:
        return await auth_service.get_current_user(credentials.credentials)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e


def require_roles(*roles: UserRole):
    async def role_checker(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access requires one of: {[r.value for r in roles]}",
            )
        return current_user

    return role_checker


RequireAdmin = Depends(require_roles(UserRole.CITY_ADMINISTRATOR))
RequireOfficer = Depends(
    require_roles(
        UserRole.CITY_ADMINISTRATOR,
        UserRole.POLLUTION_CONTROL_OFFICER,
        UserRole.FIELD_INSPECTOR,
    )
)
RequireInspector = Depends(require_roles(UserRole.FIELD_INSPECTOR))
CurrentUser = Annotated[User, Depends(get_current_user)]
