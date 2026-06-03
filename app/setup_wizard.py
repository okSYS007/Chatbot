from __future__ import annotations

import asyncio
from pathlib import Path

import yaml
from dotenv import dotenv_values
from telegram import Bot
from telegram.error import TelegramError


DEFAULT_WELCOME = "Привет, {name}! Добро пожаловать в группу."


def _read_existing_token() -> str:
    env_path = Path(".env")
    if not env_path.exists():
        return ""
    values = dotenv_values(env_path)
    return str(values.get("TELEGRAM_BOT_TOKEN") or "").strip()


def _prompt(message: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{message}{suffix}: ").strip()
    return value or default


def _yes_no(message: str, default: bool = True) -> bool:
    marker = "Y/n" if default else "y/N"
    value = input(f"{message} ({marker}): ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes", "д", "да"}


async def _detect_group(token: str) -> tuple[int | None, int | None]:
    bot = Bot(token)
    offset = None

    print()
    print("Теперь отправьте любое сообщение в нужную Telegram-группу.")
    print("Когда бот увидит группу, он покажет ее здесь.")
    print()

    for _ in range(18):
        updates = await bot.get_updates(
            offset=offset,
            timeout=10,
            allowed_updates=["message", "chat_member", "message_reaction"],
        )
        for update in updates:
            offset = update.update_id + 1
            chat = update.effective_chat
            user = update.effective_user
            if not chat or chat.type == "private":
                continue

            print(f"Найдена группа: {chat.title!r}")
            print(f"chat_id: {chat.id}")
            if user:
                print(f"Ваш user_id: {user.id}")
            if _yes_no("Использовать эту группу?", default=True):
                return chat.id, user.id if user else None

    print("Не удалось автоматически определить группу.")
    return None, None


def _write_env(token: str) -> None:
    Path(".env").write_text(f"TELEGRAM_BOT_TOKEN={token}\n", encoding="utf-8")


def _write_config(chat_id: int, admin_id: int, welcome_text: str) -> None:
    config = {
        "telegram": {
            "chat_id": chat_id,
        },
        "admins": {
            "user_ids": [admin_id],
        },
        "welcome": {
            "enabled": True,
            "text": welcome_text,
        },
        "reputation": {
            "enabled": True,
            "admin_only": True,
            "points_per_admin_reaction": 1,
            "subscription_bonus_enabled": False,
            "subscription_multiplier": 2,
            "positive_reactions": ["👍", "❤️", "🔥"],
            "cooldown_days": 0,
            "active_min_messages": 20,
            "active_min_days": 14,
            "regular_weight": 1,
            "moderator_weight": 1,
            "moderators": [admin_id],
        },
        "storage": {
            "path": "data/state.json",
        },
        "logging": {
            "path": "logs/bot.log",
        },
    }
    text = yaml.safe_dump(config, allow_unicode=True, sort_keys=False)
    Path("config.yaml").write_text(text, encoding="utf-8")


async def _setup() -> None:
    print("Настройка Telegram-бота")
    print("======================")
    print()

    Path("data").mkdir(exist_ok=True)
    Path("logs").mkdir(exist_ok=True)

    existing_token = _read_existing_token()
    token = _prompt("Вставьте токен бота из BotFather", existing_token)
    if not token:
        print("Токен не указан. Настройка остановлена.")
        return

    _write_env(token)

    chat_id: int | None = None
    admin_id: int | None = None

    if _yes_no("Определить chat_id автоматически?", default=True):
        try:
            chat_id, admin_id = await _detect_group(token)
        except TelegramError as exc:
            print(f"Telegram вернул ошибку: {exc}")

    if chat_id is None:
        chat_id = int(_prompt("Введите chat_id группы вручную"))

    if admin_id is None:
        admin_id = int(_prompt("Введите ваш Telegram user_id для админ-команд"))

    welcome_text = _prompt("Текст приветствия", DEFAULT_WELCOME)

    if Path("config.yaml").exists() and not _yes_no("config.yaml уже существует. Перезаписать?", default=False):
        print("config.yaml не изменен.")
        return

    _write_config(chat_id=chat_id, admin_id=admin_id, welcome_text=welcome_text)

    print()
    print("Готово.")
    print("Теперь откроется админ-панель. Пока окно открыто, бот работает.")


def run_setup_wizard() -> None:
    asyncio.run(_setup())
