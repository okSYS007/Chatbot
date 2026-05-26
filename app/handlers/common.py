from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes


async def remember_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage = context.application.bot_data["storage"]
    storage.remember_update(update.update_id)


def is_target_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    config = context.application.bot_data["config"]
    if not config.telegram.chat_id:
        return True
    chat = update.effective_chat
    return bool(chat and chat.id == config.telegram.chat_id)


def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    config = context.application.bot_data["config"]
    user = update.effective_user
    return bool(user and user.id in config.admins.user_ids)
