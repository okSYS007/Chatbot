import json
import asyncio
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.daily_card import DailyCardService


def cfg(folder, **kw):
    data = dict(enabled=True, folder=Path(folder), chat_id=777, message_thread_id=42,
                time="09:00", timezone="Europe/Kyiv", caption="Карта дня: {name}")
    data.update(kw)
    return SimpleNamespace(**data)


class DailyCardTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.pacing = patch("app.telegram_delivery.sleep", new=AsyncMock())
        self.pacing.start()
        self.addCleanup(self.pacing.stop)

    def temp(self):
        base = Path(__file__).parents[1] / "work" / "tmp"
        base.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=base)

    def make_card(self, root):
        folder = root / "cards" / "arbitrary" / "nested"
        folder.mkdir(parents=True)
        (folder / "one.png").write_bytes(b"\x89PNG\r\n\x1a\n")
        (folder / "two.jpg").write_bytes(b"\xff\xd8\xff\xd9")
        return root / "cards"

    async def test_recursive_independent_random_choices_and_topic(self):
        with self.temp() as raw:
            root = Path(raw); folder = self.make_card(root)
            texts = folder / "texts"; texts.mkdir()
            (texts / "meaning.txt").write_text("значение", encoding="utf-8")
            (texts / "other.txt").write_text("другое", encoding="utf-8")
            (root / "journal").mkdir()
            bot = SimpleNamespace(send_photo=AsyncMock(return_value=SimpleNamespace(message_id=1)), send_message=AsyncMock())
            service = DailyCardService(cfg(folder), root / "journal")
            with patch("app.daily_card.random.choice", side_effect=lambda values: values[-1]):
                result = await service.publish(bot, now=datetime(2026, 6, 1, 10))
            self.assertEqual(result.status, "sent")
            bot.send_photo.assert_awaited_once()
            call = bot.send_photo.await_args.kwargs
            self.assertEqual(call["chat_id"], 777)
            self.assertEqual(call["message_thread_id"], 42)
            self.assertEqual(call["caption"], "другое")

    async def test_long_emoji_text_is_exactly_split_and_literal(self):
        with self.temp() as raw:
            root = Path(raw); folder = self.make_card(root)
            (folder / "meaning.txt").write_text("😀" * 6000, encoding="utf-8")
            (root / "journal").mkdir()
            bot = SimpleNamespace(send_photo=AsyncMock(return_value=SimpleNamespace(message_id=1)), send_message=AsyncMock(side_effect=lambda **kw: SimpleNamespace(message_id=len(kw["text"]))))
            service = DailyCardService(cfg(folder), root / "journal")
            result = await service.publish(bot, now=datetime(2026, 6, 1, 10))
            self.assertEqual(result.status, "sent")
            parts = [call.kwargs["text"] for call in bot.send_message.await_args_list]
            self.assertEqual("".join(parts), "😀" * 6000)
            self.assertTrue(all(len(p.encode("utf-16-le")) // 2 <= 4096 for p in parts))
            self.assertTrue(all(call.kwargs["parse_mode"] is None for call in bot.send_message.await_args_list))
            self.assertTrue(all(call.kwargs["chat_id"] == 777 and call.kwargs["message_thread_id"] == 42 for call in bot.send_message.await_args_list))

    async def test_halfway_failure_persists_progress_and_restart_does_not_repeat(self):
        with self.temp() as raw:
            root = Path(raw); folder = self.make_card(root); (folder / "meaning.txt").write_text("x" * 10000, encoding="utf-8")
            (root / "journal").mkdir()
            photo = AsyncMock(return_value=SimpleNamespace(message_id=10)); messages = AsyncMock(side_effect=[SimpleNamespace(message_id=11), RuntimeError("network")])
            bot = SimpleNamespace(send_photo=photo, send_message=messages)
            service = DailyCardService(cfg(folder), root / "journal")
            self.assertEqual((await service.publish(bot, now=datetime(2026, 6, 1, 10))).status, "uncertain")
            journal = next((root / "journal").glob("*.json")); state = json.loads(journal.read_text(encoding="utf-8"))
            self.assertEqual(state["completed_parts"], 2); self.assertEqual(state["total_parts"], 4)
            self.assertEqual(state["message_ids"], [10, 11])
            self.assertIn(state["card"], {"arbitrary/nested/one.png", "arbitrary/nested/two.jpg"})
            self.assertEqual(state["text"], "meaning.txt")
            fresh = SimpleNamespace(send_photo=AsyncMock(), send_message=AsyncMock())
            self.assertEqual((await DailyCardService(cfg(folder), root / "journal").publish(fresh, now=datetime(2026, 6, 1, 10))).status, "uncertain")
            fresh.send_photo.assert_not_awaited(); fresh.send_message.assert_not_awaited()

    async def test_cancel_after_photo_keeps_reservation_and_blocks_retry(self):
        with self.temp() as raw:
            root = Path(raw); folder = self.make_card(root); (folder / "meaning.txt").write_text("x" * 10000, encoding="utf-8")
            (root / "journal").mkdir()
            bot = SimpleNamespace(send_photo=AsyncMock(return_value=SimpleNamespace(message_id=1)), send_message=AsyncMock(side_effect=asyncio.CancelledError()))
            service = DailyCardService(cfg(folder), root / "journal")
            with self.assertRaises(asyncio.CancelledError): await service.publish(bot, now=datetime(2026, 6, 1, 10))
            fresh = SimpleNamespace(send_photo=AsyncMock(), send_message=AsyncMock())
            self.assertEqual((await DailyCardService(cfg(folder), root / "journal").publish(fresh, now=datetime(2026, 6, 1, 10))).status, "uncertain")

    async def test_bad_text_fails_before_reservation_and_preview_has_no_journal(self):
        with self.temp() as raw:
            root = Path(raw); folder = self.make_card(root); (folder / "bad.doc").write_bytes(b"old")
            bot = SimpleNamespace(send_photo=AsyncMock(), send_message=AsyncMock())
            service = DailyCardService(cfg(folder), root / "journal")
            self.assertEqual((await service.publish(bot, now=datetime(2026, 6, 1, 10))).status, "failed")
            self.assertFalse((root / "journal").exists())
            self.assertEqual((await service.preview(bot, 9, 3)).status, "failed")
            self.assertFalse((root / "journal").exists())

    async def test_preview_long_text_sends_photo_then_chunks_without_journal(self):
        with self.temp() as raw:
            root = Path(raw); folder = self.make_card(root); (folder / "meaning.txt").write_text("z" * 10000, encoding="utf-8")
            bot = SimpleNamespace(send_photo=AsyncMock(return_value=SimpleNamespace(message_id=1)), send_message=AsyncMock())
            result = await DailyCardService(cfg(folder), root / "journal").preview(bot, 99, 5)
            self.assertEqual(result.status, "sent")
            bot.send_photo.assert_awaited_once()
            self.assertGreaterEqual(bot.send_message.await_count, 3)
            self.assertFalse((root / "journal").exists())

    async def test_existing_sent_or_reserved_journal_never_retries(self):
        with self.temp() as raw:
            root = Path(raw); folder = self.make_card(root); journal = root / "journal"; journal.mkdir()
            name = "777_42_2026-06-01.json"
            for status in ("sent", "reserved"):
                (journal / name).write_text(json.dumps({"status": status, "card": "arbitrary/nested/one.png", "text": None}), encoding="utf-8")
                bot = SimpleNamespace(send_photo=AsyncMock(), send_message=AsyncMock())
                result = await DailyCardService(cfg(folder), journal).publish(bot, now=datetime(2026, 6, 1, 10))
                self.assertEqual(result.status, "already_sent" if status == "sent" else "uncertain")
                bot.send_photo.assert_not_awaited(); bot.send_message.assert_not_awaited()
                (journal / name).unlink()


if __name__ == "__main__":
    unittest.main()
