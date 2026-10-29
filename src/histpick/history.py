"""Read command history from PowerShell, bash, zsh and fish.

Each shell stores history differently, and all of them allow multi-line commands,
so each reader returns whole commands, oldest first.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Shell:
    name: str
    ext: str
    path: Path


def powershell_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home())) / "Microsoft" / "Windows"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "PowerShell" / "PSReadLine" / "ConsoleHost_history.txt"


def known_shells() -> list[Shell]:
    home = Path.home()
    fish_base = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
    return [
        Shell("powershell", ".ps1", powershell_path()),
        Shell("bash", ".sh", Path(os.environ.get("HISTFILE", home / ".bash_history"))),
        Shell("zsh", ".sh", home / ".zsh_history"),
        Shell("fish", ".fish", fish_base / "fish" / "fish_history"),
    ]


def detect() -> Shell | None:
    """The shell we were most likely started from: its history file changed last."""
    found = [s for s in known_shells() if s.path.is_file()]
    if not found:
        return None
    parent = _parent_shell_hint()
    for s in found:
        if s.name == parent:
            return s
    return max(found, key=lambda s: s.path.stat().st_mtime)


def _parent_shell_hint() -> str | None:
    # Check the Unix-style variables first: Windows sets PSModulePath for every
    # program, Git Bash included, so it only means PowerShell when nothing else matches.
    shell = os.path.basename(os.environ.get("SHELL", "")).lower().removesuffix(".exe")
    if shell in ("bash", "zsh", "fish"):
        return shell
    if os.environ.get("MSYSTEM"):  # Git Bash and MSYS2
        return "bash"
    if os.environ.get("PSModulePath") and sys.platform == "win32":
        return "powershell"
    return None


def read(shell: Shell) -> list[str]:
    data = shell.path.read_bytes()
    if shell.name == "zsh":
        data = unmetafy(data)
    raw = data.decode("utf-8", errors="replace")
    parser = {"powershell": parse_powershell, "bash": parse_bash, "zsh": parse_zsh, "fish": parse_fish}
    return parser[shell.name](raw)


def parse_powershell(text: str) -> list[str]:
    # PSReadLine ends every line except the last of a multi-line command with a backtick.
    out, buf = [], []
    for line in text.splitlines():
        if line.endswith("`"):
            buf.append(line[:-1])
            continue
        buf.append(line)
        out.append("\n".join(buf))
        buf = []
    if buf:
        out.append("\n".join(buf))
    return [c for c in out if c.strip()]


def parse_bash(text: str) -> list[str]:
    # With HISTTIMEFORMAT set, bash writes "#1700000000" before each command.
    out = []
    for line in text.splitlines():
        if re.fullmatch(r"#\d{9,}", line):
            continue
        if line.strip():
            out.append(line)
    return out


def unmetafy(data: bytes) -> bytes:
    """Undo zsh's escaping: it writes some bytes as 0x83 followed by the byte XOR 0x20."""
    first, *rest = data.split(b"\x83")
    out = bytearray(first)
    for part in rest:
        if part:
            out.append(part[0] ^ 0x20)
            out += part[1:]
    return bytes(out)


_ZSH_EXTENDED = re.compile(r"^: \d+:\d+;(.*)$")


def parse_zsh(text: str) -> list[str]:
    # Extended history looks like ": 1700000000:0;command". Multi-line commands end
    # each continued line with a backslash.
    out, buf = [], []
    for line in text.splitlines():
        m = _ZSH_EXTENDED.match(line)
        if m and not buf:
            line = m.group(1)
        if line.endswith("\\") and not line.endswith("\\\\"):
            buf.append(line[:-1])
            continue
        buf.append(line)
        out.append("\n".join(buf))
        buf = []
    if buf:
        out.append("\n".join(buf))
    return [c for c in out if c.strip()]


def parse_fish(text: str) -> list[str]:
    # fish uses a YAML-like file: "- cmd: ..." with "\n" and "\\" escaped.
    out = []
    for line in text.splitlines():
        if line.startswith("- cmd: "):
            cmd = line[len("- cmd: "):]
            cmd = re.sub(r"\\(.)", lambda m: "\n" if m.group(1) == "n" else m.group(1), cmd)
            out.append(cmd)
    return out


def recent_unique(commands: list[str], limit: int | None = None) -> list[str]:
    """Newest first, each command once (its latest use wins)."""
    seen, out = set(), []
    for c in reversed(commands):
        if c in seen:
            continue
        seen.add(c)
        out.append(c)
        if limit and len(out) >= limit:
            break
    return out
