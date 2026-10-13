import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.daily_card import DailyCardService
from tests.support import PNG


def patterned_cfg(images, texts, patterns, **overrides):
    data = dict(
        enabled=True, folder=Path("unused"), chat_id=-100123,
        message_thread_id=17, time="09:00", timezone="Europe/Kyiv",
        caption="Карта дня: {name}", images_folder=Path(images),
        texts_folder=Path(texts), patterns=tuple(patterns), uses_patterns=True,
    )
    data.update(overrides)
    return SimpleNamespace(**data)


class PatternedDailyCardTests(unittest.IsolatedAsyncioTestCase):
    def temp(self):
        base = Path(__file__).parents[1] / "work" / "tmp"
        base.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=base)

    def setUp(self):
        self.pacing = patch("app.telegram_delivery.sleep", new=AsyncMock())
        self.pacing.start()
        self.addCleanup(self.pacing.stop)

    def make_folders(self, root):
        images, texts = root / "Картинки", root / "Тексты"
        (images / "nested").mkdir(parents=True)
        (texts / "nested").mkdir(parents=True)
        return images, texts

    @staticmethod
    def bot():
        return SimpleNamespace(
            send_photo=AsyncMock(return_value=SimpleNamespace(message_id=101)),
            send_message=AsyncMock(side_effect=lambda **kw: SimpleNamespace(message_id=200 + len(kw["text"]))),
        )

    async def test_matches_image_and_text_by_template_without_mixing_cards(self):
        with self.temp() as raw:
            root = Path(raw); images, texts = self.make_folders(root)
            image = images / "nested" / "8 пентаклей часть души.jpg"
            image.write_bytes(PNG)
            (images / "6 жезлов.jpg").write_bytes(PNG)
            (texts / "6 жезлов значение.txt").write_text("не должно попасть", encoding="utf-8")
            image_text = texts / "nested" / "8 пентаклей средина моря.txt"
            image_text.write_text("текст восьми пентаклей", encoding="utf-8")
            bot = self.bot()
            service = DailyCardService(patterned_cfg(images, texts, ["8 пентаклей"]), root / "journal")
            with patch("app.daily_card.random.choice", side_effect=lambda values: values[0]):
                result = await service.publish(bot, now=datetime(2026, 6, 1, 10))
            self.assertEqual(result.status, "sent")
            self.assertEqual(bot.send_photo.await_args.kwargs["caption"], "текст восьми пентаклей")
            self.assertEqual(json.loads(next((root / "journal").glob("*.json")).read_text(encoding="utf-8"))["pattern"], "8 пентаклей")

    async def test_nested_files_and_random_texts_are_sent_to_same_topic(self):
        with self.temp() as raw:
            root = Path(raw); images, texts = self.make_folders(root)
            (images / "8 пентаклей часть души.jpg").write_bytes(PNG)
            (texts / "nested" / "8 пентаклей один.txt").write_text("один", encoding="utf-8")
            (texts / "8 пентаклей два.txt").write_text("два", encoding="utf-8")
            bot = self.bot()
            service = DailyCardService(patterned_cfg(images, texts, ["8 пентаклей"]), root / "journal")
            with patch("app.daily_card.random.choice", side_effect=lambda values: values[-1]):
                result = await service.publish(bot, now=datetime(2026, 6, 1, 10))
            self.assertEqual(result.status, "sent")
            self.assertEqual(bot.send_photo.await_args.kwargs["message_thread_id"], 17)
            self.assertEqual(bot.send_photo.await_args.kwargs["caption"], "один")

    async def test_unmatched_image_is_excluded_before_reservation(self):
        with self.temp() as raw:
            root = Path(raw); images, texts = self.make_folders(root)
            (images / "6 жезлов.jpg").write_bytes(PNG)
            (texts / "8 пентаклей.txt").write_text("текст", encoding="utf-8")
            bot = self.bot()
            result = await DailyCardService(patterned_cfg(images, texts, ["8 пентаклей"]), root / "journal").publish(bot, now=datetime(2026, 6, 1, 10))
            self.assertEqual(result.status, "failed")
            bot.send_photo.assert_not_awaited()
            self.assertFalse((root / "journal").exists())

    async def test_ambiguous_image_is_excluded(self):
        with self.temp() as raw:
            root = Path(raw); images, texts = self.make_folders(root)
            (images / "8 пентаклей.jpg").write_bytes(PNG)
            (texts / "8 пентаклей.txt").write_text("текст", encoding="utf-8")
            config = patterned_cfg(images, texts, ["8", "пентаклей"])
            bot = self.bot()
            result = await DailyCardService(config, root / "journal").publish(bot, now=datetime(2026, 6, 1, 10))
            self.assertEqual(result.status, "failed")
            bot.send_photo.assert_not_awaited()

    async def test_doc_is_not_used_as_caption_fallback(self):
        with self.temp() as raw:
            root = Path(raw); images, texts = self.make_folders(root)
            (images / "8 пентаклей.jpg").write_bytes(PNG)
            (texts / "8 пентаклей.doc").write_bytes(b"old Word")
            config = patterned_cfg(images, texts, ["8 пентаклей"])
            bot = self.bot()
            result = await DailyCardService(config, root / "journal").publish(bot, now=datetime(2026, 6, 1, 10))
            self.assertEqual(result.status, "failed")
            bot.send_photo.assert_not_awaited()
            self.assertFalse((root / "journal").exists())

    async def test_long_text_is_split_and_preserves_topic_and_content(self):
        with self.temp() as raw:
            root = Path(raw); images, texts = self.make_folders(root)
            (images / "8 пентаклей.jpg").write_bytes(PNG)
            text = "😀" * 6000
            (texts / "8 пентаклей.txt").write_text(text, encoding="utf-8")
            bot = self.bot()
            result = await DailyCardService(patterned_cfg(images, texts, ["8 пентаклей"]), root / "journal").publish(bot, now=datetime(2026, 6, 1, 10))
            self.assertEqual(result.status, "sent")
            parts = [call.kwargs["text"] for call in bot.send_message.await_args_list]
            self.assertEqual("".join(parts), text)
            self.assertTrue(all(len(part.encode("utf-16-le")) // 2 <= 4096 for part in parts))
            self.assertTrue(all(call.kwargs["message_thread_id"] == 17 for call in bot.send_message.await_args_list))

    async def test_journal_keeps_relative_paths_and_prevents_duplicate_after_config_change(self):
        with self.temp() as raw:
            root = Path(raw); images, texts = self.make_folders(root)
            (images / "nested" / "8 пентаклей.jpg").write_bytes(PNG)
            (texts / "nested" / "8 пентаклей.txt").write_text("текст", encoding="utf-8")
            journal = root / "journal"
            config = patterned_cfg(images, texts, ["8 пентаклей"])
            bot = self.bot()
            service = DailyCardService(config, journal)
            self.assertEqual((await service.publish(bot, now=datetime(2026, 6, 1, 10))).status, "sent")
            record = json.loads(next(journal.glob("*.json")).read_text(encoding="utf-8"))
            self.assertEqual(record["card"], "nested/8 пентаклей.jpg")
            self.assertEqual(record["text"], "nested/8 пентаклей.txt")
            changed = patterned_cfg(root / "other-images", root / "other-texts", ["other"])
            fresh = self.bot()
            self.assertEqual((await DailyCardService(changed, journal).publish(fresh, now=datetime(2026, 6, 1, 10))).status, "already_sent")
            fresh.send_photo.assert_not_awaited()

    async def test_preview_works_when_disabled_without_creating_journal(self):
        with self.temp() as raw:
            root = Path(raw); images, texts = self.make_folders(root)
            (images / "8 пентаклей.jpg").write_bytes(PNG)
            (texts / "8 пентаклей.txt").write_text("текст", encoding="utf-8")
            config = patterned_cfg(images, texts, ["8 пентаклей"], enabled=False)
            bot = self.bot()
            result = await DailyCardService(config, root / "journal").preview(bot, 999, 4)
            self.assertEqual(result.status, "sent")
            self.assertEqual(bot.send_photo.await_args.kwargs["chat_id"], 999)
            self.assertEqual(bot.send_photo.await_args.kwargs["message_thread_id"], 4)
            self.assertFalse((root / "journal").exists())


if __name__ == "__main__":
    unittest.main()
