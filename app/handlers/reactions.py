from __future__ import annotations

import logging

from telegram import ReactionTypeEmoji, Update
from telegram.ext import ContextTypes

from app.config import normalize_reaction
from app.handlers.common import is_target_chat
from app.reputation import decide_reputation


logger = logging.getLogger(__name__)


def _emoji_values(reactions: tuple[object, ...] | list[object]) -> set[str]:
    values: set[str] = set()
    for reaction in reactions:
        if isinstance(reaction, ReactionTypeEmoji):
            values.add(normalize_reaction(reaction.emoji))
        else:
            emoji = getattr(reaction, "emoji", None)
            if emoji:
                values.add(normalize_reaction(str(emoji)))
    return values


def reaction_key(chat_id: int, message_id: int, reactor_id: int, reaction: str) -> str:
    return f"{chat_id}:{message_id}:{reactor_id}:{reaction}"


async def handle_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_target_chat(update, context) or not update.message_reaction:
        return

    event = update.message_reaction
    if not event.user:
        logger.info(
            "Реакция пропущена: Telegram не передал пользователя, chat_id=%s message_id=%s",
            event.chat.id,
            event.message_id,
        )
        return

    storage = context.application.bot_data["storage"]
    config = context.application.bot_data["config"]
    reactor = event.user
    storage.ensure_user(reactor)

    old_reactions = _emoji_values(event.old_reaction)
    new_reactions = _emoji_values(event.new_reaction)
    added = new_reactions - old_reactions
    removed = old_reactions - new_reactions
    if not added and not removed:
        return

    for reaction in removed:
        rolled_back, new_reputation = storage.rollback_reputation_reaction(
            reaction_key=reaction_key(event.chat.id, event.message_id, reactor.id, reaction),
            reactor_id=reactor.id,
            reason="reaction_removed",
        )
        if rolled_back:
            logger.info(
                "Репутация откатилась: reactor_id=%s reaction=%s chat_id=%s message_id=%s new_reputation=%s",
                reactor.id,
                reaction,
                event.chat.id,
                event.message_id,
                new_reputation,
            )
        else:
            logger.info(
                "Откат реакции пропущен: ранее эта реакция не начисляла репутацию, reactor_id=%s reaction=%s chat_id=%s message_id=%s",
                reactor.id,
                reaction,
                event.chat.id,
                event.message_id,
            )

    if not added:
        return

    state = storage.snapshot()
    author_id = state.get("message_authors", {}).get(f"{event.chat.id}:{event.message_id}")
    if not author_id:
        logger.info(
            "Реакция пропущена: бот не знает автора сообщения, reactor_id=%s reactions=%s chat_id=%s message_id=%s",
            reactor.id,
            sorted(added),
            event.chat.id,
            event.message_id,
        )
        return

    for reaction in added:
        if reaction not in config.reputation.positive_reactions:
            logger.info(
                "Реакция пропущена: emoji нет в белом списке, reactor_id=%s reaction=%s allowed=%s",
                reactor.id,
                reaction,
                list(config.reputation.positive_reactions),
            )
            continue

        key = reaction_key(event.chat.id, event.message_id, reactor.id, reaction)
        pair_key = f"{reactor.id}:{author_id}"
        decision = decide_reputation(
            storage.snapshot(),
            config.reputation,
            trusted_reactor_ids=config.admins.user_ids,
            reactor_id=reactor.id,
            author_id=int(author_id),
            reaction=reaction,
            reaction_key=key,
        )
        if decision.accepted:
            storage.record_reputation(
                reactor_id=reactor.id,
                author_id=int(author_id),
                reaction_key=key,
                pair_key=pair_key,
                reaction=reaction,
                weight=decision.weight,
                reason=decision.reason,
            )
            logger.info(
                "Репутация начислена: author_id=%s reactor_id=%s reaction=%s weight=%s",
                author_id,
                reactor.id,
                reaction,
                decision.weight,
            )
        else:
            logger.info(
                "Реакция не начислила репутацию: reason=%s author_id=%s reactor_id=%s reaction=%s",
                decision.reason,
                author_id,
                reactor.id,
                reaction,
            )
