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
from .text import cells, fit, printable

SECRET_MARK = "\x1b[33m!\x1b[0m"  # beside commands that may contain a password or token
CHOSEN_MARK = "\x1b[32m[x]\x1b[0m"
LEGEND = f"  {SECRET_MARK} \x1b[2mmay contain a password or token\x1b[0m"
LEGEND_COLUMNS = 35

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
        self.move(0)  # the chosen-only view may have just got shorter


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
    first, *rest = cmd.split("\n")
    more = f"  (+{len(rest)} lines)" if rest else ""
    if width < cells(more) + 4:  # no room to say both
        more = ""
    return fit(printable(first), width - cells(more)) + more


# ---------- keys ----------

UP, DOWN, PGUP, PGDN, HOME, END, ENTER, ESC, BACKSPACE, TAB, CTRL_A = (
    "up", "down", "pgup", "pgdn", "home", "end", "enter", "esc", "backspace", "tab", "ctrl-a",
)
MOVE_UP, MOVE_DOWN = "move-up", "move-down"  # Ctrl/Alt/Shift + arrow
CTRL_O, CTRL_U, CTRL_C, LEFT, RIGHT, DELETE = "ctrl-o", "ctrl-u", "ctrl-c", "left", "right", "delete"


# Space is an ordinary character so it can go into the filter; Tab chooses.
_CHARS = {"\r": ENTER, "\n": ENTER, "\x1b": ESC, "\x08": BACKSPACE, "\x7f": BACKSPACE,
          "\t": TAB, "\x01": CTRL_A, "\x0f": CTRL_O, "\x15": CTRL_U, "\x03": CTRL_C}
_WIN_KEYS = {0x26: UP, 0x28: DOWN, 0x21: PGUP, 0x22: PGDN, 0x24: HOME, 0x23: END, 0x25: LEFT, 0x27: RIGHT,
             0x2E: DELETE}  # virtual key codes
_WIN_ALT_CTRL_SHIFT = 0x1F
_CSI_LETTERS = {"A": UP, "B": DOWN, "C": RIGHT, "D": LEFT, "H": HOME, "F": END}
_CSI_MODIFIED = {"A": MOVE_UP, "B": MOVE_DOWN}
_CSI_TILDE = {"1": HOME, "7": HOME, "4": END, "8": END, "5": PGUP, "6": PGDN, "3": DELETE}


def windows_key(vk: int, char: str, modifiers: int) -> str:
    """Name a key press from the Windows console: a key name, a typed character, or ""."""
    if char != "\0":
        return _CHARS.get(char, char)
    key = _WIN_KEYS.get(vk, "")
    if key in (UP, DOWN) and modifiers & _WIN_ALT_CTRL_SHIFT:
        return MOVE_UP if key == UP else MOVE_DOWN
    return key


class _Keys:
    """Raw single-key input on Windows (console events) and Unix (termios)."""

    def __init__(self, fd: int | None = None):
        self._fd = fd

    def __enter__(self):
        if sys.platform == "win32":
            from .winkeys import ConsoleKeys

            self._console = ConsoleKeys()
            self._console.open()
        else:
            import termios
            import tty

            if self._fd is None:
                self._fd = sys.stdin.fileno()
            self._old = termios.tcgetattr(self._fd)
            tty.setraw(self._fd)
        return self

    def __exit__(self, *exc):
        if sys.platform == "win32":
            self._console.close()
        else:
            import termios

            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old)

    def read(self) -> str:
        if sys.platform == "win32":
            key = ""
            while not key:  # Shift or Ctrl on its own is an event too
                key = windows_key(*self._console.next_key())
            return key
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
    lines = [printable(ln) for ln in (cmd or "").split("\n")]
    if len(lines) <= 1:
        return []
    if len(lines) > max_rows:
        lines = lines[: max_rows - 1] + [f"… (+{len(lines) - max_rows + 1} more lines)"]
    return [fit(ln, width) for ln in lines]


def _preview_rows(cmd: str | None, cols: int, rows: int) -> list[str]:
    if rows < 8:  # a window this short needs every row for the list
        return []
    lines = preview(cmd, cols - 3, max(2, rows // 3))
    if not lines:
        return []
    return ["\x1b[2m" + "─" * (cols - 1) + "\x1b[0m"] + [f"  {ln}" for ln in lines]


def _heading(title: str, detail: str, flagged: bool, cols: int) -> str:
    """The title, then as much of the rest as the row has room for."""
    room = cols - 1
    title = fit(title, room)
    room -= cells(title)
    line = f"\x1b[1m{title}\x1b[0m"
    if room >= 8:
        detail = fit("  " + detail, room)
        room -= cells(detail)
        line += f"\x1b[2m{detail}\x1b[0m"
    if flagged and room >= LEGEND_COLUMNS:
        line += LEGEND
    return line


def _filter_line(query: str, pos: int, cols: int) -> str:
    label = "filter: "
    room = max(1, cols - 2 - len(label))  # one column stays free for the text cursor
    start = 0
    while cells(query[start:pos]) > room:  # a long filter scrolls to keep the cursor in view
        start += 1
    before = query[start:pos]
    under = query[pos] if pos < len(query) else " "
    caret = f"\x1b[7m{under}\x1b[0m"  # the terminal's cursor is hidden, so draw one
    after = fit(query[pos + 1:], room - cells(before))
    hint = "" if query else "\x1b[2m" + fit("(type to filter, words in any order)", room) + "\x1b[0m"
    return f"{label}{before}{caret}{after}{hint}"


def _row(marks: str, plain_marks: str, text: str, selected: bool) -> str:
    # The selected row uses plain marks: a colour reset inside would end the highlight.
    return f"\x1b[7m{plain_marks}{text}\x1b[0m" if selected else f"{marks}{text}"


def _paint(lines: list[str]) -> None:
    sys.stdout.write("\x1b[H\x1b[2J" + "\r\n".join(lines))
    sys.stdout.flush()


def _draw(s: PickerState, title: str) -> None:
    cols, rows = shutil.get_terminal_size((100, 30))
    pane = _preview_rows(s.current(), cols, rows)
    height = max(1, rows - 3 - len(pane))
    s.scroll(height)
    vis = s.visible()
    view = "  showing chosen only" if s.only_chosen else ""
    flagged = any(looks_secret(s.items[j]) for j in vis[s.top: s.top + height])
    lines = [_heading(title, f"{len(vis)}/{len(s.items)}  {len(s.chosen)} chosen{view}", flagged, cols),
             _filter_line(s.query, s.pos, cols)]
    for i in range(s.top, s.top + height):
        if i >= len(vis):
            lines.append("")
            continue
        cmd = s.items[vis[i]]
        chosen, secret = vis[i] in s.chosen, looks_secret(cmd)
        marks = f" {CHOSEN_MARK if chosen else '[ ]'} {SECRET_MARK if secret else ' '} "
        plain = f" {'[x]' if chosen else '[ ]'} {'!' if secret else ' '} "
        lines.append(_row(marks, plain, one_line(cmd, cols - 8), i == s.cursor))
    help_ = "↑↓ move  tab choose  ctrl+a all  ctrl+o chosen only  ctrl+u clear  enter review  esc clear/cancel"
    _paint(lines + pane + [f"\x1b[2m{fit(help_, cols - 1)}\x1b[0m"])


def _draw_review(r: ReviewState, title: str) -> None:
    cols, rows = shutil.get_terminal_size((100, 30))
    pane = _preview_rows(r.items[r.order[r.cursor]] if r.order else None, cols, rows)
    height = max(1, rows - 3 - len(pane))
    r.scroll(height)
    n = len(r.order)
    width = len(str(n))
    lines = [_heading(f"{title}: review", f"{n} command{'s' if n != 1 else ''}", False, cols)]
    secrets = sum(looks_secret(c) for c in r.result())
    if secrets:
        warning = f"{secrets} of these may contain a password or token. Check the script before you share it."
        lines.append(f"{SECRET_MARK} \x1b[33m{fit(warning, cols - 3)}\x1b[0m")
    else:
        lines.append("\x1b[2m" + fit("The script runs these from top to bottom.", cols - 1) + "\x1b[0m")
    for i in range(r.top, r.top + height):
        if i >= n:
            lines.append("")
            continue
        cmd = r.items[r.order[i]]
        secret = looks_secret(cmd)
        marks = f" {i + 1:>{width}} {SECRET_MARK if secret else ' '} "
        plain = f" {i + 1:>{width}} {'!' if secret else ' '} "
        lines.append(_row(marks, plain, one_line(cmd, cols - width - 5), i == r.cursor))
    help_ = "↑↓ select  ctrl+↑↓ or u/d reorder  x remove  enter save  esc back"
    _paint(lines + pane + [f"\x1b[2m{fit(help_, cols - 1)}\x1b[0m"])


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
