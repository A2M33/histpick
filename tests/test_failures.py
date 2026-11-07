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


def test_printed_script_is_utf8_when_python_ignores_pythonioencoding(tmp_path):
    # histpick.exe runs like `python -E`: PYTHONIOENCODING is set but nobody applies it.
    p = histpick_process(tmp_path, "--last", "1", "--print")
    p.communicate(timeout=60)
    env = {k: v for k, v in os.environ.items() if k != "PYTHONUTF8"}
    env.update(PYTHONIOENCODING="utf-8", APPDATA=str(tmp_path), XDG_DATA_HOME=str(tmp_path))
    code = f"import sys; sys.path.insert(0, {SRC!r}); from histpick.cli import main; sys.exit(main())"
    r = subprocess.run([sys.executable, "-E", "-c", code, "--shell", "powershell", "--list"], env=env,
                       cwd=tmp_path, capture_output=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "سلام دنیا" in r.stdout.decode("utf-8")


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


def test_powershell_folder_is_lowercase_on_linux_and_macos(tmp_path, monkeypatch):
    monkeypatch.setattr(history.sys, "platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert history.powershell_path() == tmp_path / "powershell" / "PSReadLine" / "ConsoleHost_history.txt"


@pytest.mark.parametrize("data", [
    b"\xef\xbb\xbfgit status\nls\n",                  # UTF-8 with a BOM
    "git status\nls\n".encode("utf-16"),              # what `>` writes in Windows PowerShell 5.1
    b"git status\n\x00\x00\x00\x00\nls\n\x00\x00",   # NUL bytes after a crash
])
def test_odd_encodings_give_clean_commands(data, ps_history):
    ps_history.write_bytes(data)
    assert history.read(history.Shell("powershell", ".ps1", ps_history)) == ["git status", "ls"]


def test_random_bytes_are_not_a_crash(ps_history, capsys):
    ps_history.write_bytes(bytes(range(256)) * 20)
    assert main(["--shell", "powershell", "--list"]) == 0


def test_unreadable_history_is_a_clean_error(ps_history, monkeypatch, capsys):
    def denied(shell):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(history, "read", denied)
    assert main(["--shell", "powershell", "--list"]) == 1
    assert capsys.readouterr().err.startswith("Can't read ")


def test_huge_range_is_refused_at_once():
    with pytest.raises(ValueError, match="no command number 999999999999"):
        cli.parse_numbers("1-999999999999", 10)
    with pytest.raises(ValueError, match="not a number"):
        cli.parse_numbers("²", 10)  # a digit to str.isdigit, but int() can't read it


def test_empty_pick_chooses_nothing(ps_history, capsys):
    assert main(["--shell", "powershell", "--pick", ""]) == 1
    assert "Nothing chosen" in capsys.readouterr().out


def test_pick_and_last_can_not_be_combined(ps_history, capsys):
    with pytest.raises(SystemExit) as e:
        main(["--shell", "powershell", "--pick", "1", "--last", "1"])
    assert e.value.code == 2
    assert "not allowed with" in capsys.readouterr().err


def test_last_can_reach_past_the_default_limit(ps_history, capsys):
    ps_history.write_text("".join(f"echo {n}\n" for n in range(400)), encoding="utf-8")
    assert main(["--shell", "powershell", "--last", "350", "--print"]) == 0
    assert capsys.readouterr().out.count("\necho ") == 350


def test_dumb_terminal_explains_itself(ps_history, monkeypatch, capsys):
    monkeypatch.setenv("TERM", "dumb")
    monkeypatch.setattr(cli, "_is_terminal", lambda stream: True)
    assert main(["--shell", "powershell"]) == 2
    assert "can't show the picker" in capsys.readouterr().err


@pytest.mark.parametrize("output", [".", "..", "afolder"])
def test_output_that_is_a_folder_is_a_clean_error(output, ps_history, tmp_path, capsys):
    (tmp_path / "afolder").mkdir()
    assert main(["--shell", "powershell", "--last", "1", "-o", output]) == 2
    assert "is a folder" in capsys.readouterr().err


def test_existing_output_stops_before_the_picker_opens(ps_history, tmp_path, monkeypatch, capsys):
    (tmp_path / "setup.ps1").write_text("keep me", encoding="utf-8")
    monkeypatch.setattr(cli, "_is_terminal", lambda stream: True)
    monkeypatch.setattr(cli, "pick", lambda *a, **kw: pytest.fail("the picker must not open"))
    assert main(["--shell", "powershell", "-o", "setup"]) == 2
    assert "already exists" in capsys.readouterr().err
    assert (tmp_path / "setup.ps1").read_text(encoding="utf-8") == "keep me"


def test_escape_sequences_from_history_are_shown_not_run(ps_history, capsys):
    ps_history.write_text('printf "\x1b[2J\x07"\necho "\x1b]0;token\x07"\n', encoding="utf-8")
    assert main(["--shell", "powershell", "--list"]) == 0
    assert '^[[2J^G' in capsys.readouterr().out
    assert main(["--shell", "powershell", "--last", "1", "--print"]) == 0
    captured = capsys.readouterr()
    assert "\x1b" not in captured.err  # the secret warning shows the command too
    assert '"\x1b]0;token\x07"' in captured.out  # the script keeps the command as it was


def test_picker_shows_control_characters_safely():
    from histpick.picker import one_line, preview

    assert one_line("a\x1b[31mb\tc", 40) == "a^[[31mb    c"
    assert preview("one\ntwo\x1b[K", 40, 5) == ["one", "two^[[K"]


def test_closed_stdout_does_not_crash(ps_history, monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)
    assert main(["--shell", "powershell", "--list"]) == 0


def test_ctrl_c_exits_with_130(ps_history, monkeypatch, capsys):
    def interrupted(shell):
        raise KeyboardInterrupt

    monkeypatch.setattr(history, "read", interrupted)
    assert main(["--shell", "powershell", "--list"]) == 130
    assert capsys.readouterr().err.strip() == "Cancelled."
