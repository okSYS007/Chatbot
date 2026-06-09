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

    def reload(self) -> None:
        self.state = self._load()
        self._migrate()

    def _migrate(self) -> None:
        changed = False
        base = default_state()
        for key, value in base.items():
            if key not in self.state:
                self.state[key] = value
                changed = True
        for key, value in base["meta"].items():
            if key not in self.state["meta"]:
                self.state["meta"][key] = value
                changed = True
        counted_reactions = self.state.get("counted_reactions", {})
        if isinstance(counted_reactions, dict):
            for key, value in list(counted_reactions.items()):
                if isinstance(value, str):
                    counted_reactions.pop(key, None)
                    changed = True
        if changed:
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
        self.reload()
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
                "subscription_active": False,
                "welcomed": False,
            }
        else:
            users[key]["username"] = telegram_user.username
            users[key]["display_name"] = telegram_user.full_name
            users[key]["last_seen_at"] = now

        return users[key]

    def get_user(self, user_id: int) -> dict[str, Any] | None:
        self.reload()
        return self.state["users"].get(str(user_id))

    def increment_message_count(self, telegram_user: Any, message_key: str | None = None) -> None:
        self.reload()
        user = self.ensure_user(telegram_user)
        user["message_count"] = int(user.get("message_count") or 0) + 1
        if message_key:
            self.state["message_authors"][message_key] = int(telegram_user.id)
        self.save()

    def mark_welcomed(self, telegram_user: Any) -> bool:
        self.reload()
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
        self.reload()
        return deepcopy(self.state)

    def get_setting(self, key: str, default: Any = None) -> Any:
        self.reload()
        return self.state.get("settings", {}).get(key, default)

    def set_setting(self, key: str, value: Any) -> None:
        self.reload()
        self.state.setdefault("settings", {})[key] = value
        self.save()

    def reset_user_data(self) -> None:
        self.reload()
        self.state["users"] = {}
        self.state["rep_cooldowns"] = {}
        self.state["counted_reactions"] = {}
        self.state["message_authors"] = {}
        self.state["pending_reactions"] = []
        self.state["rep_events"] = []
        self.save()

    def spend_reputation(self, user_id: int, amount: int, admin_id: int, reason: str) -> tuple[bool, int]:
        self.reload()
        user = self.get_user(user_id)
        if not user:
            return False, 0

        current = int(user.get("reputation") or 0)
        if amount <= 0 or current < amount:
            return False, current

        user["reputation"] = current - amount
        self.state["rep_events"].append(
            {
                "at": utc_now(),
                "admin_id": admin_id,
                "author_id": user_id,
                "weight": -amount,
                "reason": reason or "crystal_exchange",
            }
        )
        self.state["rep_events"] = self.state["rep_events"][-200:]
        self.save()
        return True, int(user["reputation"])

    def add_reputation(self, user_id: int, amount: int, admin_id: int, reason: str) -> tuple[bool, int]:
        self.reload()
        if amount <= 0:
            user = self.get_user(user_id)
            return False, int(user.get("reputation") or 0) if user else 0

        user = self.state["users"].setdefault(
            str(user_id),
            {
                "user_id": user_id,
                "username": None,
                "display_name": str(user_id),
                "first_seen_at": utc_now(),
                "last_seen_at": utc_now(),
                "message_count": 0,
                "reputation": 0,
                "likes_received": 0,
                "likes_given": 0,
                "is_moderator": False,
                "is_blocked": False,
                "subscription_active": False,
                "welcomed": False,
            },
        )
        user["reputation"] = int(user.get("reputation") or 0) + amount
        self.state["rep_events"].append(
            {
                "at": utc_now(),
                "admin_id": admin_id,
                "author_id": user_id,
                "weight": amount,
                "reason": reason or "manual_admin_add",
            }
        )
        self.state["rep_events"] = self.state["rep_events"][-200:]
        self.save()
        return True, int(user["reputation"])

    def record_reputation(
        self,
        reactor_id: int,
        author_id: int,
        reaction_key: str,
        pair_key: str,
        reaction: str,
        weight: int,
        reason: str,
    ) -> None:
        self.reload()
        now = utc_now()
        author = self.state["users"].setdefault(str(author_id), {"user_id": author_id})
        reactor = self.state["users"].setdefault(str(reactor_id), {"user_id": reactor_id})

        author["reputation"] = int(author.get("reputation") or 0) + weight
        author["likes_received"] = int(author.get("likes_received") or 0) + 1
        reactor["likes_given"] = int(reactor.get("likes_given") or 0) + 1
        self.state["counted_reactions"][reaction_key] = {
            "type": "reputation_grant",
            "at": now,
            "reactor_id": reactor_id,
            "author_id": author_id,
            "reaction": reaction,
            "weight": weight,
            "pair_key": pair_key,
        }
        self.state["rep_cooldowns"][pair_key] = now
        self.state["rep_events"].append(
            {
                "at": now,
                "reactor_id": reactor_id,
                "author_id": author_id,
                "reaction_key": reaction_key,
                "reaction": reaction,
                "weight": weight,
                "reason": reason,
            }
        )
        self.state["rep_events"] = self.state["rep_events"][-200:]
        self.save()

    def rollback_reputation_reaction(self, reaction_key: str, reactor_id: int, reason: str) -> tuple[bool, int]:
        self.reload()
        record = self.state.get("counted_reactions", {}).get(reaction_key)
        if not isinstance(record, dict) or record.get("type") != "reputation_grant":
            return False, 0
        if int(record.get("reactor_id") or 0) != int(reactor_id):
            return False, 0

        author_id = int(record.get("author_id") or 0)
        weight = int(record.get("weight") or 0)
        if not author_id or weight <= 0:
            return False, 0

        author = self.state["users"].setdefault(str(author_id), {"user_id": author_id})
        reactor = self.state["users"].setdefault(str(reactor_id), {"user_id": reactor_id})
        author["reputation"] = int(author.get("reputation") or 0) - weight
        author["likes_received"] = max(0, int(author.get("likes_received") or 0) - 1)
        reactor["likes_given"] = max(0, int(reactor.get("likes_given") or 0) - 1)

        pair_key = str(record.get("pair_key") or "")
        if pair_key:
            self.state["rep_cooldowns"].pop(pair_key, None)
        self.state["counted_reactions"].pop(reaction_key, None)
        self.state["rep_events"].append(
            {
                "at": utc_now(),
                "reactor_id": reactor_id,
                "author_id": author_id,
                "reaction_key": reaction_key,
                "reaction": record.get("reaction"),
                "weight": -weight,
                "reason": reason,
                "rollback_of": reaction_key,
            }
        )
        self.state["rep_events"] = self.state["rep_events"][-200:]
        self.save()
        return True, int(author["reputation"])

    def record_counted_reaction(self, reaction_key: str, reason: str) -> None:
        self.reload()
        self.state["counted_reactions"].setdefault(reaction_key, reason)
        self.save()
