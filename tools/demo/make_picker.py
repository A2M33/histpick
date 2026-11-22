"""Print the histpick picker frame shown in the README as plain text (escape codes removed).

    python tools/demo/make_picker.py
"""
import io
import os
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "src"))

from histpick import picker  # noqa: E402
from histpick.picker import PickerState  # noqa: E402


# Dark "trace" palette
GROUND = (0x0B, 0x12, 0x22)
PANEL = (0x11, 0x1A, 0x2D)
INSET = (0x18, 0x23, 0x3A)
LINE = (0x22, 0x30, 0x4B)
INK = (0xE6, 0xED, 0xF7)
INK_2 = (0x93, 0xA3, 0xBD)
SIGNAL = (0x2F, 0xCB, 0xEA)

# Newest first, as histpick reads them from PowerShell's history file.
HISTORY = [
    "ping github.com",
    "winget install --id Git.Git -e",
    "cls",
    "cd spacetrail",
    "git clone https://github.com/A2M33/spacetrail",
    "Get-ChildItem -Recurse -Filter *.log |\n  Remove-Item",
    "winget install --id Python.Python.3.12 -e",
    "code .",
    "Copy-Item .env.example .env",
    "git log --oneline -5",
    r".venv\Scripts\pip install -r requirements.txt",
    "python -m venv .venv",
]
CHOSEN = {1, 3, 4, 6, 10, 11}
CURSOR = 8
COLS, ROWS = 104, 19


def capture() -> list[str]:
    """One frame, exactly as the picker writes it to the terminal."""
    picker.shutil.get_terminal_size = lambda fallback=None: os.terminal_size((COLS, ROWS))
    os.environ.pop("NO_COLOR", None)
    state = PickerState(HISTORY, chosen=set(CHOSEN), cursor=CURSOR)
    buf = io.StringIO()
    with redirect_stdout(buf):
        picker._draw(state, "histpick: powershell history")
    text = buf.getvalue()
    text = text.removeprefix("\x1b[H").replace("\x1b[K", "").replace("\x1b[J", "")
    return text.split("\r\n")


out = capture()
ESC = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
lines = out.splitlines() if isinstance(out, str) else out
text = "\n".join(ESC.sub("", line).rstrip() for line in lines).rstrip()
sys.stdout.reconfigure(encoding="utf-8")
print(text)
