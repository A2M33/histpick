"""Render docs/picker.png: one real frame of the histpick picker over a made-up history, in the A2M33 "trace" palette.

The picker's own drawing code paints the frame into a buffer at a fixed terminal size, and
the escape codes are drawn as they come: cyan (45) becomes the signal token, dim the ink-2
grey, bold JetBrains Mono 500, and the reverse-video highlight an inset row.
Fonts come from tools/banner/fonts (needs a Pillow built with WOFF2 support).

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

FONTS = HERE.parent / "banner" / "fonts"
MONO = ImageFont.truetype(str(FONTS / "JetBrainsMono-400.woff2"), 15)
MONO_BOLD = ImageFont.truetype(str(FONTS / "JetBrainsMono-500.woff2"), 15)
LABEL = ImageFont.truetype(str(FONTS / "Archivo-500.woff2"), 16)

# Dark values from tokens.css
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
        elif code == "38;5;45":
            colour = SIGNAL
        else:
            raise ValueError(f"no palette colour for SGR {code!r}")
        pos = m.end()
    if pos < len(line):
        yield line[pos:], colour, bold, rev


def lamp_image(colour, size=12, scale=8):
    """An anti-aliased round pad (drawn large, scaled down)."""
    big = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    ImageDraw.Draw(big).ellipse((0, 0, size * scale - 1, size * scale - 1), fill=colour, outline=colour, width=scale)
    return big.resize((size, size), Image.LANCZOS)


def render(lines: list[str]) -> Image.Image:
    lh, margin, pad, bar = 24, 20, 26, 40
    cw = MONO.getlength("M")
    w = int(margin * 2 + pad * 2 + COLS * cw)
    h = margin * 2 + bar + pad + len(lines) * lh + pad - 6
    img = Image.new("RGB", (w, h), GROUND)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((margin, margin, w - margin - 1, h - margin - 1), radius=8, fill=PANEL, outline=LINE)
    y_mid = margin + bar // 2
    x0 = margin + pad
    lamp = lamp_image(SIGNAL)  # a lit pad: the picker is live, waiting for keys
    img.paste(lamp, (x0, y_mid - 6), lamp)
    d.text((x0 + 22, y_mid), "histpick", font=LABEL, fill=INK_2, anchor="lm")
    d.line((margin + 1, margin + bar, w - margin - 2, margin + bar), fill=LINE)
    top = margin + bar + pad - 4
    for r, line in enumerate(lines):
        x, y = x0, top + r * lh
        if "38;5;45" in line:  # a cyan bar in the margin beside chosen commands, as in the siblings
            d.rectangle((x0 - 12, y + 1, x0 - 9, y + lh - 7), fill=SIGNAL)
        for text, colour, bold, rev in spans(line):
            if rev:  # the highlighted row, or the drawn text cursor
                d.rectangle((x, y - 2, x + len(text) * cw - 1, y + lh - 5), fill=INSET)
            d.text((x, y), text, font=MONO_BOLD if bold else MONO, fill=colour)
            x += len(text) * cw
    return img


img = render(capture())
img.save(OUT, optimize=True)
print(OUT, img.size)
