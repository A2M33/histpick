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


def histpick_process(tmp_path, *args, **popen):
    """The real CLI in its own process, reading a PowerShell history from `tmp_path`."""
    folder = tmp_path / "Microsoft" / "Windows" / "PowerShell"
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONIOENCODING", "PYTHONUTF8")}
    env.update(PYTHONPATH=SRC, APPDATA=str(tmp_path), XDG_DATA_HOME=str(tmp_path))
    hist = (folder if sys.platform == "win32" else tmp_path / "powershell") / "PSReadLine"
    hist.mkdir(parents=True, exist_ok=True)
    (hist / "ConsoleHost_history.txt").write_text("git status\necho سلام دنیا\n", encoding="utf-8")
    return subprocess.Popen([sys.executable, "-m", "histpick", "--shell", "powershell", *args], env=env,
                            cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **popen)


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


def test_printed_script_keeps_non_english_text_in_a_pipe(tmp_path):
    p = histpick_process(tmp_path, "--last", "1", "--print")
    out, err = p.communicate(timeout=60)
    assert p.returncode == 0, err
    assert "سلام دنیا" in out.decode("utf-8")


def test_reader_that_leaves_early_is_not_an_error(tmp_path):
    p = histpick_process(tmp_path, "--list")
    p.stdout.close()  # what `histpick --list | more` does when you quit more
    err = p.stderr.read()
    p.stderr.close()
    assert p.wait(timeout=60) == 0, err
    assert err == b""


def test_no_home_folder_is_not_a_crash(monkeypatch, capsys):
    def nowhere():
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(history.Path, "home", nowhere)
    for name in ("APPDATA", "HISTFILE", "XDG_DATA_HOME"):
        monkeypatch.delenv(name, raising=False)
    assert main(["--list"]) == 1
    assert "No shell history found" in capsys.readouterr().err


def test_appdata_is_enough_without_a_home_folder(tmp_path, monkeypatch):
    def nowhere():
        raise RuntimeError("Could not determine home directory.")

    monkeypatch.setattr(history.Path, "home", nowhere)
    monkeypatch.setattr(history.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert str(tmp_path) in str(history.powershell_path())


def test_empty_variables_count_as_not_set(tmp_path, monkeypatch):
    monkeypatch.setattr(history.Path, "home", lambda: tmp_path)
    for name in ("APPDATA", "HISTFILE", "XDG_DATA_HOME"):
        monkeypatch.setenv(name, "")
    assert all(s.path.is_absolute() for s in history.known_shells())


def test_closed_stdout_does_not_crash(ps_history, monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)
    assert main(["--shell", "powershell", "--list"]) == 0


def test_ctrl_c_exits_with_130(ps_history, monkeypatch, capsys):
    def interrupted(shell):
        raise KeyboardInterrupt

    monkeypatch.setattr(history, "read", interrupted)
    assert main(["--shell", "powershell", "--list"]) == 130
    assert capsys.readouterr().err.strip() == "Cancelled."
