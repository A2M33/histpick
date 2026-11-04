"""Text on a terminal: making it safe to print and measuring how much room it takes."""

from __future__ import annotations

import re
import unicodedata

_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def _visible(match: re.Match) -> str:
    ch = match.group()
    if ch == "\t":
        return "    "
    return f"^{chr(ord(ch) ^ 0x40)}" if ord(ch) < 0x80 else "?"


def printable(text: str) -> str:
    """Control characters as ^[ and the like, so a line of history can't drive the terminal."""
    return _CONTROL.sub(_visible, text)


def _char_cells(ch: str) -> int:
    if unicodedata.combining(ch) or unicodedata.category(ch) == "Cf":
        return 0  # accents, and the zero-width non-joiner in Persian
    return 2 if unicodedata.east_asian_width(ch) in "WF" else 1


def cells(text: str) -> int:
    """How many terminal columns `text` takes up."""
    return sum(_char_cells(ch) for ch in text)


def fit(text: str, width: int) -> str:
    """Cut `text` to `width` columns, ending in … if anything had to go."""
    if cells(text) <= width:
        return text
    room, end = width - 1, 0
    while end < len(text) and _char_cells(text[end]) <= room:
        room -= _char_cells(text[end])
        end += 1
    return text[:end] + "…" if width > 0 else ""
