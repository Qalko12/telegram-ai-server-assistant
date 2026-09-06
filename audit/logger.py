import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AuditLog


class AuditLogger:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log(
        self,
        *,
        telegram_user_id: int,
        user_message: str | None = None,
        ai_decision: str | None = None,
        tool_name: str | None = None,
        arguments: dict[str, Any] | None = None,
        result: str | None = None,
        execution_time_ms: float | None = None,
        success: bool = True,
        error: str | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            timestamp=datetime.datetime.now(datetime.timezone.utc),
            telegram_user_id=telegram_user_id,
            user_message=user_message,
            ai_decision=ai_decision,
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            execution_time_ms=execution_time_ms,
            success=success,
            error=error,
        )
        self._session.add(entry)
        await self._session.commit()
        return entry
