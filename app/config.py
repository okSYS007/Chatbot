from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


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


DEFAULT_POSITIVE_REACTIONS = ("👍", "❤️", "🔥")


def _as_int_set(values: list[Any] | None) -> set[int]:
    return {int(value) for value in values or [] if str(value).strip()}


def _clean_reactions(values: list[Any] | tuple[Any, ...] | set[Any] | None) -> list[str]:
    reactions: list[str] = []
    for value in values or []:
        reaction = str(value).strip()
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
        return yaml.safe_load(file) or {}


def save_reputation_reactions(reactions: list[str] | tuple[str, ...], path: str = "config.yaml") -> list[str]:
    cleaned = _clean_reactions(reactions)
    if not cleaned:
        raise ValueError("Reaction list cannot be empty.")

    raw = _read_yaml_config(path)
    raw.setdefault("reputation", {})["positive_reactions"] = cleaned
    Path(path).write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return cleaned


def save_admin_user_ids(user_ids: list[int] | tuple[int, ...] | set[int], path: str = "config.yaml") -> list[int]:
    cleaned = sorted({int(user_id) for user_id in user_ids if int(user_id) > 0})
    if not cleaned:
        raise ValueError("Admin list cannot be empty.")

    raw = _read_yaml_config(path)
    raw.setdefault("admins", {})["user_ids"] = cleaned
    Path(path).write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
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

    return AppConfig(
        telegram=TelegramConfig(token=token, chat_id=chat_id),
        admins=AdminConfig(user_ids=_as_int_set(admins_raw.get("user_ids"))),
        welcome=WelcomeConfig(
            enabled=bool(welcome_raw.get("enabled", True)),
            text=str(welcome_raw.get("text", "Привет, {name}! Добро пожаловать в группу.")),
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
    )
