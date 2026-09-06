import datetime
import secrets
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import PendingConfirmation

CONFIRMATION_TTL_SECONDS = 300


class ConfirmationError(Exception):
    pass


@dataclass
class ConfirmationRequest:
    telegram_user_id: int
    chat_id: int
    tool_name: str
    arguments: dict[str, Any]
    reason: str
    agent_session_snapshot: dict[str, Any]


def generate_action_id() -> str:
    return secrets.token_urlsafe(16)


class ConfirmationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, request: ConfirmationRequest, message_id: int | None = None) -> PendingConfirmation:
        now = datetime.datetime.now(datetime.timezone.utc)
        confirmation = PendingConfirmation(
            action_id=generate_action_id(),
            telegram_user_id=request.telegram_user_id,
            chat_id=request.chat_id,
            message_id=message_id,
            tool_name=request.tool_name,
            arguments=request.arguments,
            reason=request.reason,
            agent_session_snapshot=request.agent_session_snapshot,
            status="PENDING",
            created_at=now,
            expires_at=now + datetime.timedelta(seconds=CONFIRMATION_TTL_SECONDS),
        )
        self._session.add(confirmation)
        await self._session.commit()
        return confirmation

    async def resolve(self, action_id: str, telegram_user_id: int, new_status: str) -> PendingConfirmation:
        result = await self._session.execute(
            select(PendingConfirmation).where(PendingConfirmation.action_id == action_id)
        )
        confirmation = result.scalar_one_or_none()

        if confirmation is None:
            raise ConfirmationError("not_found")
        if confirmation.telegram_user_id != telegram_user_id:
            raise ConfirmationError("wrong_user")

        now = datetime.datetime.now(datetime.timezone.utc)
        if confirmation.status != "PENDING" or confirmation.expires_at.replace(tzinfo=datetime.timezone.utc) <= now:
            raise ConfirmationError("not_pending")

        stmt = (
            update(PendingConfirmation)
            .where(PendingConfirmation.action_id == action_id, PendingConfirmation.status == "PENDING")
            .values(status=new_status)
        )
        exec_result = await self._session.execute(stmt)
        await self._session.commit()

        if exec_result.rowcount == 0:
            raise ConfirmationError("race_lost")

        await self._session.refresh(confirmation)
        return confirmation

    async def sweep_expired(self) -> list[PendingConfirmation]:
        now = datetime.datetime.now(datetime.timezone.utc)
        result = await self._session.execute(
            select(PendingConfirmation).where(
                PendingConfirmation.status == "PENDING",
                PendingConfirmation.expires_at <= now,
            )
        )
        expired = list(result.scalars().all())

        if expired:
            await self._session.execute(
                update(PendingConfirmation)
                .where(PendingConfirmation.action_id.in_([c.action_id for c in expired]))
                .values(status="EXPIRED")
            )
            await self._session.commit()

        return expired
