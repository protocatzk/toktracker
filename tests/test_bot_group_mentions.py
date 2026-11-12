"""
Tests für den Gruppen-Mention/Reply-Handler des Telegram-Bots.

Antworten auf Bot-Nachrichten ohne gültigen Text-Befehl dürfen keine Nachricht
auslösen. Direkte @-Mentions ohne Befehl zeigen weiterhin die Hilfe.
"""

try:  # Testumgebung (isolierte DB/Secrets) vor App-Imports setzen
    from . import _bootstrap  # noqa: F401
except ImportError:  # pragma: no cover
    import _bootstrap  # noqa: F401

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from telegram import Chat, Message, Update, User
from telegram.constants import ChatType

from telegram_service import TelegramBotService

BOT_USERNAME = "testbot"
BOT_USER = User(id=999, first_name="Bot", is_bot=True, username=BOT_USERNAME)
HUMAN_USER = User(id=1, first_name="Alice", is_bot=False, username="alice")
CHAT = Chat(id=-1001234567890, type=ChatType.SUPERGROUP, title="Testgruppe")


def _message(
    *,
    message_id: int,
    text: str,
    reply_to: Message | None = None,
) -> Message:
    return Message(
        message_id=message_id,
        date=datetime.now(timezone.utc),
        chat=CHAT,
        from_user=HUMAN_USER,
        text=text,
        reply_to_message=reply_to,
    )


def _bot_message(message_id: int = 10) -> Message:
    return Message(
        message_id=message_id,
        date=datetime.now(timezone.utc),
        chat=CHAT,
        from_user=BOT_USER,
        text="Bot-Nachricht",
    )


class GroupMentionHandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.service = TelegramBotService()
        self.service._bot_username_raw = BOT_USERNAME
        self.service._cmd_help = AsyncMock()
        self.service._cmd_streamer = AsyncMock()
        self.context = SimpleNamespace(args=None)

    async def test_reply_without_command_is_silent(self) -> None:
        update = Update(
            update_id=1,
            message=_message(
                message_id=2,
                text="Danke!",
                reply_to=_bot_message(),
            ),
        )

        await self.service._on_group_mention(update, self.context)

        self.service._cmd_help.assert_not_awaited()
        self.service._cmd_streamer.assert_not_awaited()

    async def test_reply_with_command_is_dispatched(self) -> None:
        update = Update(
            update_id=2,
            message=_message(
                message_id=3,
                text="stats streamer123",
                reply_to=_bot_message(),
            ),
        )

        await self.service._on_group_mention(update, self.context)

        self.service._cmd_streamer.assert_awaited_once()
        self.service._cmd_help.assert_not_awaited()

    async def test_reply_with_help_still_shows_help(self) -> None:
        update = Update(
            update_id=3,
            message=_message(
                message_id=4,
                text="help",
                reply_to=_bot_message(),
            ),
        )

        await self.service._on_group_mention(update, self.context)

        self.service._cmd_help.assert_awaited_once()

    async def test_mention_without_command_still_shows_help(self) -> None:
        update = Update(
            update_id=4,
            message=_message(
                message_id=5,
                text=f"@{BOT_USERNAME} Danke!",
            ),
        )

        await self.service._on_group_mention(update, self.context)

        self.service._cmd_help.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
