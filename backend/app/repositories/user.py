from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(User, session)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(
                User.email == email, User.is_deleted == False
            )  # noqa: E712
        )
        return result.scalar_one_or_none()

    async def get_active_users_by_city(self, city: str) -> list[User]:
        result = await self.session.execute(
            select(User).where(
                User.city == city,
                User.is_active == True,  # noqa: E712
                User.is_deleted == False,  # noqa: E712
            )
        )
        return list(result.scalars().all())
