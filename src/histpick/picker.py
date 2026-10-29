"""A small full-screen picker that runs in any terminal, with no extra packages.

`PickerState` holds all the logic and is tested on its own. `pick()` only reads keys
and draws.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field

# ---------- logic ----------


@dataclass
class PickerState:
    items: list[str]  # newest first
    query: str = ""
    cursor: int = 0  # index into visible()
    top: int = 0  # first visible row on screen
    chosen: set[int] = field(default_factory=set)  # indexes into items

    def visible(self) -> list[int]:
        # Each space-separated word must appear somewhere in the command, in any order.
        words = self.query.lower().split()
        return [i for i, c in enumerate(self.items) if all(w in c.lower() for w in words)]

    def move(self, delta: int) -> None:
        n = len(self.visible())
        self.cursor = max(0, min(n - 1, self.cursor + delta)) if n else 0

    def toggle(self) -> None:
        vis = self.visible()
        if vis:
            self.chosen ^= {vis[self.cursor]}
            self.move(1)

    def toggle_all_visible(self) -> None:
        vis = set(self.visible())
        if vis <= self.chosen:
            self.chosen -= vis
        else:
            self.chosen |= vis

    def type(self, ch: str) -> None:
        self.query += ch
        self.cursor = self.top = 0

    def backspace(self) -> None:
        self.query = self.query[:-1]
        self.cursor = self.top = 0

    def result(self) -> list[str]:
        """Chosen commands in the order you ran them (oldest first)."""
        return [self.items[i] for i in sorted(self.chosen, reverse=True)]

    def scroll(self, height: int) -> None:
        if self.cursor < self.top:
            self.top = self.cursor
        elif self.cursor >= self.top + height:
            self.top = self.cursor - height + 1


def one_line(cmd: str, width: int) -> str:
    lines = cmd.splitlines() or [""]
    text = lines[0]
    if len(lines) > 1:
        text += f"  (+{len(lines) - 1} lines)"
    return text if len(text) <= width else text[: max(0, width - 1)] + "…"


# ---------- keys ----------

UP, DOWN, PGUP, PGDN, HOME, END, ENTER, ESC, BACKSPACE, TAB, CTRL_A = (
    "up", "down", "pgup", "pgdn", "home", "end", "enter", "esc", "backspace", "tab", "ctrl-a",
)


# Space is an ordinary character so it can go into the filter; Tab chooses.
_CHARS = {"\r": ENTER, "\n": ENTER, "\x1b": ESC, "\x08": BACKSPACE, "\x7f": BACKSPACE,
          "\t": TAB, "\x01": CTRL_A, "\x03": ESC}
_CSI_LETTERS = {"A": UP, "B": DOWN, "H": HOME, "F": END}
_CSI_TILDE = {"1": HOME, "7": HOME, "4": END, "8": END, "5": PGUP, "6": PGDN}


class _Keys:
    """Raw single-key input on Windows (msvcrt) and Unix (termios)."""

    def __init__(self, fd: int | None = None):
        self._fd = fd

    def __enter__(self):
        if sys.platform != "win32":
            import termios
            import tty

            if self._fd is None:
                self._fd = sys.stdin.fileno()
            self._old = termios.tcgetattr(self._fd)
            tty.setraw(self._fd)
        return self

    def __exit__(self, *exc):
        if sys.platform != "win32":
            import termios

            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old)

    def read(self) -> str:
        if sys.platform == "win32":
            import msvcrt

            ch = msvcrt.getwch()
            if ch in ("\x00", "\xe0"):  # arrows and other special keys come in two parts
                return {"H": UP, "P": DOWN, "I": PGUP, "Q": PGDN, "G": HOME, "O": END}.get(msvcrt.getwch(), "")
            return _CHARS.get(ch, ch)
        return self._read_posix()

    # Read the file descriptor directly. sys.stdin.read(1) pulls the whole escape
    # sequence into Python's buffer, where select() can't see the rest of it, so
    # every arrow key looked like a lone Esc.
    def _ready(self, timeout: float) -> bool:
        import select

        return bool(select.select([self._fd], [], [], timeout)[0])

    def _byte(self) -> bytes:
        return os.read(self._fd, 1)

    def _read_posix(self) -> str:
        b = self._byte()
        if not b:
            return ESC  # end of input
        if b == b"\x1b":
            if not self._ready(0.05):
                return ESC
            seq = self._byte()
            if seq not in (b"[", b"O"):
                return ""  # Alt+key
            final = b""
            while self._ready(0.05):
                final = self._byte()
                if 0x40 <= final[0] <= 0x7E:
                    break
                seq += final
            params = seq[1:].decode("ascii", "replace").split(";")[0]
            if final == b"~":
                return _CSI_TILDE.get(params, "")
            return _CSI_LETTERS.get(final.decode("ascii", "replace"), "")
        if b[0] >= 0xC0:  # first byte of a multi-byte UTF-8 character
            need = 1 if b[0] < 0xE0 else 2 if b[0] < 0xF0 else 3
            while need and self._ready(0.05):
                b += self._byte()
                need -= 1
        ch = b.decode("utf-8", errors="replace")
        return _CHARS.get(ch, ch)


# ---------- drawing ----------

def _enable_ansi() -> None:
    if sys.platform == "win32":
        import ctypes

        k = ctypes.windll.kernel32
        h = k.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if k.GetConsoleMode(h, ctypes.byref(mode)):
            k.SetConsoleMode(h, mode.value | 0x0004)


def _draw(s: PickerState, title: str) -> None:
    cols, rows = shutil.get_terminal_size((100, 30))
    height = max(3, rows - 4)
    s.scroll(height)
    vis = s.visible()
    out = ["\x1b[H\x1b[2J"]
    out.append(f"\x1b[1m{title}\x1b[0m  \x1b[2m{len(s.chosen)} chosen\x1b[0m\r\n")
    out.append(f"filter: {s.query}\x1b[2m{'' if s.query else '(type to filter)'}\x1b[0m\r\n")
    for row in range(height):
        i = s.top + row
        if i >= len(vis):
            out.append("\r\n")
            continue
        idx = vis[i]
        mark = "\x1b[32m[x]\x1b[0m" if idx in s.chosen else "[ ]"
        text = one_line(s.items[idx], cols - 7)
        line = f" {mark} {text}"
        out.append(f"\x1b[7m{line}\x1b[0m\r\n" if i == s.cursor else line + "\r\n")
    out.append("\x1b[2m↑↓ move  tab choose  ctrl+a all  enter save  esc cancel\x1b[0m")
    sys.stdout.write("".join(out))
    sys.stdout.flush()


def pick(items: list[str], title: str = "histpick") -> list[str] | None:
    """Interactive picker. Returns chosen commands oldest first, or None if cancelled."""
    if os.environ.get("TERM") == "dumb":
        raise RuntimeError("this terminal can't show the picker; use --pick or --last")
    _enable_ansi()
    s = PickerState(items)
    sys.stdout.write("\x1b[?1049h\x1b[?25l")  # alternate screen, hide cursor
    try:
        with _Keys() as keys:
            while True:
                _draw(s, title)
                k = keys.read()
                page = max(3, shutil.get_terminal_size((100, 30)).lines - 4)
                if k == UP:
                    s.move(-1)
                elif k == DOWN:
                    s.move(1)
                elif k == PGUP:
                    s.move(-page)
                elif k == PGDN:
                    s.move(page)
                elif k == HOME:
                    s.move(-len(items))
                elif k == END:
                    s.move(len(items))
                elif k == TAB:
                    s.toggle()
                elif k == CTRL_A:
                    s.toggle_all_visible()
                elif k == BACKSPACE:
                    s.backspace()
                elif k == ENTER:
                    if not s.chosen and s.visible():
                        s.toggle()  # Enter on nothing chosen takes the highlighted line
                    return s.result()
                elif k == ESC:
                    return None
                elif len(k) == 1 and k.isprintable():
                    s.type(k)
    finally:
        sys.stdout.write("\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()
