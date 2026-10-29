from histpick.history import parse_bash, parse_fish, parse_powershell, parse_zsh, recent_unique


def test_powershell_multiline():
    text = "git status\nGet-ChildItem |`\n  Where-Object Length -gt 1MB\nexit\n"
    assert parse_powershell(text) == [
        "git status",
        "Get-ChildItem |\n  Where-Object Length -gt 1MB",
        "exit",
    ]


def test_bash_skips_timestamps_and_blanks():
    text = "#1700000000\nls -la\n\n#1700000001\ncd /tmp\n"
    assert parse_bash(text) == ["ls -la", "cd /tmp"]


def test_zsh_extended_and_multiline():
    text = ": 1700000000:0;echo one\n: 1700000001:0;for f in *; do\\\necho $f\\\ndone\n: 1700000002:0;ls\n"
    assert parse_zsh(text) == ["echo one", "for f in *; do\necho $f\ndone", "ls"]


def test_zsh_plain_format():
    assert parse_zsh("ls\ncd ~\n") == ["ls", "cd ~"]


def test_fish():
    text = "- cmd: ls -la\n  when: 1700000000\n- cmd: echo a\\nb\n  when: 1700000001\n- cmd: echo back\\\\slash\n"
    assert parse_fish(text) == ["ls -la", "echo a\nb", "echo back\\slash"]


def test_recent_unique_keeps_latest_order():
    assert recent_unique(["a", "b", "a", "c"]) == ["c", "a", "b"]
    assert recent_unique(["a", "b", "c"], limit=2) == ["c", "b"]


def test_git_bash_on_windows_is_not_mistaken_for_powershell(monkeypatch):
    from histpick import history

    monkeypatch.setattr(history.sys, "platform", "win32")
    monkeypatch.setenv("PSModulePath", r"C:\Program Files\WindowsPowerShell\Modules")
    monkeypatch.delenv("SHELL", raising=False)
    monkeypatch.setenv("MSYSTEM", "MINGW64")
    assert history._parent_shell_hint() == "bash"
    monkeypatch.delenv("MSYSTEM")
    monkeypatch.setenv("SHELL", "/usr/bin/bash")
    assert history._parent_shell_hint() == "bash"
    monkeypatch.delenv("SHELL")
    assert history._parent_shell_hint() == "powershell"
