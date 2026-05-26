from __future__ import annotations

import asyncio
import os

from dotenv import load_dotenv
from telegram import Bot


async def main() -> None:
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN in .env first.")

    bot = Bot(token)
    offset = None
    print("Send any message in your group. Press Ctrl+C when you see the chat_id.")

    while True:
        updates = await bot.get_updates(
            offset=offset,
            timeout=30,
            allowed_updates=["message", "chat_member", "message_reaction"],
        )
        for update in updates:
            offset = update.update_id + 1
            chat = update.effective_chat
            user = update.effective_user
            if not chat:
                continue
            print(
                f"chat_id={chat.id} | type={chat.type} | title={chat.title!r} | "
                f"from={getattr(user, 'id', None)}"
            )


if __name__ == "__main__":
    asyncio.run(main())
