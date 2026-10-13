from __future__ import annotations


def _units(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2


def split_telegram_text(text: str, limit: int = 4096) -> list[str]:
    if not text:
        return []
    if limit <= 0:
        raise ValueError("limit must be positive")
    if text.isspace():
        raise ValueError("whitespace-only text cannot be sent")

    result: list[str] = []
    remaining = text
    while remaining:
        if _units(remaining) <= limit:
            if remaining.isspace():
                raise ValueError("whitespace-only text cannot be sent")
            result.append(remaining)
            break

        used = 0
        cut = 0
        for index, char in enumerate(remaining):
            next_used = used + _units(char)
            if next_used > limit:
                break
            used = next_used
            cut = index + 1
        if cut == 0:
            raise ValueError("limit is smaller than the first Unicode code point")

        prefix = remaining[:cut]
        tail = remaining[cut:]
        if tail and tail.isspace():
            # Move the final meaningful code point into the remainder. This
            # keeps trailing whitespace attached to content and avoids a
            # whitespace-only message.
            meaningful_end = len(remaining.rstrip())
            cut = min(cut, meaningful_end - 1)
            if cut <= 0:
                raise ValueError("limit would produce a whitespace-only message")
            prefix = remaining[:cut]
        # Prefer the last paragraph/newline/space boundary that fits.
        boundary = prefix.rfind("\n\n")
        if boundary <= 0:
            boundary = prefix.rfind("\n")
        if boundary <= 0:
            boundary = prefix.rfind(" ")
        if boundary > 0:
            if prefix[boundary:boundary + 2] == "\n\n":
                boundary += 2
            else:
                boundary += 1
            candidate = remaining[:boundary]
            if not candidate.isspace():
                cut = boundary
                prefix = candidate

        if prefix.isspace():
            raise ValueError("split would produce a whitespace-only message")
        result.append(prefix)
        remaining = remaining[cut:]
    return result
