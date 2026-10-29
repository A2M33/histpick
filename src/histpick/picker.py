"""A small full-screen picker that runs in any terminal, with no extra packages.

`PickerState` holds all the logic and is tested on its own. `pick()` only reads keys
and draws.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field

from .history import looks_secret

SECRET_MARK = "\x1b[33m!\x1b[0m"  # beside commands that may contain a password or token

# ---------- logic ----------


@dataclass
class PickerState:
    items: list[str]  # newest first
    query: str = ""
    pos: int = 0  # text cursor in query
    cursor: int = 0  # index into visible()
    top: int = 0  # first visible row on screen
    chosen: set[int] = field(default_factory=set)  # indexes into items
    order: list[int] = field(default_factory=list)  # script order from the last review
    only_chosen: bool = False  # hide commands that aren't chosen

    def visible(self) -> list[int]:
        # Each space-separated word must appear somewhere in the command, in any order.
        words = self.query.lower().split()
        return [i for i, c in enumerate(self.items)
                if all(w in c.lower() for w in words) and (not self.only_chosen or i in self.chosen)]

    def current(self) -> str | None:
        """The highlighted command."""
        vis = self.visible()
        return self.items[vis[self.cursor]] if vis else None

    def move(self, delta: int) -> None:
        n = len(self.visible())
        self.cursor = max(0, min(n - 1, self.cursor + delta)) if n else 0

    def toggle(self) -> None:
        vis = self.visible()
        if vis:
            self.chosen ^= {vis[self.cursor]}
            # In the chosen-only view the line just disappeared; stay where it was.
            self.move(0 if self.only_chosen else 1)

    def toggle_only_chosen(self) -> None:
        self.only_chosen = not self.only_chosen
        self.cursor = self.top = 0

    def toggle_all_visible(self) -> None:
        vis = set(self.visible())
        if vis <= self.chosen:
            self.chosen -= vis
        else:
            self.chosen |= vis

    # ----- editing the filter; pos is the text cursor inside query -----

    def _set_query(self, query: str, pos: int) -> None:
        self.query, self.pos = query, pos
        self.cursor = self.top = 0

    def type(self, ch: str) -> None:
        self._set_query(self.query[: self.pos] + ch + self.query[self.pos:], self.pos + len(ch))

    def backspace(self) -> None:
        if self.pos:
            self._set_query(self.query[: self.pos - 1] + self.query[self.pos:], self.pos - 1)

    def delete(self) -> None:
        if self.pos < len(self.query):
            self._set_query(self.query[: self.pos] + self.query[self.pos + 1:], self.pos)

    def left(self) -> None:
        self.pos = max(0, self.pos - 1)

    def right(self) -> None:
        self.pos = min(len(self.query), self.pos + 1)

    def clear(self) -> None:
        self._set_query("", 0)

    def escape(self) -> bool:
        """Esc undoes the filter or the chosen-only view first. True means cancel."""
        if self.query:
            self.clear()
        elif self.only_chosen:
            self.toggle_only_chosen()
        else:
            return True
        return False

    def result(self) -> list[str]:
        """Chosen commands in the order you ran them (oldest first)."""
        return [self.items[i] for i in sorted(self.chosen, reverse=True)]

    def scroll(self, height: int) -> None:
        _scroll(self, height)

    def review(self) -> ReviewState:
        """The review screen: earlier review order first, newly chosen commands after it in run order."""
        kept = [i for i in self.order if i in self.chosen]
        new = [i for i in sorted(self.chosen, reverse=True) if i not in kept]
        return ReviewState(self.items, kept + new)

    def back_from(self, review: ReviewState) -> None:
        self.order = list(review.order)
        self.chosen = set(review.order)


@dataclass
class ReviewState:
    """The chosen commands in script order, before saving."""

    items: list[str]
    order: list[int]  # indexes into items, top of the script first
    cursor: int = 0
    top: int = 0

    def move(self, delta: int) -> None:
        n = len(self.order)
        self.cursor = max(0, min(n - 1, self.cursor + delta)) if n else 0

    def shift(self, delta: int) -> None:
        """Move the highlighted command up (-1) or down (+1) in the script."""
        j = self.cursor + delta
        if self.order and 0 <= j < len(self.order):
            o = self.order
            o[self.cursor], o[j] = o[j], o[self.cursor]
            self.cursor = j

    def remove(self) -> None:
        if self.order:
            del self.order[self.cursor]
            self.move(0)

    def result(self) -> list[str]:
        return [self.items[i] for i in self.order]

    def scroll(self, height: int) -> None:
        _scroll(self, height)


def _scroll(s, height: int) -> None:
    if s.cursor < s.top:
        s.top = s.cursor
    elif s.cursor >= s.top + height:
        s.top = s.cursor - height + 1


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
MOVE_UP, MOVE_DOWN = "move-up", "move-down"  # Ctrl/Alt/Shift + arrow
CTRL_O, CTRL_U, CTRL_C, LEFT, RIGHT, DELETE = "ctrl-o", "ctrl-u", "ctrl-c", "left", "right", "delete"


# Space is an ordinary character so it can go into the filter; Tab chooses.
_CHARS = {"\r": ENTER, "\n": ENTER, "\x1b": ESC, "\x08": BACKSPACE, "\x7f": BACKSPACE,
          "\t": TAB, "\x01": CTRL_A, "\x0f": CTRL_O, "\x15": CTRL_U, "\x03": CTRL_C}
_WIN_SPECIAL = {"H": UP, "P": DOWN, "I": PGUP, "Q": PGDN, "G": HOME, "O": END, "K": LEFT, "M": RIGHT,
                "S": DELETE, "\x8d": MOVE_UP, "\x91": MOVE_DOWN, "\x98": MOVE_UP, "\xa0": MOVE_DOWN}
_CSI_LETTERS = {"A": UP, "B": DOWN, "C": RIGHT, "D": LEFT, "H": HOME, "F": END}
_CSI_MODIFIED = {"A": MOVE_UP, "B": MOVE_DOWN}
_CSI_TILDE = {"1": HOME, "7": HOME, "4": END, "8": END, "5": PGUP, "6": PGDN, "3": DELETE}


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
                return _WIN_SPECIAL.get(msvcrt.getwch(), "")
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
            return CTRL_C  # end of input
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
            params = seq[1:].decode("ascii", "replace").split(";")
            if final == b"~":
                return _CSI_TILDE.get(params[0], "")
            letter = final.decode("ascii", "replace")
            if len(params) > 1 and letter in _CSI_MODIFIED:  # "1;5A" is Ctrl+Up
                return _CSI_MODIFIED[letter]
            return _CSI_LETTERS.get(letter, "")
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


def preview(cmd: str | None, width: int, max_rows: int) -> list[str]:
    """All lines of a multi-line command, cut to fit; nothing for a one-line command."""
    lines = (cmd or "").splitlines()
    if len(lines) <= 1:
        return []
    if len(lines) > max_rows:
        lines = lines[: max_rows - 1] + [f"… (+{len(lines) - max_rows + 1} more lines)"]
    return [ln if len(ln) <= width else ln[: max(0, width - 1)] + "…" for ln in lines]


def _fit(text: str, cols: int) -> str:
    return text if len(text) < cols else text[: max(0, cols - 2)] + "…"


def _preview_rows(cmd: str | None, cols: int, rows: int) -> list[str]:
    lines = preview(cmd, cols - 4, max(2, rows // 3))
    if not lines:
        return []
    return ["\x1b[2m" + "─" * (cols - 1) + "\x1b[0m\r\n"] + [f"  {ln}\r\n" for ln in lines]


def _draw(s: PickerState, title: str) -> None:
    cols, rows = shutil.get_terminal_size((100, 30))
    pane = _preview_rows(s.current(), cols, rows)
    height = max(3, rows - 4 - len(pane))
    s.scroll(height)
    vis = s.visible()
    view = "  showing chosen only" if s.only_chosen else ""
    flagged = any(looks_secret(s.items[j]) for j in vis[s.top: s.top + height])
    legend = f"  {SECRET_MARK} \x1b[2mmay contain a password or token\x1b[0m" if flagged else ""
    out = ["\x1b[H\x1b[2J"]
    out.append(f"\x1b[1m{title}\x1b[0m  \x1b[2m{len(vis)}/{len(s.items)}  {len(s.chosen)} chosen{view}\x1b[0m"
               f"{legend}\r\n")
    q, p = s.query, s.pos
    caret = f"\x1b[7m{q[p] if p < len(q) else ' '}\x1b[0m"  # the cursor is hidden, so draw one
    hint = "" if q else "\x1b[2m(type to filter, words in any order)\x1b[0m"
    out.append(f"filter: {q[:p]}{caret}{q[p + 1:]}{hint}\r\n")
    for row in range(height):
        i = s.top + row
        if i >= len(vis):
            out.append("\r\n")
            continue
        idx = vis[i]
        chosen, secret = idx in s.chosen, looks_secret(s.items[idx])
        text = one_line(s.items[idx], cols - 9)
        if i == s.cursor:  # plain marks: a color reset inside would end the highlight
            out.append(f"\x1b[7m {'[x]' if chosen else '[ ]'} {'!' if secret else ' '} {text}\x1b[0m\r\n")
        else:
            mark = "\x1b[32m[x]\x1b[0m" if chosen else "[ ]"
            out.append(f" {mark} {SECRET_MARK if secret else ' '} {text}\r\n")
    out += pane
    help_ = "↑↓ move  tab choose  ctrl+a all  ctrl+o chosen only  ctrl+u clear  enter review  esc clear/cancel"
    out.append(f"\x1b[2m{_fit(help_, cols)}\x1b[0m")
    sys.stdout.write("".join(out))
    sys.stdout.flush()


def _draw_review(r: ReviewState, title: str) -> None:
    cols, rows = shutil.get_terminal_size((100, 30))
    pane = _preview_rows(r.items[r.order[r.cursor]] if r.order else None, cols, rows)
    height = max(3, rows - 4 - len(pane))
    r.scroll(height)
    n = len(r.order)
    width = len(str(n))
    out = ["\x1b[H\x1b[2J"]
    out.append(f"\x1b[1m{title}: review\x1b[0m  \x1b[2m{n} command{'s' if n != 1 else ''}\x1b[0m\r\n")
    secrets = sum(looks_secret(c) for c in r.result())
    if secrets:
        out.append(f"{SECRET_MARK} \x1b[33m{secrets} of these may contain a password or token. "
                   "Check the script before you share it.\x1b[0m\r\n")
    else:
        out.append("\x1b[2mThe script runs these from top to bottom.\x1b[0m\r\n")
    for row in range(height):
        i = r.top + row
        if i >= n:
            out.append("\r\n")
            continue
        cmd = r.items[r.order[i]]
        text = one_line(cmd, cols - width - 6)
        if i == r.cursor:
            out.append(f"\x1b[7m {i + 1:>{width}} {'!' if looks_secret(cmd) else ' '} {text}\x1b[0m\r\n")
        else:
            out.append(f" {i + 1:>{width}} {SECRET_MARK if looks_secret(cmd) else ' '} {text}\r\n")
    out += pane
    help_ = "↑↓ select  ctrl+↑↓ or u/d reorder  x remove  enter save  esc back"
    out.append(f"\x1b[2m{_fit(help_, cols)}\x1b[0m")
    sys.stdout.write("".join(out))
    sys.stdout.flush()


def _review_key(r: ReviewState, k: str, page: int) -> None:
    if k == UP:
        r.move(-1)
    elif k == DOWN:
        r.move(1)
    elif k == PGUP:
        r.move(-page)
    elif k == PGDN:
        r.move(page)
    elif k == HOME:
        r.move(-len(r.order))
    elif k == END:
        r.move(len(r.order))
    elif k in (MOVE_UP, "u", "U"):
        r.shift(-1)
    elif k in (MOVE_DOWN, "d", "D"):
        r.shift(1)
    elif k in ("x", "X", BACKSPACE, DELETE):
        r.remove()


def pick(items: list[str], title: str = "histpick") -> list[str] | None:
    """Interactive picker. Returns chosen commands in script order, or None if cancelled.

    Enter opens a review screen where you can reorder or drop commands; Enter there
    saves and Esc goes back to the list.
    """
    if os.environ.get("TERM") == "dumb":
        raise RuntimeError("this terminal can't show the picker; use --pick or --last")
    _enable_ansi()
    s = PickerState(items)
    review: ReviewState | None = None
    sys.stdout.write("\x1b[?1049h\x1b[?25l")  # alternate screen, hide cursor
    try:
        with _Keys() as keys:
            while True:
                if review is not None:
                    _draw_review(review, title)
                else:
                    _draw(s, title)
                k = keys.read()
                page = max(3, shutil.get_terminal_size((100, 30)).lines - 4)
                if k == CTRL_C:
                    return None
                if review is not None:
                    if k == ENTER:
                        return review.result()
                    if k == ESC:
                        s.back_from(review)
                        review = None
                    else:
                        _review_key(review, k, page)
                    continue
                if k in (UP, MOVE_UP):
                    s.move(-1)
                elif k in (DOWN, MOVE_DOWN):
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
                elif k == CTRL_O:
                    s.toggle_only_chosen()
                elif k == CTRL_A:
                    s.toggle_all_visible()
                elif k == BACKSPACE:
                    s.backspace()
                elif k == DELETE:
                    s.delete()
                elif k == LEFT:
                    s.left()
                elif k == RIGHT:
                    s.right()
                elif k == CTRL_U:
                    s.clear()
                elif k == ENTER:
                    if not s.chosen and s.visible():
                        s.toggle()  # Enter on nothing chosen takes the highlighted line
                    if not s.chosen:
                        return []
                    review = s.review()
                elif k == ESC:
                    if s.escape():
                        return None
                elif len(k) == 1 and k.isprintable():
                    s.type(k)
    finally:
        sys.stdout.write("\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()
