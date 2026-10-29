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
    assert parse_numbers("5-3 3", 10) == [4, 3, 2]
    with pytest.raises(ValueError):
        parse_numbers("11", 10)


def test_list_shows_newest_first_without_own_calls(ps_history, capsys):
    assert main(["--shell", "powershell", "--list"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].endswith("git config --global user.name Amin")
    assert "Get-ChildItem |  (+1 lines)" in lines[1]
    assert not any("histpick" in line for line in lines)


def test_pick_saves_in_the_order_given(ps_history, tmp_path, capsys):
    assert main(["--shell", "powershell", "--pick", "3 1", "-o", "setup"]) == 0
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


def test_grep_searches_past_the_limit(ps_history, capsys):
    assert main(["--shell", "powershell", "--grep", "winget", "--limit", "1", "--list"]) == 0
    assert capsys.readouterr().out.splitlines() == ["1   winget install Git.Git"]


def test_scripts_stop_when_a_program_fails():
    ps = render(["git clone x", "cd x"], "powershell")
    assert "$PSNativeCommandUseErrorActionPreference = $true" in ps
    assert "$global:LASTEXITCODE = 0" in ps
    assert ps.endswith("git clone x\nif ($LASTEXITCODE) { exit $LASTEXITCODE }\n\n"
                       "cd x\nif ($LASTEXITCODE) { exit $LASTEXITCODE }\n")
    fish = render(["git clone x"], "fish")
    assert fish.endswith("git clone x\nor exit $status\n")
    assert "set -e" in render(["ls"], "zsh")


def test_pick_order_wins_over_history_order(ps_history, capsys):
    # 1 = git config (newest), 3 = winget (oldest): the script follows the numbers
    assert main(["--shell", "powershell", "--pick", "1 3", "--print"]) == 0
    out = capsys.readouterr().out
    assert out.index("git config") < out.index("winget install")


def test_save_message_has_full_path_and_run_command(ps_history, tmp_path, capsys):
    assert main(["--shell", "powershell", "--last", "1", "-o", "setup"]) == 0
    out = capsys.readouterr().out
    full = str((tmp_path / "setup.ps1").resolve())
    assert f"to {full}" in out
    assert "Run it with: " in out and full in out.splitlines()[-1]


def test_run_hint():
    from pathlib import Path, PurePosixPath

    from histpick.cli import run_hint

    p = Path("C:/Users/me/setup.ps1")
    assert run_hint(p, "powershell", "win32") == f'powershell -ExecutionPolicy Bypass -File "{p}"'
    assert run_hint(PurePosixPath("/home/me/setup.ps1"), "powershell", "linux").startswith("pwsh -File ")
    assert run_hint(PurePosixPath("/home/me/my setup.sh"), "bash", "linux") == "bash '/home/me/my setup.sh'"
    assert run_hint(PurePosixPath("/home/me/x.fish"), "fish", "darwin") == "fish /home/me/x.fish"


def test_bad_numbers_give_a_clear_error(ps_history, capsys):
    for bad in ("abc", "1-", "-3", "2-x"):
        with pytest.raises(ValueError, match="not a number or a range"):
            parse_numbers(bad, 10)
    assert main(["--shell", "powershell", "--pick", "abc", "--print"]) == 2
    assert capsys.readouterr().err.strip() == '"abc" is not a number or a range like 3-5'


@pytest.mark.parametrize("value", ["0", "-1", "x"])
def test_last_and_limit_must_be_positive(ps_history, capsys, value):
    for flag in ("--last", "--limit"):
        with pytest.raises(SystemExit) as e:
            main(["--shell", "powershell", flag, value, "--print"])
        assert e.value.code == 2
        err = capsys.readouterr().err
        assert "must be 1 or more" in err or "is not a number" in err


def test_output_into_a_missing_folder(ps_history, tmp_path, capsys):
    assert main(["--shell", "powershell", "--last", "1", "-o", "nodir/x"]) == 0
    assert (tmp_path / "nodir" / "x.ps1").is_file()


def test_unwritable_output_is_a_clean_error(ps_history, tmp_path, capsys):
    (tmp_path / "afile").write_text("", encoding="utf-8")
    assert main(["--shell", "powershell", "--last", "1", "-o", "afile/x"]) == 2
    assert capsys.readouterr().err.startswith("Can't write ")


def test_empty_history_says_so(ps_history, capsys):
    ps_history.write_text("", encoding="utf-8")
    assert main(["--shell", "powershell", "--list"]) == 1
    assert "has no commands in it" in capsys.readouterr().err
    ps_history.write_text("histpick --list\n", encoding="utf-8")
    assert main(["--shell", "powershell", "--list"]) == 1
    assert "has no commands in it" in capsys.readouterr().err


def test_grep_without_matches_says_what_it_searched(ps_history, capsys):
    assert main(["--shell", "powershell", "--grep", "docker", "--list"]) == 1
    assert 'contains "docker"' in capsys.readouterr().err


def test_secrets_are_marked_and_warned_about(ps_history, tmp_path, capsys):
    with open(ps_history, "a", encoding="utf-8") as f:
        f.write("$env:GITHUB_TOKEN = 'abc123'\n")
    assert main(["--shell", "powershell", "--list"]) == 0
    out = capsys.readouterr()
    assert out.out.splitlines()[0] == "1 ! $env:GITHUB_TOKEN = 'abc123'"
    assert out.out.splitlines()[1].startswith("2   ")
    assert "may contain a password or token" in out.err
    assert main(["--shell", "powershell", "--pick", "1", "-o", "s"]) == 0
    err = capsys.readouterr().err
    assert err.startswith("Warning: 1 of the chosen commands may contain a password or token")
    assert "  ! $env:GITHUB_TOKEN = 'abc123'" in err
    assert (tmp_path / "s.ps1").is_file()
    assert main(["--shell", "powershell", "--pick", "2", "--print"]) == 0
    assert "Warning" not in capsys.readouterr().err
