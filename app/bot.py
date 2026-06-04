from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from telegram import Update
from telegram.error import TelegramError
from telegram.ext import (
    ApplicationBuilder,
    ChatMemberHandler,
    CommandHandler,
    MessageHandler,
    MessageReactionHandler,
    TypeHandler,
    filters,
)

from app.config import load_config, save_admin_user_ids
from app.handlers.admin import (
    health,
    rep,
    rep_reaction_add,
    rep_reaction_remove,
    rep_reactions,
    reset_users,
    set_welcome,
    spend_rep,
    test_welcome,
    top_rep,
)
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


async def sync_group_admins(application) -> None:
    config = application.bot_data["config"]
    if not config.telegram.chat_id:
        return

    logger = logging.getLogger(__name__)
    try:
        chat_admins = await application.bot.get_chat_administrators(config.telegram.chat_id)
    except TelegramError as exc:
        logger.warning("Could not sync Telegram group admins: %s", exc)
        return

    telegram_admin_ids = {
        member.user.id
        for member in chat_admins
        if member.user and not member.user.is_bot
    }
    if not telegram_admin_ids:
        return

    current_admin_ids = set(config.admins.user_ids)
    merged_admin_ids = current_admin_ids | telegram_admin_ids
    if merged_admin_ids == current_admin_ids:
        return

    save_admin_user_ids(merged_admin_ids)
    application.bot_data["config"] = load_config()
    logger.info("Added Telegram group admins to config: %s", sorted(telegram_admin_ids - current_admin_ids))


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

    application = ApplicationBuilder().token(config.telegram.token).post_init(sync_group_admins).build()
    application.bot_data["config"] = config
    application.bot_data["storage"] = storage

    application.add_handler(TypeHandler(Update, remember_update), group=-100)
    application.add_handler(CommandHandler("health", health))
    application.add_handler(CommandHandler("toprep", top_rep))
    application.add_handler(CommandHandler("rep", rep))
    application.add_handler(CommandHandler("test_welcome", test_welcome))
    application.add_handler(CommandHandler("set_welcome", set_welcome))
    application.add_handler(CommandHandler("reset_users", reset_users))
    application.add_handler(CommandHandler("spend_rep", spend_rep))
    application.add_handler(CommandHandler("rep_reactions", rep_reactions))
    application.add_handler(CommandHandler("rep_reaction_add", rep_reaction_add))
    application.add_handler(CommandHandler("rep_reaction_remove", rep_reaction_remove))
    application.add_handler(ChatMemberHandler(handle_chat_member, ChatMemberHandler.CHAT_MEMBER))
    application.add_handler(MessageReactionHandler(handle_reaction))
    application.add_handler(MessageHandler(filters.ALL, handle_message))

    return application


def run_bot() -> None:
    application = build_application()
    logging.getLogger(__name__).info("Bot started")
    application.run_polling(allowed_updates=ALLOWED_UPDATES)
