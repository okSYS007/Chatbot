from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.handlers.common import is_admin
from app.welcome import get_welcome_text, render_welcome


async def health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update, context):
        return

    storage = context.application.bot_data["storage"]
    state = storage.snapshot()
    meta = state.get("meta", {})
    await update.effective_message.reply_text(
        "\n".join(
            [
                "Бот работает.",
                f"Пользователей в JSON: {len(state.get('users', {}))}",
                f"Последний update_id: {meta.get('last_update_id')}",
                f"Последний update: {meta.get('last_seen_update_at')}",
            ]
        )
    )


async def top_rep(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage = context.application.bot_data["storage"]
    users = list(storage.snapshot().get("users", {}).values())
    users.sort(key=lambda item: int(item.get("reputation") or 0), reverse=True)
    top = users[:10]
    if not top:
        await update.effective_message.reply_text("Пока нет данных по репутации.")
        return

    lines = ["Топ репутации:"]
    for index, user in enumerate(top, start=1):
        name = user.get("display_name") or user.get("username") or user.get("user_id")
        lines.append(f"{index}. {name}: {user.get('reputation', 0)}")
    await update.effective_message.reply_text("\n".join(lines))


async def rep(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage = context.application.bot_data["storage"]
    target_id: int | None = None

    if context.args:
        try:
            target_id = int(context.args[0])
        except ValueError:
            target_id = None
    elif update.effective_user:
        target_id = update.effective_user.id

    if not target_id:
        await update.effective_message.reply_text("Укажи user_id: /rep 123456789")
        return

    user = storage.get_user(target_id)
    if not user:
        await update.effective_message.reply_text("Пока нет данных по этому пользователю.")
        return

    await update.effective_message.reply_text(
        "\n".join(
            [
                f"Пользователь: {user.get('display_name') or user.get('username') or target_id}",
                f"Репутация: {user.get('reputation', 0)}",
                f"Сообщений: {user.get('message_count', 0)}",
                f"Засчитанных лайков: {user.get('likes_received', 0)}",
            ]
        )
    )


async def test_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update, context) or not update.effective_user or not update.effective_chat:
        return

    config = context.application.bot_data["config"]
    storage = context.application.bot_data["storage"]
    await update.effective_message.reply_text(
        render_welcome(get_welcome_text(config, storage), update.effective_user, update.effective_chat)
    )


async def set_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update, context):
        return

    text = " ".join(context.args).strip()
    if not text:
        await update.effective_message.reply_text(
            "Использование: /set_welcome Привет, {name}! Добро пожаловать."
        )
        return

    storage = context.application.bot_data["storage"]
    storage.set_setting("welcome_text", text)
    await update.effective_message.reply_text("Текст приветствия обновлен.")
