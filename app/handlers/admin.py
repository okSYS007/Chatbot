from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.config import load_config, save_reputation_reactions
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
                f"Пользователей в базе: {len(state.get('users', {}))}",
                f"Последний update_id: {meta.get('last_update_id')}",
                f"Последнее событие: {meta.get('last_seen_update_at')}",
            ]
        )
    )


async def top_rep(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update, context):
        return

    storage = context.application.bot_data["storage"]
    users = list(storage.snapshot().get("users", {}).values())
    users.sort(key=lambda item: int(item.get("reputation") or 0), reverse=True)
    top = users[:10]
    if not top:
        await update.effective_message.reply_text("Данных по репутации пока нет.")
        return

    lines = ["Топ репутации:"]
    for index, user in enumerate(top, start=1):
        name = user.get("display_name") or user.get("username") or user.get("user_id")
        lines.append(f"{index}. {name}: {user.get('reputation', 0)}")
    await update.effective_message.reply_text("\n".join(lines))


async def rep(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update, context):
        return

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
        await update.effective_message.reply_text("Использование: /rep 123456789")
        return

    user = storage.get_user(target_id)
    if not user:
        await update.effective_message.reply_text("По этому пользователю пока нет данных.")
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


async def reset_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update, context):
        return

    if not context.args or context.args[0] != "CONFIRM":
        await update.effective_message.reply_text(
            "Команда очищает только пользователей и репутацию. Для подтверждения: /reset_users CONFIRM"
        )
        return

    storage = context.application.bot_data["storage"]
    storage.reset_user_data()
    await update.effective_message.reply_text("Данные пользователей и репутации очищены.")


async def spend_rep(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update, context):
        return

    if not update.effective_user:
        return

    if len(context.args) < 2:
        await update.effective_message.reply_text("Использование: /spend_rep user_id amount [reason]")
        return

    try:
        user_id = int(context.args[0])
        amount = int(context.args[1])
    except ValueError:
        await update.effective_message.reply_text("user_id и amount должны быть числами.")
        return

    reason = " ".join(context.args[2:]).strip() or "crystal_exchange"
    storage = context.application.bot_data["storage"]
    ok, balance = storage.spend_reputation(
        user_id=user_id,
        amount=amount,
        admin_id=update.effective_user.id,
        reason=reason,
    )
    if not ok:
        await update.effective_message.reply_text(
            f"Не удалось списать репутацию. Текущий баланс: {balance}"
        )
        return

    await update.effective_message.reply_text(
        f"Списано очков репутации: {amount}. Новый баланс: {balance}"
    )


async def rep_reactions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update, context):
        return

    config = context.application.bot_data["config"]
    reactions = list(config.reputation.positive_reactions)
    await update.effective_message.reply_text(
        "Репутационные реакции: " + (" ".join(reactions) if reactions else "список пуст")
    )


async def rep_reaction_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update, context):
        return

    additions = [item.strip() for item in context.args if item.strip()]
    if not additions:
        await update.effective_message.reply_text("Использование: /rep_reaction_add 👍")
        return

    config = context.application.bot_data["config"]
    reactions = list(config.reputation.positive_reactions)
    added: list[str] = []
    for reaction in additions:
        if reaction not in reactions:
            reactions.append(reaction)
            added.append(reaction)

    save_reputation_reactions(reactions)
    context.application.bot_data["config"] = load_config()
    if added:
        await update.effective_message.reply_text("Добавлены реакции: " + " ".join(added))
    else:
        await update.effective_message.reply_text("Эти реакции уже есть в белом списке.")


async def rep_reaction_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update, context):
        return

    removals = [item.strip() for item in context.args if item.strip()]
    if not removals:
        await update.effective_message.reply_text("Использование: /rep_reaction_remove 🔥")
        return

    config = context.application.bot_data["config"]
    reactions = [reaction for reaction in config.reputation.positive_reactions if reaction not in removals]
    if not reactions:
        await update.effective_message.reply_text("Нельзя удалить все реакции. В списке должна остаться хотя бы одна.")
        return

    save_reputation_reactions(reactions)
    context.application.bot_data["config"] = load_config()
    removed = [reaction for reaction in removals if reaction in config.reputation.positive_reactions]
    if removed:
        await update.effective_message.reply_text("Удалены реакции: " + " ".join(removed))
    else:
        await update.effective_message.reply_text("Таких реакций не было в белом списке.")
