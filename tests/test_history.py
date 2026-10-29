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


def zsh_metafy(text: str) -> bytes:
    # What zsh does when it writes history: bytes 0x83-0xa2 become 0x83, byte ^ 0x20.
    out = bytearray()
    for b in text.encode("utf-8"):
        if 0x83 <= b <= 0xA2:
            out += bytes([0x83, b ^ 0x20])
        else:
            out.append(b)
    return bytes(out)


def test_zsh_non_ascii_is_unmetafied(tmp_path):
    from histpick import history

    f = tmp_path / ".zsh_history"
    f.write_bytes(zsh_metafy(": 1700000000:0;echo é à 日本\n: 1700000001:0;ls\n"))
    assert history.read(history.Shell("zsh", ".sh", f)) == ["echo é à 日本", "ls"]


def test_recent_unique_ignores_trailing_whitespace():
    assert recent_unique(["git status", "ls", "git status  ", "git status\t"]) == ["git status\t", "ls"]


def test_looks_secret():
    from histpick.history import looks_secret

    for cmd in ["mysql -u root --password=hunter2", "export GITHUB_TOKEN=abc", "curl -H 'Authorization: Bearer abc.def'",
                "set API_KEY=1", "az login --client-secret x", "aws configure set aws_access_key_id AKIAIOSFODNN7EXAMPLE",
                "git clone https://ghp_" + "a" * 36 + "@github.com/me/repo", "$env:apikey = 'x'"]:
        assert looks_secret(cmd), cmd
    for cmd in ["git status", "pwd", "npm install", "echo bearer", "cd ~/akiapath"]:
        assert not looks_secret(cmd), cmd
