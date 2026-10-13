from __future__ import annotations

import os
import re
import string
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from dotenv import load_dotenv

from app.card_matching import validate_patterns


@dataclass(frozen=True)
class TelegramConfig:
    token: str
    chat_id: int


@dataclass(frozen=True)
class AdminConfig:
    user_ids: set[int] = field(default_factory=set)


@dataclass(frozen=True)
class WelcomeConfig:
    enabled: bool
    text: str
    texts: tuple[str, ...] = ()


@dataclass(frozen=True)
class DailyCardConfig:
    enabled: bool = False
    folder: Path = Path("cards/day")
    chat_id: int = 0
    message_thread_id: int | None = None
    time: str = "09:00"
    timezone: str = "Europe/Kyiv"
    caption: str = "Карта дня: {name}"
    images_folder: Path | None = None
    texts_folder: Path | None = None
    patterns: tuple[str, ...] = ()

    @property
    def uses_patterns(self) -> bool:
        return self.images_folder is not None or self.texts_folder is not None or bool(self.patterns)


@dataclass(frozen=True)
class ReputationConfig:
    enabled: bool
    admin_only: bool
    positive_reactions: tuple[str, ...]
    points_per_admin_reaction: int
    subscription_bonus_enabled: bool
    subscription_multiplier: int
    cooldown_days: int
    active_min_messages: int
    active_min_days: int
    regular_weight: int
    moderator_weight: int
    moderators: set[int]


@dataclass(frozen=True)
class StorageConfig:
    path: Path


@dataclass(frozen=True)
class LoggingConfig:
    path: Path


@dataclass(frozen=True)
class AppConfig:
    telegram: TelegramConfig
    admins: AdminConfig
    welcome: WelcomeConfig
    reputation: ReputationConfig
    storage: StorageConfig
    logging: LoggingConfig
    daily_card: DailyCardConfig = field(default_factory=DailyCardConfig)


DEFAULT_POSITIVE_REACTIONS = ("👍", "❤️", "🔥")


def normalize_reaction(value: str) -> str:
    return value.replace("\ufe0f", "").replace("\ufe0e", "")


def _repair_mojibake(value: str) -> str:
    try:
        return value.encode("cp1251").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def _as_int_set(values: list[Any] | None) -> set[int]:
    return {int(value) for value in values or [] if str(value).strip()}


def _clean_reactions(values: list[Any] | tuple[Any, ...] | set[Any] | None) -> list[str]:
    reactions: list[str] = []
    for value in values or []:
        reaction = normalize_reaction(_repair_mojibake(str(value).strip()))
        if reaction and reaction not in reactions:
            reactions.append(reaction)
    return reactions


def _read_yaml_config(path: str = "config.yaml") -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        config_path = Path("config.example.yaml")

    if not config_path.exists():
        return {}

    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}
    if not isinstance(raw, dict):
        raise ValueError("Конфигурация должна быть YAML-словарём.")
    return raw


def _write_yaml_config(raw: dict[str, Any], path: str) -> None:
    config_path = Path(path)
    tmp_path = config_path.with_suffix(config_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as file:
        file.write(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False))
        file.flush()
        os.fsync(file.fileno())
    os.replace(tmp_path, config_path)


def parse_daily_card(raw: dict[str, Any]) -> DailyCardConfig:
    if not isinstance(raw, dict):
        raise ValueError("daily_card должен быть YAML-словарём.")
    enabled = raw.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValueError("daily_card.enabled должен быть true или false.")
    clock = str(raw.get("time", "09:00"))
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", clock):
        raise ValueError("Время карты дня указывается в формате ЧЧ:ММ (00:00–23:59).")
    timezone = str(raw.get("timezone", "Europe/Kyiv"))
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("Неизвестный часовой пояс. Пример: Europe/Kyiv.") from exc
    try:
        chat_id = int(raw.get("chat_id", 0) or 0)
        topic_id = int(raw.get("message_thread_id", 0) or 0) or None
    except (TypeError, ValueError) as exc:
        raise ValueError("ID чата и темы должны быть целыми числами.") from exc
    if topic_id is not None and topic_id < 1:
        raise ValueError("ID темы должен быть положительным числом или пустым.")
    if enabled and not chat_id:
        raise ValueError("Перед включением карты дня укажите ID чата.")
    new_keys = {"images_folder", "texts_folder", "patterns"}
    new_mode = bool(new_keys.intersection(raw))
    if new_mode:
        image_value = raw.get("images_folder", "cards/images")
        text_value = raw.get("texts_folder", "cards/texts")
        if not isinstance(image_value, str) or not image_value.strip():
            raise ValueError("Укажите папку с картинками карт дня.")
        if not isinstance(text_value, str) or not text_value.strip():
            raise ValueError("Укажите папку с текстами карт дня.")
        pattern_values = raw.get("patterns", [])
        if not isinstance(pattern_values, list):
            raise ValueError("daily_card.patterns должен быть списком строк.")
        try:
            patterns = validate_patterns(pattern_values)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Некорректные шаблоны карт: {exc}") from exc
        if enabled and not patterns:
            raise ValueError("Перед включением карты дня добавьте хотя бы один шаблон.")
        images_folder = Path(image_value.strip())
        texts_folder = Path(text_value.strip())
    else:
        images_folder = texts_folder = None
        patterns = ()

    folder = raw.get("folder", "cards/day")
    if not isinstance(folder, str):
        raise ValueError("Папка с картами дня должна быть строкой.")
    folder = folder.strip()
    if not folder:
        raise ValueError("Укажите папку с картами дня.")
    caption = str(raw.get("caption", "Карта дня: {name}"))
    try:
        for _, name, spec, conversion in string.Formatter().parse(caption):
            if name is not None and (name not in {"name", "date"} or spec or conversion):
                raise ValueError("В подписи разрешены только {name} и {date}, без форматов.")
    except ValueError as exc:
        raise ValueError("Некорректная подпись карты: используйте {name} и {date}.") from exc
    if len(caption.encode("utf-16-le")) // 2 > 1024:
        raise ValueError("Подпись карты не должна превышать 1024 символа Telegram.")
    return DailyCardConfig(
        enabled=enabled,
        folder=Path(folder),
        chat_id=chat_id,
        message_thread_id=topic_id,
        time=clock,
        timezone=timezone,
        caption=caption,
        images_folder=images_folder,
        texts_folder=texts_folder,
        patterns=patterns,
    )


def save_daily_card(values: dict[str, Any], path: str = "config.yaml") -> DailyCardConfig:
    raw = _read_yaml_config(path)
    section = {**raw.get("daily_card", {}), **values}
    config = parse_daily_card(section)
    raw["daily_card"] = section
    _write_yaml_config(raw, path)
    return config


def save_reputation_reactions(reactions: list[str] | tuple[str, ...], path: str = "config.yaml") -> list[str]:
    cleaned = _clean_reactions(reactions)
    if not cleaned:
        raise ValueError("Reaction list cannot be empty.")

    raw = _read_yaml_config(path)
    raw.setdefault("reputation", {})["positive_reactions"] = cleaned
    _write_yaml_config(raw, path)
    return cleaned


def save_admin_user_ids(user_ids: list[int] | tuple[int, ...] | set[int], path: str = "config.yaml") -> list[int]:
    cleaned = sorted({int(user_id) for user_id in user_ids if int(user_id) > 0})
    if not cleaned:
        raise ValueError("Admin list cannot be empty.")

    raw = _read_yaml_config(path)
    raw.setdefault("admins", {})["user_ids"] = cleaned
    _write_yaml_config(raw, path)
    return cleaned


def load_config(path: str = "config.yaml") -> AppConfig:
    load_dotenv()
    raw = _read_yaml_config(path)

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token or token == "put_your_bot_token_here":
        raise RuntimeError("Set TELEGRAM_BOT_TOKEN in .env before starting the bot.")

    telegram_raw = raw.get("telegram", {})
    chat_id = int(os.getenv("TELEGRAM_CHAT_ID", telegram_raw.get("chat_id", 0)) or 0)

    admins_raw = raw.get("admins", {})
    welcome_raw = raw.get("welcome", {})
    rep_raw = raw.get("reputation", {})
    storage_raw = raw.get("storage", {})
    logging_raw = raw.get("logging", {})
    welcome_texts = welcome_raw.get("texts", []) or []
    if not isinstance(welcome_texts, list) or any(not isinstance(text, str) or not text.strip() for text in welcome_texts):
        raise ValueError("welcome.texts должен быть списком непустых строк.")

    return AppConfig(
        telegram=TelegramConfig(token=token, chat_id=chat_id),
        admins=AdminConfig(user_ids=_as_int_set(admins_raw.get("user_ids"))),
        welcome=WelcomeConfig(
            enabled=bool(welcome_raw.get("enabled", True)),
            text=str(welcome_raw.get("text", "Привет, {name}! Добро пожаловать в группу.")),
            texts=tuple(welcome_texts),
        ),
        reputation=ReputationConfig(
            enabled=bool(rep_raw.get("enabled", True)),
            admin_only=bool(rep_raw.get("admin_only", True)),
            positive_reactions=tuple(_clean_reactions(rep_raw.get("positive_reactions")) or DEFAULT_POSITIVE_REACTIONS),
            points_per_admin_reaction=int(rep_raw.get("points_per_admin_reaction", 1)),
            subscription_bonus_enabled=bool(rep_raw.get("subscription_bonus_enabled", False)),
            subscription_multiplier=int(rep_raw.get("subscription_multiplier", 2)),
            cooldown_days=int(rep_raw.get("cooldown_days", 0)),
            active_min_messages=int(rep_raw.get("active_min_messages", 20)),
            active_min_days=int(rep_raw.get("active_min_days", 14)),
            regular_weight=int(rep_raw.get("regular_weight", 1)),
            moderator_weight=int(rep_raw.get("moderator_weight", 2)),
            moderators=_as_int_set(rep_raw.get("moderators")),
        ),
        storage=StorageConfig(path=Path(storage_raw.get("path", "data/state.json"))),
        logging=LoggingConfig(path=Path(logging_raw.get("path", "logs/bot.log"))),
        daily_card=parse_daily_card(raw.get("daily_card", {})),
    )
