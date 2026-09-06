import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def touch(self, telegram_user_id: int, username: str | None) -> User:
        result = await self._session.execute(select(User).where(User.telegram_user_id == telegram_user_id))
        user = result.scalar_one_or_none()
        now = datetime.datetime.now(datetime.timezone.utc)

        if user is None:
            user = User(telegram_user_id=telegram_user_id, username=username, first_seen_at=now, last_seen_at=now)
            self._session.add(user)
        else:
            user.last_seen_at = now
            if username is not None:
                user.username = username

        await self._session.commit()
        return user
