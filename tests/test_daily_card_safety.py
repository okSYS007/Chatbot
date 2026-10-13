import asyncio
import json
import unittest
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.config import DailyCardConfig
from app.daily_card import DailyCardService
from tests.support import PNG, project_temp


class DailyCardSafetyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = project_temp()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cards = self.root / 'cards'
        self.cards.mkdir()
        self.card = self.cards / 'sun.png'
        self.card.write_bytes(PNG)
        self.config = DailyCardConfig(enabled=True, folder=self.cards, chat_id=-1001, message_thread_id=42)
        self.journal = self.root / 'journal'
        self.service = DailyCardService(self.config, self.journal)
        self.bot = SimpleNamespace(send_photo=AsyncMock(return_value=SimpleNamespace(message_id=77)),
                                   send_message=AsyncMock(return_value=SimpleNamespace(message_id=78)))
        self.now = datetime(2026, 6, 1, 7, tzinfo=UTC)

    async def test_restart_and_deleted_cards_keep_deduplication(self):
        self.assertEqual((await self.service.publish(self.bot, now=self.now)).status, 'sent')
        self.card.unlink()
        restarted = DailyCardService(self.config, self.journal)
        self.assertEqual((await restarted.publish(self.bot, now=self.now)).status, 'already_sent')
        self.bot.send_photo.assert_awaited_once()

    async def test_sends_topic_and_caption_with_closed_file(self):
        self.card.with_suffix('.txt').write_text('Солнце — вопрос для размышления.', encoding='utf-8')
        await self.service.publish(self.bot, now=self.now)
        kwargs = self.bot.send_photo.call_args.kwargs
        self.assertEqual(kwargs['message_thread_id'], 42)
        self.assertEqual(kwargs['chat_id'], -1001)
        self.assertEqual(kwargs['caption'], 'Солнце — вопрос для размышления.')
        self.assertIsNone(kwargs['parse_mode'])
        self.assertTrue(kwargs['photo'].closed)

    async def test_before_time_and_force_respects_dedup(self):
        before = datetime(2026, 6, 1, 5, tzinfo=UTC)
        self.assertEqual((await self.service.publish(self.bot, now=before)).status, 'not_due')
        self.assertFalse(self.journal.exists())
        self.assertEqual((await self.service.publish(self.bot, now=before, force=True)).status, 'sent')
        self.assertEqual((await self.service.publish(self.bot, now=before, force=True)).status, 'already_sent')

    async def test_new_local_day_and_late_start_no_backlog(self):
        service = DailyCardService(replace(self.config, time='00:00'), self.journal)
        for moment in [datetime(2026, 6, 1, 20, 59, tzinfo=UTC), datetime(2026, 6, 1, 21, 1, tzinfo=UTC)]:
            self.assertEqual((await service.publish(self.bot, now=moment)).status, 'sent')
        self.assertEqual(len(list(self.journal.glob('*.json'))), 2)
        await service.publish(self.bot, now=datetime(2026, 6, 20, 22, tzinfo=UTC))
        self.assertEqual(self.bot.send_photo.await_count, 3)

    async def test_dst_repeated_hour_does_not_duplicate(self):
        service = DailyCardService(replace(self.config, time='03:30'), self.journal)
        self.assertEqual((await service.publish(self.bot, now=datetime(2026, 10, 25, 0, 45, tzinfo=UTC))).status, 'sent')
        self.assertEqual((await service.publish(self.bot, now=datetime(2026, 10, 25, 1, 45, tzinfo=UTC))).status, 'already_sent')

    async def test_parallel_services_only_send_once(self):
        async def send(**kwargs):
            await asyncio.sleep(0)
            return SimpleNamespace(message_id=77)
        self.bot.send_photo.side_effect = send
        second = DailyCardService(self.config, self.journal)
        results = await asyncio.gather(self.service.publish(self.bot, now=self.now), second.publish(self.bot, now=self.now))
        self.assertEqual([r.status for r in results].count('sent'), 1)
        self.bot.send_photo.assert_awaited_once()

    async def test_network_error_blocks_automatic_retry(self):
        self.bot.send_photo.side_effect = TimeoutError()
        self.assertEqual((await self.service.publish(self.bot, now=self.now)).status, 'uncertain')
        self.assertEqual((await self.service.publish(self.bot, now=self.now, force=True)).status, 'uncertain')
        self.bot.send_photo.assert_awaited_once()

    async def test_finalize_disk_failure_preserves_reservation(self):
        with patch.object(self.service, '_atomic_write', side_effect=OSError('disk full')):
            self.assertEqual((await self.service.publish(self.bot, now=self.now)).status, 'uncertain')
        self.assertEqual((await self.service.publish(self.bot, now=self.now)).status, 'uncertain')
        self.bot.send_photo.assert_awaited_once()

    async def test_cancellation_after_reservation_blocks_retry(self):
        self.bot.send_photo.side_effect = asyncio.CancelledError()
        with self.assertRaises(asyncio.CancelledError):
            await self.service.publish(self.bot, now=self.now)
        self.assertEqual((await self.service.publish(self.bot, now=self.now)).status, 'uncertain')
        self.bot.send_photo.assert_awaited_once()

    async def test_corrupt_reservation_blocks_even_without_cards(self):
        self.journal.mkdir()
        self.card.unlink()
        for bad in ('[]', 'bad json', 'null'):
            (self.journal / '-1001_42_2026-06-01.json').write_text(bad, encoding='utf-8')
            self.assertEqual((await self.service.publish(self.bot, now=self.now)).status, 'uncertain')
        self.bot.send_photo.assert_not_awaited()

    async def test_invalid_image_or_empty_text_does_not_reserve(self):
        self.card.write_bytes(b'not an image')
        self.assertEqual((await self.service.publish(self.bot, now=self.now)).status, 'failed')
        self.assertFalse(self.journal.exists())
        self.card.write_bytes(PNG)
        self.card.with_suffix('.txt').write_text('  \n ', encoding='utf-8')
        self.assertEqual((await self.service.publish(self.bot, now=self.now)).status, 'failed')
        self.assertFalse(self.journal.exists())
        self.bot.send_photo.assert_not_awaited()

    async def test_oversized_file_does_not_reserve(self):
        with self.card.open('wb') as stream:
            stream.write(PNG)
            stream.truncate(10 * 1024 * 1024 + 1)
        self.assertEqual((await self.service.publish(self.bot, now=self.now)).status, 'failed')
        self.assertFalse(self.journal.exists())

    async def test_preview_when_disabled_never_writes_journal(self):
        service = DailyCardService(replace(self.config, enabled=False), self.journal)
        self.assertEqual((await service.publish(self.bot, now=self.now, force=True)).status, 'disabled')
        self.assertEqual((await service.preview(self.bot, 100)).status, 'sent')
        self.assertFalse(self.journal.exists())
        self.assertEqual(self.bot.send_photo.call_args.kwargs['chat_id'], 100)
        self.assertNotIn('message_thread_id', self.bot.send_photo.call_args.kwargs)

    async def test_missing_directory_creates_no_journal(self):
        self.card.unlink()
        self.cards.rmdir()
        self.assertEqual((await self.service.publish(self.bot, now=self.now)).status, 'no_cards')
        self.assertFalse(self.journal.exists())

    def test_scan_recursive_and_supported_extensions(self):
        (self.cards / 'notes.txt').write_text('x', encoding='utf-8')
        (self.cards / 'nested').mkdir()
        (self.cards / 'nested' / 'hidden.png').write_bytes(PNG)
        (self.cards / 'second.JPG').write_bytes(b'\xff\xd8\xff')
        self.assertEqual({p.name for p in self.service.list_cards()}, {'sun.png', 'second.JPG', 'hidden.png'})
