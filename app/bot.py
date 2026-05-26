from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ChatMemberHandler,
    CommandHandler,
    MessageHandler,
    MessageReactionHandler,
    TypeHandler,
    filters,
)

from app.config import load_config
from app.handlers.admin import health, rep, set_welcome, test_welcome, top_rep
from app.handlers.common import remember_update
from app.handlers.members import handle_chat_member
from app.handlers.messages import handle_message
from app.handlers.reactions import handle_reaction
from app.storage import JsonStorage


ALLOWED_UPDATES = [
    "message",
    "chat_member",
    "message_reaction",
]


def setup_logging(log_path) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def build_application():
    config = load_config()
    setup_logging(config.logging.path)

    storage = JsonStorage(config.storage.path)
    storage.set_started()

    application = ApplicationBuilder().token(config.telegram.token).build()
    application.bot_data["config"] = config
    application.bot_data["storage"] = storage

    application.add_handler(TypeHandler(Update, remember_update), group=-100)
    application.add_handler(CommandHandler("health", health))
    application.add_handler(CommandHandler("toprep", top_rep))
    application.add_handler(CommandHandler("rep", rep))
    application.add_handler(CommandHandler("test_welcome", test_welcome))
    application.add_handler(CommandHandler("set_welcome", set_welcome))
    application.add_handler(ChatMemberHandler(handle_chat_member, ChatMemberHandler.CHAT_MEMBER))
    application.add_handler(MessageReactionHandler(handle_reaction))
    application.add_handler(MessageHandler(filters.ALL, handle_message))

    return application


def run_bot() -> None:
    application = build_application()
    logging.getLogger(__name__).info("Bot started")
    application.run_polling(allowed_updates=ALLOWED_UPDATES)
