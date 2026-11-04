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


def test_long_filter_scrolls_to_keep_the_cursor_in_view(monkeypatch, capsys):
    s = PickerState(["ls"])
    for ch in "abcdefghij" * 10:
        s.type(ch)
    line = frame(picker._draw, s, 40, 24, monkeypatch, capsys)[1]
    assert cells(line) < 40 and line.rstrip().endswith("ghij")


def test_one_line_keeps_the_line_count_of_a_long_command():
    assert one_line("x" * 100 + "\ny\nz", 30).endswith("…  (+2 lines)")
    assert cells(one_line("x" * 100 + "\ny", 5)) <= 5


def test_fit_counts_columns_not_characters():
    assert fit("abc", 3) == "abc"
    assert fit("abcdef", 4) == "abc…"
    assert fit("日本語日本語", 7) == "日本語…"
    assert fit("anything", 0) == ""
