from __future__ import annotations

from telegram import Chat, User


def get_welcome_text(config, storage) -> str:
    return storage.get_setting("welcome_text", config.welcome.text)


def render_welcome(template: str, user: User, chat: Chat) -> str:
    username = f"@{user.username}" if user.username else user.full_name
    return template.format(
        name=user.full_name,
        username=username,
        user_id=user.id,
        group=chat.title or "группу",
    )
