"""Prepare daily posts and protect against duplicate delivery across restarts."""
from __future__ import annotations

import json
import logging
import os
import random
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app.card_content import CardContentFiles, read_card_text, scan_card_folder
from app.card_matching import MatchCatalog, build_match_catalog
from app.message_parts import split_telegram_text
from app.telegram_delivery import send_post_part

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DailyCardResult:
    status: str
    message: str = ""
    card: Path | None = None
    message_id: int | None = None


@dataclass(frozen=True)
class _PreparedCard:
    card: Path
    text_file: Path | None
    caption: str
    text_parts: list[str]
    photo: Any
    pattern: str | None = None


def _utf16_length(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def _local_now(now: datetime | None, timezone: str) -> datetime:
    zone = ZoneInfo(timezone)
    current = now or datetime.now(zone)
    return current.replace(tzinfo=zone) if current.tzinfo is None else current.astimezone(zone)


class DailyCardService:
    def __init__(self, config: Any, journal_dir: Path):
        self.config = config
        self.journal_dir = Path(journal_dir)

    def content_files(self) -> CardContentFiles:
        if getattr(self.config, "uses_patterns", False):
            images = scan_card_folder(self.config.images_folder)
            texts = scan_card_folder(self.config.texts_folder)
            return CardContentFiles(images.images, texts.texts, texts.unsupported_texts)
        return scan_card_folder(Path(self.config.folder))

    def matching_catalog(self, files: CardContentFiles | None = None) -> MatchCatalog:
        files = files if files is not None else self.content_files()
        return build_match_catalog(files.images, files.texts, self.config.patterns)

    def list_cards(self) -> list[Path]:
        return list(self.content_files().images)

    def _prepare(self, files: CardContentFiles, local_date: date) -> _PreparedCard:
        pattern = None
        if getattr(self.config, "uses_patterns", False):
            catalog = self.matching_catalog(files)
            if not catalog.pairs:
                raise ValueError("Нет картинок с подходящим текстом. Проверьте обе папки и шаблоны в настройках.")
            selected = random.choice(catalog.pairs)
            card, pattern = selected.image, selected.pattern
            text_file = random.choice(selected.texts)
        else:
            card = random.choice(files.images)
            text_file = random.choice(files.texts) if files.texts else None
        if text_file:
            text = read_card_text(text_file)
        elif files.unsupported_texts:
            raise ValueError("Найдены файлы .doc; сохраните тексты как .docx или .txt.")
        else:
            text = str(self.config.caption).format(name=card.stem, date=local_date.isoformat())
        if _utf16_length(text) <= 1024:
            caption, parts = text, []
        else:
            caption, parts = "", split_telegram_text(text)
        return _PreparedCard(card, text_file, caption, parts, self._open_photo(card), pattern)

    @staticmethod
    def _open_photo(card: Path):
        photo = card.open("rb")
        try:
            if os.fstat(photo.fileno()).st_size > 10 * 1024 * 1024:
                raise ValueError("Карта превышает ограничение 10 МБ.")
            header = photo.read(8)
            if not (header.startswith(b"\xff\xd8\xff") or header == b"\x89PNG\r\n\x1a\n"):
                raise ValueError("Файл должен содержать изображение JPEG или PNG.")
            photo.seek(0)
            return photo
        except Exception:
            photo.close()
            raise

    def _reservation_path(self, local_date: date) -> Path:
        topic = getattr(self.config, "message_thread_id", None)
        topic_key = "none" if topic is None else str(int(topic))
        return self.journal_dir / f"{int(self.config.chat_id)}_{topic_key}_{local_date.isoformat()}.json"

    @staticmethod
    def _read_reservation(path: Path) -> dict[str, Any] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else None
        except (OSError, UnicodeError, json.JSONDecodeError):
            return None

    @staticmethod
    def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    @staticmethod
    async def _deliver(bot: Any, prepared: _PreparedCard, chat_id: int,
                       topic: int | None, record: Callable[[int], None]) -> int:
        target: dict[str, Any] = {"chat_id": int(chat_id), "parse_mode": None}
        if topic is not None:
            target["message_thread_id"] = int(topic)
        photo_message = await send_post_part(bot.send_photo, **target, photo=prepared.photo, caption=prepared.caption)
        record(photo_message.message_id)
        for part in prepared.text_parts:
            message = await send_post_part(bot.send_message, pause=True, **target, text=part)
            record(message.message_id)
        return photo_message.message_id

    async def publish(self, bot: Any, *, now: datetime | None = None, force: bool = False) -> DailyCardResult:
        if not bool(self.config.enabled):
            return DailyCardResult("disabled", "daily card is disabled")
        current = _local_now(now, self.config.timezone)
        state = self.status(now)
        # Never resume: Telegram may have accepted an unconfirmed part.
        if state.status != "not_sent":
            return state
        try:
            scheduled = time.fromisoformat(str(self.config.time))
        except ValueError:
            return DailyCardResult("failed", "invalid daily card time")
        if not force and current.time().replace(tzinfo=None) < scheduled:
            return DailyCardResult("not_due", "scheduled time has not arrived")
        files = self.content_files()
        if not files.images:
            return DailyCardResult("no_cards", "card folder is empty or missing")
        try:
            prepared = self._prepare(files, current.date())
        except (OSError, UnicodeError, ValueError) as exc:
            return DailyCardResult("failed", str(exc))

        reservation = self._reservation_path(current.date())
        patterned = getattr(self.config, "uses_patterns", False)
        image_folder = Path(self.config.images_folder if patterned else self.config.folder)
        text_folder = Path(self.config.texts_folder if patterned else self.config.folder)
        payload = {
            "status": "reserved", "date": current.date().isoformat(),
            "card": prepared.card.relative_to(image_folder).as_posix(),
            "text": prepared.text_file.relative_to(text_folder).as_posix() if prepared.text_file else None,
            "pattern": prepared.pattern,
            "attempted_at": current.isoformat(), "timezone": self.config.timezone,
            "chat_id": self.config.chat_id, "message_thread_id": self.config.message_thread_id,
            "completed_parts": 0, "total_parts": 1 + len(prepared.text_parts), "message_ids": [],
        }
        with prepared.photo:
            self.journal_dir.mkdir(parents=True, exist_ok=True)
            try:
                fd = os.open(reservation, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(payload, stream, ensure_ascii=False)
                    stream.flush()
                    os.fsync(stream.fileno())
            except FileExistsError:
                return self.status(now)

            def record(message_id: int) -> None:
                payload["message_ids"].append(message_id)
                payload["completed_parts"] += 1
                payload["message_id"] = payload["message_ids"][0]
                if payload["completed_parts"] == payload["total_parts"]:
                    payload["status"] = "sent"
                self._atomic_write(reservation, payload)

            try:
                message_id = await self._deliver(bot, prepared, self.config.chat_id, self.config.message_thread_id, record)
                return DailyCardResult("sent", "card published", card=prepared.card, message_id=message_id)
            except Exception as exc:
                logger.warning("Daily card delivery unconfirmed: %s", type(exc).__name__)
                payload.update(status="uncertain", error=type(exc).__name__)
                try:
                    self._atomic_write(reservation, payload)
                except OSError:
                    logger.error("Could not finalize daily card journal; reservation retained")
                return DailyCardResult("uncertain", "Publication may be partial; automatic retry is disabled", card=prepared.card)

    def status(self, now: datetime | None = None) -> DailyCardResult:
        path = self._reservation_path(_local_now(now, self.config.timezone).date())
        if not path.exists():
            return DailyCardResult("not_sent", "card has not been published today")
        value = self._read_reservation(path)
        if not value:
            return DailyCardResult("uncertain", "daily card journal is unreadable")
        if value.get("status") == "sent":
            return DailyCardResult("already_sent", "card already published", message_id=value.get("message_id"))
        return DailyCardResult("uncertain", "publication has an incomplete or ambiguous reservation")

    async def preview(self, bot: Any, chat_id: int, message_thread_id: int | None = None) -> DailyCardResult:
        files = self.content_files()
        if not files.images:
            return DailyCardResult("no_cards", "card folder is empty or missing")
        try:
            prepared = self._prepare(files, _local_now(None, self.config.timezone).date())
        except (OSError, UnicodeError, ValueError) as exc:
            return DailyCardResult("failed", str(exc))
        try:
            with prepared.photo:
                message_id = await self._deliver(bot, prepared, chat_id, message_thread_id, lambda _: None)
            return DailyCardResult("sent", "preview published", card=prepared.card, message_id=message_id)
        except Exception:
            return DailyCardResult("uncertain", "preview may be partial", card=prepared.card)
