import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_seen_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_seen_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)


class ConversationHistory(Base):
    __tablename__ = "conversation_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    role: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


class ConversationSummary(Base):
    __tablename__ = "conversation_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    summary_text: Mapped[str] = mapped_column(Text)
    covers_up_to_message_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class MonitoringRule(Base):
    __tablename__ = "monitoring_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_by_telegram_id: Mapped[int] = mapped_column(BigInteger)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    rule_type: Mapped[str] = mapped_column(String(64))
    condition: Mapped[dict[str, Any]] = mapped_column(JSON)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    last_triggered_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PendingConfirmation(Base):
    __tablename__ = "pending_confirmations"

    action_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tool_name: Mapped[str] = mapped_column(String(128))
    arguments: Mapped[dict[str, Any]] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)
    agent_session_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), default="PENDING", index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    expires_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    arguments: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    path: Mapped[str] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(32), default="created")
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
