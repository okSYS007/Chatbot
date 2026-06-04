from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.handlers.common import is_target_chat
from app.welcome import get_welcome_text, render_welcome


def message_key(chat_id: int, message_id: int) -> str:
    return f"{chat_id}:{message_id}"


def is_reputation_query(text: str | None) -> bool:
    return bool(text and text.strip().lower() in {"!rep", "!reputation"})


async def reply_with_reputation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return

    storage = context.application.bot_data["storage"]
    user = storage.get_user(update.effective_user.id)
    reputation = int(user.get("reputation") or 0) if user else 0
    await update.message.reply_text(f"Ваша репутация: {reputation}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_target_chat(update, context) or not update.message:
        return

    message = update.message
    storage = context.application.bot_data["storage"]
    config = context.application.bot_data["config"]

    if message.new_chat_members:
        for user in message.new_chat_members:
            storage.ensure_user(user)
            should_welcome = storage.mark_welcomed(user)
            if should_welcome and config.welcome.enabled:
                await message.reply_text(render_welcome(get_welcome_text(config, storage), user, message.chat))
        return

    if message.from_user:
        storage.increment_message_count(
            message.from_user,
            message_key=message_key(message.chat.id, message.message_id),
        )

    if is_reputation_query(message.text):
        await reply_with_reputation(update, context)
