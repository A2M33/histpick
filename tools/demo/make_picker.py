"""Render docs/picker.png: one real frame of the histpick picker over a made-up history, in the A2M33 palette.

The picker's own drawing code paints the frame into a buffer at a fixed terminal size, and
the escape codes are drawn as they come: amber (214) becomes the amber token, dim the label
grey, bold Consolas Bold, and the reverse-video highlight an inset row.
Windows only as written (Consolas from C:/Windows/Fonts).

    pip install pillow
    python tools/demo/make_picker.py
"""
import io
import os
import re
import sys
from contextlib import redirect_stdout
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT = REPO / "docs" / "picker.png"
sys.path.insert(0, str(REPO / "src"))

from histpick import picker  # noqa: E402
from histpick.picker import PickerState  # noqa: E402

MONO = ImageFont.truetype("C:/Windows/Fonts/consola.ttf", 15)
MONO_BOLD = ImageFont.truetype("C:/Windows/Fonts/consolab.ttf", 15)
LABEL = ImageFont.truetype(str(HERE / "fonts" / "Barlow-Medium.woff2"), 16)

# Light values from tokens.css
CAB = (0xE3, 0xE5, 0xE0)
PANEL = (0xF4, 0xF5, 0xF2)
INSET = (0xD5, 0xD9, 0xD3)
LINE = (0xB9, 0xBF, 0xB7)
INK = (0x1D, 0x24, 0x20)
INK_2 = (0x56, 0x60, 0x5A)
AMBER = (0xD9, 0x92, 0x11)
AMBER_INK = (0x6B, 0x46, 0x00)  # amber text that stays readable on the light panel

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


SGR = re.compile("\x1b\\[([0-9;]*)m")


def spans(line: str):
    """(text, colour, bold, reversed) pieces of one line of picker output."""
    colour, bold, rev, pos = INK, False, False, 0
    for m in SGR.finditer(line):
        if m.start() > pos:
            yield line[pos:m.start()], colour, bold, rev
        code = m.group(1)
        if code in ("", "0"):
            colour, bold, rev = INK, False, False
        elif code == "1":
            bold = True
        elif code == "2":
            colour = INK_2
        elif code == "7":
            rev = True
        elif code == "38;5;214":
            colour = AMBER
        else:
            raise ValueError(f"no palette colour for SGR {code!r}")
        pos = m.end()
    if pos < len(line):
        yield line[pos:], colour, bold, rev


def lamp_image(colour, size=12, scale=8):
    """An anti-aliased round lamp (drawn large, scaled down)."""
    big = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    ImageDraw.Draw(big).ellipse((0, 0, size * scale - 1, size * scale - 1), fill=colour, outline=colour, width=scale)
    return big.resize((size, size), Image.LANCZOS)


def render(lines: list[str]) -> Image.Image:
    lh, margin, pad, bar = 24, 20, 26, 40
    cw = MONO.getlength("M")
    w = int(margin * 2 + pad * 2 + COLS * cw)
    h = margin * 2 + bar + pad + len(lines) * lh + pad - 6
    img = Image.new("RGB", (w, h), CAB)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((margin, margin, w - margin - 1, h - margin - 1), radius=6, fill=PANEL, outline=LINE)
    y_mid = margin + bar // 2
    x0 = margin + pad
    lamp = lamp_image(AMBER)  # amber: the picker is live, waiting for keys
    img.paste(lamp, (x0, y_mid - 6), lamp)
    d.text((x0 + 22, y_mid), "histpick", font=LABEL, fill=INK_2, anchor="lm")
    d.line((margin + 1, margin + bar, w - margin - 2, margin + bar), fill=LINE)
    top = margin + bar + pad - 4
    for r, line in enumerate(lines):
        x, y = x0, top + r * lh
        if "38;5;214" in line:  # an amber bar in the margin beside chosen commands, as in the siblings
            d.rectangle((x0 - 12, y + 1, x0 - 9, y + lh - 7), fill=AMBER)
        for text, colour, bold, rev in spans(line):
            if rev:  # the highlighted row, or the drawn text cursor
                d.rectangle((x, y - 2, x + len(text) * cw - 1, y + lh - 5), fill=INSET)
            fill = AMBER_INK if colour == AMBER else colour
            d.text((x, y), text, font=MONO_BOLD if bold else MONO, fill=fill)
            x += len(text) * cw
    return img


img = render(capture())
img.save(OUT, optimize=True)
print(OUT, img.size)
