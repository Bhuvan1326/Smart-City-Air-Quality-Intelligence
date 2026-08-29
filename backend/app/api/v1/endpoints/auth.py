from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser
from app.core.database import get_db
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.schemas.base import APIResponse
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=APIResponse[UserResponse],
    status_code=status.HTTP_201_CREATED,
)
async def register(
    data: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[UserResponse]:
    auth_service = AuthService(session)
    try:
        user = await auth_service.register(data)
        return APIResponse(data=user, message="Registration successful")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)
        ) from e


@router.post("/login", response_model=APIResponse[TokenResponse])
async def login(
    data: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[TokenResponse]:
    auth_service = AuthService(session)
    try:
        tokens = await auth_service.login(data)
        return APIResponse(data=tokens, message="Login successful")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)
        ) from e


@router.post("/refresh", response_model=APIResponse[TokenResponse])
async def refresh_token(
    data: RefreshRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> APIResponse[TokenResponse]:
    auth_service = AuthService(session)
    try:
        tokens = await auth_service.refresh(data.refresh_token)
        return APIResponse(data=tokens)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)
        ) from e


@router.post("/logout", response_model=APIResponse[None])
async def logout(
    current_user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    data: LogoutRequest | None = None,
) -> APIResponse[None]:
    auth_service = AuthService(session)
    await auth_service.logout(data.refresh_token if data else None)
    return APIResponse(message="Logged out successfully")


@router.get("/me", response_model=APIResponse[UserResponse])
async def get_me(current_user: CurrentUser) -> APIResponse[UserResponse]:
    return APIResponse(data=UserResponse.model_validate(current_user))
