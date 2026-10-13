from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from app.daily_card import DailyCardService

logger = logging.getLogger(__name__)


def daily_card_service(application) -> DailyCardService:
    config = application.bot_data["config"]
    return DailyCardService(config.daily_card, config.storage.path.parent / "daily_cards")


async def daily_card_loop(application) -> None:
    previous_status = None
    while True:
        try:
            result = await daily_card_service(application).publish(application.bot)
            if result.status != previous_status:
                if result.status in {"failed", "uncertain", "no_cards"}:
                    logger.warning("Daily card: %s (see /daily_card_status)", result.status)
                elif result.status == "sent":
                    logger.info("Daily card published: message_id=%s", result.message_id)
                previous_status = result.status
        except Exception as exc:
            # Keep the scheduler alive without logging tokens from HTTP exceptions.
            name = type(exc).__name__
            if previous_status != name:
                logger.error("Daily card scheduler error: %s", name)
            previous_status = name
        await asyncio.sleep(30)


async def start_daily_cards(application) -> None:
    application.bot_data["daily_card_task"] = asyncio.create_task(daily_card_loop(application))


async def stop_daily_cards(application) -> None:
    task = application.bot_data.pop("daily_card_task", None)
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
