from __future__ import annotations

from telegram import ChatMember, Update
from telegram.ext import ContextTypes

from app.handlers.common import is_target_chat
from app.welcome import get_welcome_text, render_welcome


def _became_member(old_status: str, new_status: str) -> bool:
    inactive = {ChatMember.LEFT, ChatMember.BANNED}
    active = {ChatMember.MEMBER, ChatMember.ADMINISTRATOR, ChatMember.OWNER}
    return old_status in inactive and new_status in active


async def handle_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_target_chat(update, context) or not update.chat_member:
        return

    event = update.chat_member
    if not _became_member(event.old_chat_member.status, event.new_chat_member.status):
        return

    user = event.new_chat_member.user
    storage = context.application.bot_data["storage"]
    config = context.application.bot_data["config"]
    storage.ensure_user(user)
    should_welcome = storage.mark_welcomed(user)

    if should_welcome and config.welcome.enabled:
        await context.bot.send_message(
            chat_id=event.chat.id,
            text=render_welcome(get_welcome_text(config, storage), user, event.chat),
        )
