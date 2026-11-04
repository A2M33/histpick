"""What the CLI does when the terminal, the environment or the history file misbehave."""

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from histpick import cli, history
from histpick.cli import main

SRC = str(Path(__file__).resolve().parent.parent / "src")


@pytest.fixture
def ps_history(tmp_path, monkeypatch):
    f = tmp_path / "ConsoleHost_history.txt"
    f.write_text("git status\necho سلام دنیا\n", encoding="utf-8")
    monkeypatch.setattr(history, "powershell_path", lambda: f)
    monkeypatch.chdir(tmp_path)
    return f


@pytest.mark.parametrize("processes, clicked", [
    (2, True),    # double-clicked: the onefile stub and Python
    (3, False),   # typed in a terminal: the shell as well
])
def test_double_click_counts_the_onefile_stub(processes, clicked, monkeypatch):
    monkeypatch.setattr(cli.sys, "platform", "win32")
    monkeypatch.setattr(cli.sys, "frozen", True, raising=False)
    monkeypatch.setattr(cli, "_console_process_count", lambda: processes)
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(isatty=lambda: True))
    assert cli._double_clicked() is clicked


@pytest.mark.parametrize("error", [EOFError, KeyboardInterrupt])
def test_pause_survives_closed_stdin_and_ctrl_c(error, monkeypatch):
    def interrupted(prompt=""):
        raise error

    monkeypatch.setattr(cli, "_double_clicked", lambda: True)
    monkeypatch.setattr("builtins.input", interrupted)
    cli._pause_if_double_clicked()
