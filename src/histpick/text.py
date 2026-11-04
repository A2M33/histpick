"""Text on a terminal: making it safe to print and measuring how much room it takes."""

from __future__ import annotations

import re

_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def _visible(match: re.Match) -> str:
    ch = match.group()
    if ch == "\t":
        return "    "
    return f"^{chr(ord(ch) ^ 0x40)}" if ord(ch) < 0x80 else "?"


def printable(text: str) -> str:
    """Control characters as ^[ and the like, so a line of history can't drive the terminal."""
    return _CONTROL.sub(_visible, text)
