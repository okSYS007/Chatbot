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
                "Bot is running.",
                f"Users in JSON: {len(state.get('users', {}))}",
                f"Last update_id: {meta.get('last_update_id')}",
                f"Last update: {meta.get('last_seen_update_at')}",
            ]
        )
    )


async def top_rep(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    storage = context.application.bot_data["storage"]
    users = list(storage.snapshot().get("users", {}).values())
    users.sort(key=lambda item: int(item.get("reputation") or 0), reverse=True)
    top = users[:10]
    if not top:
        await update.effective_message.reply_text("No reputation data yet.")
        return

    lines = ["Top reputation:"]
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
        await update.effective_message.reply_text("Use: /rep 123456789")
        return

    user = storage.get_user(target_id)
    if not user:
        await update.effective_message.reply_text("No data for this user yet.")
        return

    await update.effective_message.reply_text(
        "\n".join(
            [
                f"User: {user.get('display_name') or user.get('username') or target_id}",
                f"Reputation: {user.get('reputation', 0)}",
                f"Messages: {user.get('message_count', 0)}",
                f"Counted likes: {user.get('likes_received', 0)}",
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
            "Use: /set_welcome Hello, {name}! Welcome."
        )
        return

    storage = context.application.bot_data["storage"]
    storage.set_setting("welcome_text", text)
    await update.effective_message.reply_text("Welcome text updated.")


async def reset_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update, context):
        return

    if not context.args or context.args[0] != "CONFIRM":
        await update.effective_message.reply_text(
            "This clears users and reputation only. To confirm: /reset_users CONFIRM"
        )
        return

    storage = context.application.bot_data["storage"]
    storage.reset_user_data()
    await update.effective_message.reply_text("Users and reputation data cleared.")


async def spend_rep(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update, context):
        return

    if not update.effective_user:
        return

    if len(context.args) < 2:
        await update.effective_message.reply_text("Use: /spend_rep user_id amount [reason]")
        return

    try:
        user_id = int(context.args[0])
        amount = int(context.args[1])
    except ValueError:
        await update.effective_message.reply_text("user_id and amount must be numbers.")
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
            f"Cannot spend reputation. Current balance: {balance}"
        )
        return

    await update.effective_message.reply_text(
        f"Spent {amount} reputation points. New balance: {balance}"
    )
