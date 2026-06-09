from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import ReputationConfig, normalize_reaction


@dataclass(frozen=True)
class ReputationDecision:
    accepted: bool
    weight: int = 0
    reason: str = "unknown"


def parse_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_active(user: dict[str, Any] | None, config: ReputationConfig, now: datetime) -> bool:
    if not user or user.get("is_blocked"):
        return False

    if int(user.get("message_count") or 0) >= config.active_min_messages:
        return True

    first_seen = parse_utc(user.get("first_seen_at"))
    if first_seen and now - first_seen >= timedelta(days=config.active_min_days):
        return True

    return False


def reputation_weight(author: dict[str, Any] | None, config: ReputationConfig) -> int:
    weight = config.points_per_admin_reaction
    if config.subscription_bonus_enabled and author and author.get("subscription_active"):
        weight *= config.subscription_multiplier
    return weight


def decide_reputation(
    state: dict[str, Any],
    config: ReputationConfig,
    trusted_reactor_ids: set[int],
    reactor_id: int,
    author_id: int,
    reaction: str,
    reaction_key: str,
) -> ReputationDecision:
    if not config.enabled:
        return ReputationDecision(False, reason="disabled")
    reaction = normalize_reaction(reaction)
    positive_reactions = {normalize_reaction(item) for item in config.positive_reactions}
    if reaction not in positive_reactions:
        return ReputationDecision(False, reason="not_positive")
    if reaction_key in state.get("counted_reactions", {}):
        return ReputationDecision(False, reason="duplicate_reaction")

    users = state.get("users", {})
    author = users.get(str(author_id))
    if not author:
        return ReputationDecision(False, reason="unknown_author")

    pair_key = f"{reactor_id}:{author_id}"
    now = datetime.now(UTC)
    last_pair_at = parse_utc(state.get("rep_cooldowns", {}).get(pair_key))
    if config.cooldown_days > 0 and last_pair_at and now - last_pair_at < timedelta(days=config.cooldown_days):
        return ReputationDecision(False, reason="cooldown")

    if reactor_id not in trusted_reactor_ids:
        return ReputationDecision(False, reason="not_admin_reaction")

    return ReputationDecision(True, weight=reputation_weight(author, config), reason="admin_reaction")
