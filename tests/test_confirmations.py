import datetime

import pytest

from security.confirmations import ConfirmationError, ConfirmationRequest, ConfirmationService


def _make_request(**overrides) -> ConfirmationRequest:
    defaults = dict(
        telegram_user_id=42,
        chat_id=42,
        tool_name="reboot",
        arguments={},
        reason="dummy critical action for testing",
        agent_session_snapshot={"messages": []},
    )
    defaults.update(overrides)
    return ConfirmationRequest(**defaults)


async def test_create_confirmation_is_pending(session_factory) -> None:
    async with session_factory() as session:
        service = ConfirmationService(session)
        confirmation = await service.create(_make_request())

        assert confirmation.status == "PENDING"
        assert confirmation.tool_name == "reboot"
        assert confirmation.telegram_user_id == 42


async def test_approve_transitions_to_approved(session_factory) -> None:
    async with session_factory() as session:
        service = ConfirmationService(session)
        confirmation = await service.create(_make_request())

        resolved = await service.resolve(confirmation.action_id, telegram_user_id=42, new_status="APPROVED")

        assert resolved.status == "APPROVED"


async def test_wrong_user_cannot_resolve(session_factory) -> None:
    async with session_factory() as session:
        service = ConfirmationService(session)
        confirmation = await service.create(_make_request())

        with pytest.raises(ConfirmationError, match="wrong_user"):
            await service.resolve(confirmation.action_id, telegram_user_id=999, new_status="APPROVED")


async def test_double_resolve_fails_on_second_attempt(session_factory) -> None:
    async with session_factory() as session:
        service = ConfirmationService(session)
        confirmation = await service.create(_make_request())

        await service.resolve(confirmation.action_id, telegram_user_id=42, new_status="APPROVED")

        with pytest.raises(ConfirmationError, match="not_pending"):
            await service.resolve(confirmation.action_id, telegram_user_id=42, new_status="APPROVED")


async def test_unknown_action_id_raises_not_found(session_factory) -> None:
    async with session_factory() as session:
        service = ConfirmationService(session)

        with pytest.raises(ConfirmationError, match="not_found"):
            await service.resolve("does-not-exist", telegram_user_id=42, new_status="APPROVED")


async def test_expired_confirmation_cannot_be_resolved(session_factory) -> None:
    async with session_factory() as session:
        service = ConfirmationService(session)
        confirmation = await service.create(_make_request())
        confirmation.expires_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=1)
        await session.commit()

        with pytest.raises(ConfirmationError, match="not_pending"):
            await service.resolve(confirmation.action_id, telegram_user_id=42, new_status="APPROVED")


async def test_sweep_expired_marks_status_expired(session_factory) -> None:
    async with session_factory() as session:
        service = ConfirmationService(session)
        confirmation = await service.create(_make_request())
        confirmation.expires_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=1)
        await session.commit()

        expired = await service.sweep_expired()

        assert [c.action_id for c in expired] == [confirmation.action_id]

        with pytest.raises(ConfirmationError, match="not_pending"):
            await service.resolve(confirmation.action_id, telegram_user_id=42, new_status="APPROVED")
