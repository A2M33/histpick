"""Every frame must fit the window, whatever is in the history."""

import os
import re

import pytest

from histpick import picker
from histpick.picker import PickerState, ReviewState, one_line
from histpick.text import cells, fit

ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


def frame(draw, state, cols, rows, monkeypatch, capsys):
    """The rows of one drawn frame, without colour codes."""
    monkeypatch.setattr(picker.shutil, "get_terminal_size", lambda fallback=None: os.terminal_size((cols, rows)))
    draw(state, "histpick: powershell history")
    return ANSI.sub("", capsys.readouterr().out).split("\r\n")


ITEMS = [
    "x" * 500,
    "日本語のコマンド" * 40,
    "echo سلام می‌خواهم " * 30,
    "export API_TOKEN=abc",
    "for f in *\n  do echo $f\ndone",
]


@pytest.mark.parametrize("cols, rows", [(120, 30), (80, 24), (40, 12), (20, 6)])
def test_list_frame_fits_the_window(cols, rows, monkeypatch, capsys):
    lines = frame(picker._draw, PickerState(ITEMS, chosen={0}), cols, rows, monkeypatch, capsys)
    assert len(lines) <= rows
    assert all(cells(line) < cols for line in lines)


@pytest.mark.parametrize("cols, rows", [(120, 30), (80, 24), (40, 12), (20, 6)])
def test_review_frame_fits_the_window(cols, rows, monkeypatch, capsys):
    lines = frame(picker._draw_review, ReviewState(ITEMS, [3, 0, 1, 4]), cols, rows, monkeypatch, capsys)
    assert len(lines) <= rows
    assert all(cells(line) < cols for line in lines)


def test_no_color_keeps_the_highlight_but_drops_the_colours(monkeypatch, capsys):
    s = PickerState(["export API_TOKEN=x", "git status"], chosen={1})
    monkeypatch.delenv("NO_COLOR", raising=False)
    picker._draw(s, "histpick")
    coloured = capsys.readouterr().out
    assert "\x1b[38;5;45m[x]" in coloured  # chosen commands are cyan
    assert "\x1b[1m\x1b[38;5;45m!" in coloured  # and so is the possible-secret mark, in bold
    assert not any(f"\x1b[{code}m" in coloured for code in ("31", "32", "33"))  # no red, green or yellow
    monkeypatch.setenv("NO_COLOR", "1")
    picker._draw(s, "histpick")
    plain = capsys.readouterr().out
    assert "38;5;45" not in plain and "\x1b[7m" in plain and "\x1b[1m!" in plain


def test_review_warning_about_secrets_is_cyan(monkeypatch, capsys):
    s = ReviewState(["export API_TOKEN=x", "git status"], [0, 1])
    monkeypatch.setattr(picker.shutil, "get_terminal_size", lambda fallback=None: os.terminal_size((120, 24)))
    monkeypatch.delenv("NO_COLOR", raising=False)
    picker._draw_review(s, "histpick")
    assert "\x1b[38;5;45m1 of these may contain a password or token" in capsys.readouterr().out
    monkeypatch.setenv("NO_COLOR", "1")
    picker._draw_review(s, "histpick")
    plain = capsys.readouterr().out
    assert "38;5;45" not in plain and "1 of these may contain a password or token" in plain


def test_terminal_without_escape_codes_gets_an_explanation(monkeypatch):
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setattr(picker, "enable_ansi", lambda: False)
    with pytest.raises(RuntimeError, match="can't show the picker"):
        picker.pick(["ls"])


def test_highlight_fills_the_row(monkeypatch, capsys):
    monkeypatch.setattr(picker.shutil, "get_terminal_size", lambda fallback=None: os.terminal_size((50, 24)))
    picker._draw(PickerState(["ls"]), "histpick")
    raw = capsys.readouterr().out
    row = next(r for r in raw.split("\r\n") if "ls" in r and "filter" not in r)
    assert cells(ANSI.sub("", row)) == 49


@pytest.mark.parametrize("cols", [80, 60, 50])
def test_help_keeps_esc_on_screen(cols, monkeypatch, capsys):
    last = frame(picker._draw, PickerState(["ls"]), cols, 24, monkeypatch, capsys)[-1]
    assert "esc cancel" in last and "…" not in last


def test_long_filter_scrolls_to_keep_the_cursor_in_view(monkeypatch, capsys):
    s = PickerState(["ls"])
    for ch in "abcdefghij" * 10:
        s.type(ch)
    line = frame(picker._draw, s, 40, 24, monkeypatch, capsys)[1]
    assert cells(line) < 40 and line.rstrip().endswith("ghij")


def test_one_line_keeps_the_line_count_of_a_long_command():
    assert one_line("x" * 100 + "\ny\nz", 30).endswith("…  (+2 lines)")
    assert cells(one_line("x" * 100 + "\ny", 5)) <= 5


def test_list_cuts_long_commands_only_in_a_terminal(tmp_path, monkeypatch, capsys):
    from histpick import cli

    history_file = tmp_path / "history.txt"
    history_file.write_text("x" * 300 + "\n", encoding="utf-8")
    monkeypatch.setattr(cli.history, "powershell_path", lambda: history_file)
    assert cli.main(["--shell", "powershell", "--list"]) == 0
    assert "x" * 300 in capsys.readouterr().out  # a pipe gets the whole command

    monkeypatch.setattr(cli, "_is_terminal", lambda stream: True)
    monkeypatch.setattr(cli.shutil, "get_terminal_size", lambda fallback=None: os.terminal_size((40, 24)))
    assert cli.main(["--shell", "powershell", "--list"]) == 0
    assert cells(capsys.readouterr().out.rstrip("\n")) == 39


def test_fit_counts_columns_not_characters():
    assert fit("abc", 3) == "abc"
    assert fit("abcdef", 4) == "abc…"
    assert fit("日本語日本語", 7) == "日本語…"
    assert fit("anything", 0) == ""
