"""Turn a list of commands into a script file for the right shell."""

from __future__ import annotations

import os
import stat
import sys
from datetime import datetime
from pathlib import Path

HEADERS = {
    # Stop at the first failing command, like you would have when typing them by hand.
    "powershell": "$ErrorActionPreference = 'Stop'",
    "bash": "#!/usr/bin/env bash\nset -euo pipefail",
    "zsh": "#!/usr/bin/env zsh\nset -euo pipefail",
    "fish": "#!/usr/bin/env fish",
}
LABELS = {"powershell": "PowerShell", "bash": "bash", "zsh": "zsh", "fish": "fish"}


def render(commands: list[str], shell: str, now: datetime | None = None) -> str:
    now = now or datetime.now()
    header = HEADERS[shell]
    note = f"# Saved with histpick from {LABELS[shell]} history on {now:%Y-%m-%d %H:%M}"
    if header.startswith("#!"):
        shebang, _, rest = header.partition("\n")
        top = [shebang, note] + ([rest] if rest else [])
    else:
        top = [note, header]
    return "\n".join(top) + "\n\n" + "\n\n".join(commands) + "\n"


def default_name(ext: str, now: datetime | None = None) -> str:
    now = now or datetime.now()
    return f"histpick-{now:%Y%m%d-%H%M}{ext}"


def save(text: str, path: Path, shell: str, force: bool = False) -> Path:
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists (use --force to overwrite)")
    # Windows PowerShell 5.1 reads a .ps1 without a BOM as ANSI and mangles non-English text.
    encoding = "utf-8-sig" if shell == "powershell" else "utf-8"
    newline = "\r\n" if shell == "powershell" and sys.platform == "win32" else "\n"
    with open(path, "w", encoding=encoding, newline=newline) as f:
        f.write(text)
    if sys.platform != "win32":
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def is_own_command(cmd: str) -> bool:
    first = cmd.strip().split(maxsplit=1)[0] if cmd.strip() else ""
    # Split on both kinds of slash: a PowerShell history read on Linux still has C:\ paths.
    name = first.replace("\\", "/").rsplit("/", 1)[-1]
    return os.path.splitext(name)[0].lower() == "histpick"
