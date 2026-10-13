"""Safe discovery and text extraction for a selected tarot-card folder."""

from __future__ import annotations

import codecs
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET


MAX_FILE_SIZE = 10 * 1024 * 1024
MAX_DOCUMENT_XML = 4 * 1024 * 1024
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


@dataclass(frozen=True)
class CardContentFiles:
    images: tuple[Path, ...]
    texts: tuple[Path, ...]
    unsupported_texts: tuple[Path, ...]


def _safe_entries(folder: Path) -> Iterable[Path]:
    if not folder.is_dir() or folder.is_symlink():
        return ()
    result: list[Path] = []
    root = folder.resolve()
    for current, dirs, files in os.walk(folder, topdown=True, followlinks=False):
        current_path = Path(current)
        kept: list[str] = []
        for name in dirs:
            candidate = current_path / name
            if name.startswith("~$") or name.startswith(".~") or candidate.is_symlink() or getattr(candidate, "is_junction", lambda: False)():
                continue
            try:
                candidate.resolve().relative_to(root)
            except ValueError:
                continue
            kept.append(name)
        dirs[:] = kept
        for name in files:
            path = current_path / name
            if name.startswith("~$") or name.startswith(".~") or path.is_symlink():
                continue
            try:
                path.resolve().relative_to(root)
            except ValueError:
                continue
            result.append(path)
    return result


def scan_card_folder(folder: Path) -> CardContentFiles:
    images: list[Path] = []
    texts: list[Path] = []
    unsupported: list[Path] = []
    for path in _safe_entries(Path(folder)):
        suffix = path.suffix.lower()
        if suffix in {".jpg", ".jpeg", ".png"}:
            images.append(path)
        elif suffix in {".txt", ".docx"}:
            texts.append(path)
        elif suffix == ".doc":
            unsupported.append(path)
    key = lambda p: p.as_posix().casefold()
    return CardContentFiles(tuple(sorted(images, key=key)), tuple(sorted(texts, key=key)), tuple(sorted(unsupported, key=key)))


def _check_size(path: Path) -> None:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ValueError(f"Не удалось прочитать файл: {path.name}") from exc
    if size > MAX_FILE_SIZE:
        raise ValueError("Файл содержимого карты превышает ограничение 10 МБ.")


def _read_txt(path: Path) -> str:
    _check_size(path)
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_FILE_SIZE + 1)
        if len(raw) > MAX_FILE_SIZE:
            raise ValueError("Файл содержимого карты превышает ограничение 10 МБ.")
        if raw.startswith(codecs.BOM_UTF8):
            text = raw[len(codecs.BOM_UTF8):].decode("utf-8")
        elif raw.startswith(codecs.BOM_UTF16_LE):
            text = raw[len(codecs.BOM_UTF16_LE):].decode("utf-16-le")
        elif raw.startswith(codecs.BOM_UTF16_BE):
            text = raw[len(codecs.BOM_UTF16_BE):].decode("utf-16-be")
        else:
            text = raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError("Текстовый файл должен быть в UTF-8 или UTF-16 с BOM.") from exc
    if not text.strip():
        raise ValueError("Текстовый файл пустой.")
    return text


def _element_text(element: ET.Element) -> str:
    chunks: list[str] = []
    def visit(node: ET.Element, hidden: bool = False) -> None:
        hidden = hidden or node.tag in {_W + "del", _W + "vanish"}
        if node.tag == _W + "r":
            vanish = node.find("./" + _W + "rPr/" + _W + "vanish")
            if vanish is not None and str(vanish.get(_W + "val", "true")).lower() not in {"0", "false", "off", "no"}:
                hidden = True
        if not hidden:
            if node.tag == _W + "t" and node.text:
                chunks.append(node.text)
            elif node.tag == _W + "tab":
                chunks.append("\t")
            elif node.tag == _W + "br":
                chunks.append("\n")
        for child in node:
            visit(child, hidden)
    visit(element)
    return "".join(chunks)


def _docx_text(path: Path) -> str:
    _check_size(path)
    try:
        with zipfile.ZipFile(path) as archive:
            try:
                info = archive.getinfo("word/document.xml")
            except KeyError as exc:
                raise ValueError("DOCX не содержит основной документ.") from exc
            if info.file_size > MAX_DOCUMENT_XML:
                raise ValueError("Основной XML документа превышает ограничение 4 МБ.")
            with archive.open(info) as member:
                xml = member.read(MAX_DOCUMENT_XML + 1)
            if len(xml) > MAX_DOCUMENT_XML:
                raise ValueError("Основной XML документа превышает ограничение 4 МБ.")
    except (OSError, RuntimeError, NotImplementedError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ValueError("Файл DOCX повреждён или имеет неверный формат.") from exc
    try:
        xml_text = xml.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Основной XML документа имеет неверную кодировку.") from exc
    if "<!DOCTYPE" in xml_text.upper() or "<!ENTITY" in xml_text.upper():
        raise ValueError("DOCX с DTD или внешними сущностями не поддерживается.")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise ValueError("Основной XML документа повреждён.") from exc
    body = root.find(".//" + _W + "body")
    if body is None:
        raise ValueError("DOCX не содержит текста документа.")
    lines: list[str] = []
    for child in list(body):
        if child.tag == _W + "p":
            lines.append(_element_text(child))
        elif child.tag == _W + "tbl":
            for row in child.findall(".//" + _W + "tr"):
                cells = []
                for cell in row.findall("./" + _W + "tc"):
                    paragraphs = [_element_text(p) for p in cell.findall("./" + _W + "p")]
                    cells.append("\n".join(paragraphs))
                lines.append("\t".join(cells))
    text = "\n".join(lines)
    if not text.strip():
        raise ValueError("DOCX документ пустой.")
    return text


def read_card_text(path: Path) -> str:
    path = Path(path)
    if path.suffix.lower() == ".txt":
        return _read_txt(path)
    if path.suffix.lower() == ".docx":
        return _docx_text(path)
    if path.suffix.lower() == ".doc":
        raise ValueError("Формат .doc устарел; сохраните файл как .docx или .txt.")
    raise ValueError("Поддерживаются только файлы .txt и .docx.")
