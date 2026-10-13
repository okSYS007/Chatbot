"""Match card images with text files by configured filename phrases."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata
from typing import Iterable


_SPACE_RE = re.compile(r"[\s_]+", re.UNICODE)
_MAX_PATTERNS = 200
_MAX_PATTERN_LENGTH = 100


def normalize_pattern(value: str) -> str:
    """Normalize a phrase for case-insensitive filename matching."""
    if not isinstance(value, str):
        raise ValueError("Шаблон должен быть строкой.")
    return _SPACE_RE.sub(" ", unicodedata.normalize("NFKC", value).casefold()).strip()


def validate_patterns(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(values, (list, tuple)):
        raise ValueError("Шаблоны должны быть списком строк.")
    if len(values) > _MAX_PATTERNS:
        raise ValueError(f"Допустимо не более {_MAX_PATTERNS} шаблонов.")
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_pattern(value)
        if not normalized:
            raise ValueError("Шаблон не должен быть пустым.")
        if len(normalized) > _MAX_PATTERN_LENGTH:
            raise ValueError(f"Шаблон не должен превышать {_MAX_PATTERN_LENGTH} символов.")
        if normalized in seen:
            raise ValueError(f"Шаблон повторяется: {normalized}")
        seen.add(normalized)
        result.append(normalized)
    return tuple(result)


def _is_word(character: str) -> bool:
    return character.isalnum() or unicodedata.category(character).startswith("M")


def _contains_phrase(text: str, phrase: str) -> bool:
    start = 0
    while True:
        index = text.find(phrase, start)
        if index < 0:
            return False
        before = text[index - 1] if index else ""
        after_index = index + len(phrase)
        after = text[after_index] if after_index < len(text) else ""
        left_ok = not _is_word(phrase[0]) or not before or not _is_word(before)
        right_ok = not _is_word(phrase[-1]) or not after or not _is_word(after)
        if left_ok and right_ok:
            return True
        start = index + 1


def match_pattern(stem: str, patterns: tuple[str, ...]) -> str | None:
    """Return the most specific matching phrase, or raise on ambiguity."""
    normalized_stem = normalize_pattern(stem)
    normalized_patterns = tuple(normalize_pattern(p) for p in patterns)
    matches = [p for p in normalized_patterns if p and _contains_phrase(normalized_stem, p)]
    if not matches:
        return None
    specific = [p for p in matches if not any(p != other and _contains_phrase(other, p) for other in matches)]
    if len(specific) == 1:
        return specific[0]
    raise ValueError("Имя соответствует нескольким независимым шаблонам.")


@dataclass(frozen=True)
class MatchedCard:
    image: Path
    pattern: str
    texts: tuple[Path, ...]


@dataclass(frozen=True)
class MatchCatalog:
    pairs: tuple[MatchedCard, ...]
    unmatched_images: tuple[Path, ...]
    ambiguous_images: tuple[Path, ...]
    unmatched_texts: tuple[Path, ...]
    ambiguous_texts: tuple[Path, ...]
    missing_text_images: tuple[Path, ...]


def _sorted(paths: Iterable[Path]) -> tuple[Path, ...]:
    return tuple(sorted(paths, key=lambda path: (str(path).casefold(), str(path))))


def build_match_catalog(
    images: Iterable[Path], texts: Iterable[Path], patterns: tuple[str, ...]
) -> MatchCatalog:
    patterns = validate_patterns(patterns)
    image_paths = _sorted(images)
    text_paths = _sorted(texts)
    text_groups: dict[str, list[Path]] = {pattern: [] for pattern in patterns}
    unmatched_texts: list[Path] = []
    ambiguous_texts: list[Path] = []
    for path in text_paths:
        try:
            pattern = match_pattern(path.stem, patterns)
        except ValueError:
            ambiguous_texts.append(path)
            continue
        if pattern is None:
            unmatched_texts.append(path)
        else:
            text_groups[pattern].append(path)

    pairs: list[MatchedCard] = []
    unmatched_images: list[Path] = []
    ambiguous_images: list[Path] = []
    missing_text_images: list[Path] = []
    for path in image_paths:
        try:
            pattern = match_pattern(path.stem, patterns)
        except ValueError:
            ambiguous_images.append(path)
            continue
        if pattern is None:
            unmatched_images.append(path)
            continue
        matching_texts = tuple(text_groups[pattern])
        if not matching_texts:
            missing_text_images.append(path)
        else:
            pairs.append(MatchedCard(path, pattern, matching_texts))
    return MatchCatalog(
        tuple(pairs), _sorted(unmatched_images), _sorted(ambiguous_images),
        _sorted(unmatched_texts), _sorted(ambiguous_texts), _sorted(missing_text_images)
    )
