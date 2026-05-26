from __future__ import annotations

from telegram import ReactionTypeEmoji, Update
from telegram.ext import ContextTypes

from app.handlers.common import is_target_chat
from app.reputation import decide_reputation


def _emoji_values(reactions: tuple[object, ...] | list[object]) -> set[str]:
    values: set[str] = set()
    for reaction in reactions:
        if isinstance(reaction, ReactionTypeEmoji):
            values.add(reaction.emoji)
        else:
            emoji = getattr(reaction, "emoji", None)
            if emoji:
                values.add(str(emoji))
    return values


async def handle_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_target_chat(update, context) or not update.message_reaction:
        return

    event = update.message_reaction
    if not event.user:
        return

    storage = context.application.bot_data["storage"]
    config = context.application.bot_data["config"]
    reactor = event.user
    storage.ensure_user(reactor)

    old_reactions = _emoji_values(event.old_reaction)
    new_reactions = _emoji_values(event.new_reaction)
    added = new_reactions - old_reactions
    if not added:
        return

    author_id = storage.state["message_authors"].get(f"{event.chat.id}:{event.message_id}")
    if not author_id:
        return

    for reaction in added:
        reaction_key = f"{event.chat.id}:{event.message_id}:{reactor.id}:{reaction}"
        pair_key = f"{reactor.id}:{author_id}"
        decision = decide_reputation(
            storage.snapshot(),
            config.reputation,
            reactor_id=reactor.id,
            author_id=int(author_id),
            reaction=reaction,
            reaction_key=reaction_key,
        )
        if decision.accepted:
            storage.record_reputation(
                reactor_id=reactor.id,
                author_id=int(author_id),
                reaction_key=reaction_key,
                pair_key=pair_key,
                weight=decision.weight,
                reason=decision.reason,
            )
        else:
            storage.record_counted_reaction(reaction_key, decision.reason)
