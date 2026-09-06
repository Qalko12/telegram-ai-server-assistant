from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ConversationHistory

MAX_HISTORY_MESSAGES = 20


async def load_recent_messages(
    session: AsyncSession, chat_id: int, limit: int = MAX_HISTORY_MESSAGES
) -> list[dict[str, str]]:
    result = await session.execute(
        select(ConversationHistory)
        .where(ConversationHistory.chat_id == chat_id)
        .order_by(ConversationHistory.created_at.desc())
        .limit(limit)
    )
    rows = list(reversed(result.scalars().all()))
    return [{"role": row.role, "content": row.content} for row in rows]


async def append_message(session: AsyncSession, chat_id: int, role: str, content: str) -> None:
    session.add(ConversationHistory(chat_id=chat_id, role=role, content=content))
    await session.commit()
