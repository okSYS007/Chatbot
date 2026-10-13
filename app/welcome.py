from __future__ import annotations

import random
import string
import logging
from typing import Any, Iterable

from telegram import Chat, User

logger = logging.getLogger(__name__)

WELCOME_PLACEHOLDERS = frozenset({"name", "username", "user_id", "group"})
MAX_TELEGRAM_TEXT_LENGTH = 4096


def validate_welcome_template(template: str) -> str | None:
    if not isinstance(template, str) or not template.strip():
        return "Текст приветствия не может быть пустым."
    if len(template.encode("utf-16-le")) > MAX_TELEGRAM_TEXT_LENGTH * 2:
        return "Текст приветствия не должен быть длиннее 4096 символов."
    try:
        fields = set()
        for _, field, format_spec, conversion in string.Formatter().parse(template):
            if field is None:
                continue
            if not field or conversion or format_spec or not field.isidentifier():
                return "Разрешены только простые шаблоны {name}, {username}, {user_id}, {group}."
            fields.add(field)
    except ValueError:
        return "В шаблоне некорректные фигурные скобки."
    unknown = fields - WELCOME_PLACEHOLDERS
    if unknown:
        return "Неизвестные шаблоны: " + ", ".join("{" + item + "}" for item in sorted(unknown))
    return None


def validate_welcome_templates(templates: Iterable[str]) -> tuple[list[str], str | None]:
    values = [str(item).strip() for item in templates]
    if not values or any(not item for item in values):
        return [], "Список приветствий не может быть пустым."
    for index, template in enumerate(values, start=1):
        error = validate_welcome_template(template)
        if error:
            return [], f"Вариант {index}: {error}"
    return values, None


def get_welcome_templates(config: Any, storage: Any) -> list[str]:
    settings = storage.snapshot().get("settings", {})
    saved = settings.get("welcome_texts")
    if isinstance(saved, list) and saved:
        return [str(item) for item in saved]
    legacy = settings.get("welcome_text")
    if isinstance(legacy, str) and legacy.strip():
        return [legacy]
    configured = getattr(config.welcome, "texts", ())
    if configured:
        return [str(item) for item in configured]
    return [str(config.welcome.text)]


def get_welcome_text(config: Any, storage: Any) -> str:
    templates = get_welcome_templates(config, storage)
    valid = [item for item in templates if validate_welcome_template(item) is None]
    if not valid:
        logger.warning("all welcome templates are invalid; using safe fallback")
        return "Привет, {name}! Добро пожаловать в группу."
    return random.choice(valid)


def _truncate_telegram_text(text: str) -> str:
    raw = text.encode("utf-16-le")
    if len(raw) <= MAX_TELEGRAM_TEXT_LENGTH * 2:
        return text
    return raw[: MAX_TELEGRAM_TEXT_LENGTH * 2].decode("utf-16-le", errors="ignore")


def render_welcome(template: str, user: User, chat: Chat) -> str:
    if validate_welcome_template(template) is not None:
        logger.warning("invalid welcome template encountered during rendering")
        template = "Привет, {name}! Добро пожаловать в группу."
    username = f"@{user.username}" if user.username else user.full_name
    try:
        rendered = template.format(
            name=user.full_name,
            username=username,
            user_id=user.id,
            group=chat.title or "группу",
        )
    except (KeyError, ValueError, IndexError):
        logger.warning("invalid welcome template encountered during rendering")
        rendered = "Привет, {name}! Добро пожаловать в группу.".format(name=user.full_name)
    return _truncate_telegram_text(rendered)
