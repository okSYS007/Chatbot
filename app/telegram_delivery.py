from __future__ import annotations

from asyncio import sleep
from datetime import timedelta
from typing import Any, Awaitable, Callable

from telegram.error import RetryAfter


async def send_post_part(
    method: Callable[..., Awaitable[Any]], *, pause: bool = False, **kwargs: Any
) -> Any:
    if pause:
        await sleep(3.1)

    for attempt in range(3):
        photo = kwargs.get("photo")
        if photo is not None and hasattr(photo, "seek"):
            photo.seek(0)
        try:
            return await method(**kwargs)
        except RetryAfter as error:
            if attempt == 2:
                raise
            retry_after = error.retry_after
            seconds = retry_after.total_seconds() if isinstance(retry_after, timedelta) else float(retry_after)
            await sleep(seconds + 0.1)
