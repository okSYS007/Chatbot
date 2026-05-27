from __future__ import annotations

import json
import os
import shutil
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_state() -> dict[str, Any]:
    return {
        "meta": {
            "last_update_id": 0,
            "started_at": None,
            "last_seen_update_at": None,
        },
        "users": {},
        "rep_cooldowns": {},
        "counted_reactions": {},
        "message_authors": {},
        "pending_reactions": [],
        "rep_events": [],
        "settings": {},
    }


class JsonStorage:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state = self._load()
        self._migrate()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return default_state()

        with self.path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _migrate(self) -> None:
        base = default_state()
        for key, value in base.items():
            self.state.setdefault(key, value)
        for key, value in base["meta"].items():
            self.state["meta"].setdefault(key, value)
        self.save()

    def save(self) -> None:
        tmp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        backup_path = self.path.with_name(self.path.stem + ".backup" + self.path.suffix)

        if self.path.exists():
            shutil.copy2(self.path, backup_path)

        with tmp_path.open("w", encoding="utf-8") as file:
            json.dump(self.state, file, ensure_ascii=False, indent=2)

        os.replace(tmp_path, self.path)

    def remember_update(self, update_id: int) -> None:
        if update_id > int(self.state["meta"].get("last_update_id") or 0):
            self.state["meta"]["last_update_id"] = update_id
            self.state["meta"]["last_seen_update_at"] = utc_now()
            self.save()

    def ensure_user(self, telegram_user: Any, now: str | None = None) -> dict[str, Any]:
        now = now or utc_now()
        user_id = int(telegram_user.id)
        key = str(user_id)
        users = self.state["users"]
        if key not in users:
            users[key] = {
                "user_id": user_id,
                "username": telegram_user.username,
                "display_name": telegram_user.full_name,
                "first_seen_at": now,
                "last_seen_at": now,
                "message_count": 0,
                "reputation": 0,
                "likes_received": 0,
                "likes_given": 0,
                "is_moderator": False,
                "is_blocked": False,
                "welcomed": False,
            }
        else:
            users[key]["username"] = telegram_user.username
            users[key]["display_name"] = telegram_user.full_name
            users[key]["last_seen_at"] = now

        return users[key]

    def get_user(self, user_id: int) -> dict[str, Any] | None:
        return self.state["users"].get(str(user_id))

    def increment_message_count(self, telegram_user: Any, message_key: str | None = None) -> None:
        user = self.ensure_user(telegram_user)
        user["message_count"] = int(user.get("message_count") or 0) + 1
        if message_key:
            self.state["message_authors"][message_key] = int(telegram_user.id)
        self.save()

    def mark_welcomed(self, telegram_user: Any) -> bool:
        user = self.ensure_user(telegram_user)
        if user.get("welcomed"):
            self.save()
            return False
        user["welcomed"] = True
        self.save()
        return True

    def set_started(self) -> None:
        self.state["meta"]["started_at"] = utc_now()
        self.save()

    def snapshot(self) -> dict[str, Any]:
        return deepcopy(self.state)

    def get_setting(self, key: str, default: Any = None) -> Any:
        return self.state.get("settings", {}).get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        self.state.setdefault("settings", {})[key] = value
        self.save()

    def reset_user_data(self) -> None:
        self.state["users"] = {}
        self.state["rep_cooldowns"] = {}
        self.state["counted_reactions"] = {}
        self.state["message_authors"] = {}
        self.state["pending_reactions"] = []
        self.state["rep_events"] = []
        self.save()

    def record_reputation(
        self,
        reactor_id: int,
        author_id: int,
        reaction_key: str,
        pair_key: str,
        weight: int,
        reason: str,
    ) -> None:
        now = utc_now()
        author = self.state["users"].setdefault(str(author_id), {"user_id": author_id})
        reactor = self.state["users"].setdefault(str(reactor_id), {"user_id": reactor_id})

        author["reputation"] = int(author.get("reputation") or 0) + weight
        author["likes_received"] = int(author.get("likes_received") or 0) + 1
        reactor["likes_given"] = int(reactor.get("likes_given") or 0) + 1
        self.state["counted_reactions"][reaction_key] = True
        self.state["rep_cooldowns"][pair_key] = now
        self.state["rep_events"].append(
            {
                "at": now,
                "reactor_id": reactor_id,
                "author_id": author_id,
                "reaction_key": reaction_key,
                "weight": weight,
                "reason": reason,
            }
        )
        self.state["rep_events"] = self.state["rep_events"][-200:]
        self.save()

    def record_counted_reaction(self, reaction_key: str, reason: str) -> None:
        self.state["counted_reactions"][reaction_key] = reason
        self.save()
