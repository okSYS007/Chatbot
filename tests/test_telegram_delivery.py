import asyncio
import io
import unittest
from datetime import timedelta
from unittest.mock import AsyncMock, patch

from telegram.error import RetryAfter

from app.telegram_delivery import send_post_part


class TelegramDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_pause_and_success(self):
        method = AsyncMock(return_value="ok")
        with patch("app.telegram_delivery.sleep", new=AsyncMock()) as sleep:
            result = await send_post_part(method, pause=True, text="hello")
        self.assertEqual(result, "ok")
        sleep.assert_awaited_once_with(3.1)
        method.assert_awaited_once_with(text="hello")

    async def test_retry_after_int_and_timedelta(self):
        method = AsyncMock(side_effect=[RetryAfter(2), "ok"])
        with patch("app.telegram_delivery.sleep", new=AsyncMock()) as sleep:
            self.assertEqual(await send_post_part(method), "ok")
        sleep.assert_awaited_once_with(2.1)

        method = AsyncMock(side_effect=[RetryAfter(timedelta(seconds=4)), "ok"])
        with patch("app.telegram_delivery.sleep", new=AsyncMock()) as sleep:
            self.assertEqual(await send_post_part(method), "ok")
        sleep.assert_awaited_once_with(4.1)

    async def test_three_retry_after_failures_reraises_without_final_sleep(self):
        error = RetryAfter(1)
        method = AsyncMock(side_effect=error)
        with patch("app.telegram_delivery.sleep", new=AsyncMock()) as sleep:
            with self.assertRaises(RetryAfter):
                await send_post_part(method)
        self.assertEqual(method.await_count, 3)
        self.assertEqual(sleep.await_count, 2)

    async def test_timeout_is_not_retried(self):
        method = AsyncMock(side_effect=TimeoutError())
        with self.assertRaises(TimeoutError):
            await send_post_part(method)
        method.assert_awaited_once()

    async def test_photo_stream_is_reset_for_each_attempt(self):
        photo = io.BytesIO(b"image")
        received = []

        async def consume(**kwargs):
            received.append(kwargs["photo"].read())
            if len(received) == 1:
                raise RetryAfter(0)
            return "ok"

        method = AsyncMock(side_effect=consume)
        with patch("app.telegram_delivery.sleep", new=AsyncMock()):
            await send_post_part(method, photo=photo)
        self.assertEqual(method.await_count, 2)
        self.assertEqual(received, [b"image", b"image"])

    async def test_cancellation_during_pause_sends_nothing(self):
        method = AsyncMock()
        with patch("app.telegram_delivery.sleep", new=AsyncMock(side_effect=asyncio.CancelledError())):
            with self.assertRaises(asyncio.CancelledError):
                await send_post_part(method, pause=True)
        method.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
