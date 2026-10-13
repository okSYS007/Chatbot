import asyncio
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.config import AdminConfig, DailyCardConfig, StorageConfig
from app.daily_card import DailyCardResult
from app.daily_card_runtime import daily_card_loop, daily_card_service, start_daily_cards, stop_daily_cards
from app.handlers.daily_card import daily_card_here, daily_card_preview, daily_card_publish, daily_card_status
from tests.support import project_temp


class DailyCardIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = project_temp()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = SimpleNamespace(admins=AdminConfig({1}), daily_card=DailyCardConfig(), storage=StorageConfig(self.root / "custom.json"))
        self.application = SimpleNamespace(bot=Mock(), bot_data={"config": self.config})
        self.context = SimpleNamespace(application=self.application, bot=Mock(), args=[])
        self.message = SimpleNamespace(reply_text=AsyncMock(), message_thread_id=42, is_topic_message=True)
        self.update = SimpleNamespace(effective_user=SimpleNamespace(id=1), effective_chat=SimpleNamespace(id=-1001, type="supergroup"), effective_message=self.message)

    async def test_non_admin_cannot_use_any_daily_commands(self):
        self.update.effective_user.id = 2
        with patch("app.handlers.daily_card.save_daily_card") as save, patch("app.handlers.daily_card.daily_card_service") as service:
            for handler in [daily_card_here, daily_card_preview, daily_card_publish, daily_card_status]:
                await handler(self.update, self.context)
            save.assert_not_called()
            service.assert_not_called()

    async def test_destination_topic_is_saved_without_enabling(self):
        from app.config import AppConfig, load_config
        # Use a real dataclass for the handler's immutable config replacement.
        self.application.bot_data["config"] = AppConfig(None, AdminConfig({1}), None, None, self.config.storage, None)
        with patch("app.handlers.daily_card.save_daily_card", return_value=DailyCardConfig(chat_id=-1001, message_thread_id=42)) as save:
            await daily_card_here(self.update, self.context)
        save.assert_called_once_with({"chat_id": -1001, "message_thread_id": 42, "enabled": False})
        self.assertFalse(self.application.bot_data["config"].daily_card.enabled)

    async def test_preview_is_only_private_and_no_confirmation_no_send(self):
        with patch("app.handlers.daily_card.daily_card_service") as service:
            await daily_card_preview(self.update, self.context)
            await daily_card_publish(self.update, self.context)
            service.assert_not_called()
        self.update.effective_chat.type = "private"
        self.update.effective_chat.id = 1
        preview = AsyncMock(return_value=DailyCardResult("sent"))
        with patch("app.handlers.daily_card.daily_card_service", return_value=SimpleNamespace(preview=preview)):
            await daily_card_preview(self.update, self.context)
        preview.assert_awaited_once_with(self.context.bot, 1)

    async def test_manual_publish_requires_confirmation_and_keeps_service_limits(self):
        self.context.args = ["CONFIRM"]
        publish = AsyncMock(return_value=DailyCardResult("already_sent"))
        with patch("app.handlers.daily_card.daily_card_service", return_value=SimpleNamespace(publish=publish)):
            await daily_card_publish(self.update, self.context)
        publish.assert_awaited_once_with(self.context.bot, force=True)
        self.assertIn("уже опубликована", self.message.reply_text.call_args.args[0])

    def test_journal_is_beside_configured_database_and_does_not_open_it(self):
        self.assertEqual(daily_card_service(self.application).journal_dir, self.root / "daily_cards")
        self.assertFalse(self.root.joinpath("custom.json").exists())

    async def test_scheduler_survives_error_and_cancels_cleanly(self):
        calls = AsyncMock(side_effect=[OSError("disk error"), DailyCardResult("disabled")])
        sleep = AsyncMock(side_effect=[None, asyncio.CancelledError()])
        with patch("app.daily_card_runtime.daily_card_service", return_value=SimpleNamespace(publish=calls)), patch("app.daily_card_runtime.asyncio.sleep", sleep):
            with self.assertRaises(asyncio.CancelledError):
                await daily_card_loop(self.application)
        self.assertEqual(calls.await_count, 2)

    async def test_start_stop_twice_leaves_no_task(self):
        await start_daily_cards(self.application)
        task = self.application.bot_data["daily_card_task"]
        await stop_daily_cards(self.application)
        await stop_daily_cards(self.application)
        self.assertTrue(task.done())
        self.assertNotIn("daily_card_task", self.application.bot_data)
