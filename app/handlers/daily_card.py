from __future__ import annotations

import logging
from dataclasses import replace

from app.config import save_daily_card
from app.daily_card_runtime import daily_card_service
from app.handlers.common import is_admin

logger = logging.getLogger(__name__)

STATUS_TEXT = {
    "disabled": "Автопубликация выключена.",
    "not_due": "Время публикации ещё не наступило.",
    "not_sent": "Сегодня карта ещё не отправлялась.",
    "no_cards": "В выбранной папке и её подпапках нет карт. Добавьте JPG или PNG.",
    "sent": "Карта отправлена.",
    "already_sent": "Сегодня карта уже опубликована; повторная отправка заблокирована.",
    "uncertain": "Есть незавершённая попытка отправки. Проверьте чат: картинка и часть текста могли дойти. Автоматический повтор заблокирован, чтобы не создать дубль. Порядок восстановления описан в README.",
    "failed": "Не удалось подготовить карту. Нажмите «Проверить папки» в настройках: проверьте шаблоны в именах JPG/PNG и TXT/DOCX. Старые .doc пересохраните в .docx.",
}


async def daily_card_status(update, context) -> None:
    if not is_admin(update, context):
        return
    config = context.application.bot_data["config"].daily_card
    service = daily_card_service(context.application)
    match_details = ""
    try:
        files = service.content_files()
        count = len(files.images)
        text_count = len(files.texts)
        unsupported_count = len(files.unsupported_texts)
        if config.uses_patterns:
            catalog = service.matching_catalog(files)
            match_details = (
                f"Шаблонов: {len(config.patterns)}. Готовых картинок с текстом: {len(catalog.pairs)}\n"
                f"Картинок без шаблона: {len(catalog.unmatched_images)}, "
                f"без текста: {len(catalog.missing_text_images)}, "
                f"неоднозначных: {len(catalog.ambiguous_images)}\n"
            )
        else:
            match_details = "Работает прежний режим одной папки; новые папки и шаблоны настраиваются в панели.\n"
        status = STATUS_TEXT.get(service.status().status, "Статус неизвестен.")
    except (OSError, ValueError):
        count = "нет доступа"
        text_count = "нет доступа"
        unsupported_count = 0
        status = "Не удалось проверить папки, шаблоны или журнал публикаций."
    await update.effective_message.reply_text(
        f"Карта дня: {'включена' if config.enabled else 'выключена'}\n"
        f"Расписание: {config.time}, {config.timezone}\n"
        f"Чат: {config.chat_id or 'не выбран'}, тема: {config.message_thread_id or 'общая'}\n"
        f"Картинок: {count}, текстов TXT/DOCX: {text_count}\n"
        f"Пропущено .doc: {unsupported_count}\n{match_details}{status}"
    )


async def daily_card_here(update, context) -> None:
    if not is_admin(update, context):
        return
    chat, message = update.effective_chat, update.effective_message
    if not chat or chat.type not in {"group", "supergroup"}:
        await message.reply_text("Отправьте /daily_card_here в нужной группе или её теме «Карта дня».")
        return
    config = context.application.bot_data["config"]
    saved = save_daily_card({
        "chat_id": chat.id,
        "message_thread_id": message.message_thread_id if message.is_topic_message else None,
        # Choosing a destination must not immediately send a post to a new group.
        "enabled": False,
    })
    context.application.bot_data["config"] = replace(config, daily_card=saved)
    logger.info("Daily card destination configured by admin_id=%s", update.effective_user.id)
    await message.reply_text("Место публикации сохранено. В панели «Карта дня» задайте время и включите публикацию.")


async def daily_card_preview(update, context) -> None:
    if not is_admin(update, context):
        return
    if update.effective_chat.type != "private":
        await update.effective_message.reply_text("Для предпросмотра напишите /daily_card_preview боту в личные сообщения.")
        return
    try:
        result = await daily_card_service(context.application).preview(context.bot, update.effective_chat.id)
        text = STATUS_TEXT.get(result.status, "Предпросмотр завершён.")
        if result.status == "uncertain":
            text = "Результат отправки предпросмотра неизвестен. Проверьте личный чат. Журнал карты дня не изменён."
    except OSError:
        text = "Не удалось прочитать папку карт. Проверьте путь и права доступа."
    await update.effective_message.reply_text(text)


async def daily_card_publish(update, context) -> None:
    if not is_admin(update, context):
        return
    if context.args != ["CONFIRM"]:
        await update.effective_message.reply_text(
            "Опубликовать сегодняшнюю карту сейчас в настроенный чат: /daily_card_publish CONFIRM. "
            "Функция должна быть включена; повтор за сегодня не отправится."
        )
        return
    try:
        result = await daily_card_service(context.application).publish(context.bot, force=True)
        text = STATUS_TEXT.get(result.status, "Проверьте /daily_card_status.")
    except OSError:
        text = "Не удалось прочитать или сохранить журнал публикаций. Проверьте доступ к папке данных."
    logger.info("Manual daily card requested by admin_id=%s", update.effective_user.id)
    await update.effective_message.reply_text(text)
