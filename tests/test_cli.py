from datetime import datetime

import pytest

from histpick import history
from histpick.cli import main, parse_numbers
from histpick.writer import is_own_command, render


@pytest.fixture
def ps_history(tmp_path, monkeypatch):
    f = tmp_path / "ConsoleHost_history.txt"
    f.write_text("winget install Git.Git\ngit config --global user.name Amin\nhistpick --list\n"
                 "Get-ChildItem |`\n  Measure-Object\ngit config --global user.name Amin\n", encoding="utf-8")
    monkeypatch.setattr(history, "powershell_path", lambda: f)
    monkeypatch.chdir(tmp_path)
    return f


def test_parse_numbers():
    assert parse_numbers("1 3-5,8", 10) == [0, 2, 3, 4, 7]
    assert parse_numbers("5-3 3", 10) == [2, 3, 4]
    with pytest.raises(ValueError):
        parse_numbers("11", 10)


def test_list_shows_newest_first_without_own_calls(ps_history, capsys):
    assert main(["--shell", "powershell", "--list"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].endswith("git config --global user.name Amin")
    assert "Get-ChildItem |  (+1 lines)" in lines[1]
    assert not any("histpick" in line for line in lines)


def test_pick_saves_in_run_order(ps_history, tmp_path, capsys):
    assert main(["--shell", "powershell", "--pick", "1 3", "-o", "setup"]) == 0
    out = (tmp_path / "setup.ps1").read_text(encoding="utf-8-sig")
    assert out.index("winget install") < out.index("git config")
    assert "$ErrorActionPreference = 'Stop'" in out
    assert (tmp_path / "setup.ps1").read_bytes().startswith(b"\xef\xbb\xbf")
    assert main(["--shell", "powershell", "--last", "1", "-o", "setup"]) == 2  # no overwrite


def test_last_and_print(ps_history, capsys):
    assert main(["--shell", "powershell", "--last", "2", "--print"]) == 0
    out = capsys.readouterr().out
    assert out.index("Get-ChildItem |\n  Measure-Object") < out.index("git config")


def test_render_bash_header():
    text = render(["ls"], "bash", datetime(2026, 10, 29, 9, 5))
    assert text.startswith("#!/usr/bin/env bash\n# Saved with histpick from bash history on 2026-10-29 09:05\nset -euo pipefail")


def test_is_own_command():
    assert is_own_command("histpick --list")
    assert is_own_command(r"C:\tools\histpick.exe -o x")
    assert not is_own_command("git status")
