"""Key presses from the Windows console, read as events.

msvcrt.getwch() won't do: it returns 0xE0 both as the first half of an arrow key and for
a typed "à", and nothing tells the two apart. The event says which key it was.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

STD_INPUT_HANDLE = -10
KEY_EVENT = 1
VK_ALT = 0x12
PROCESSED_INPUT = 0x0001  # switched off, so Ctrl+C arrives as a key
VIRTUAL_TERMINAL_INPUT = 0x0200  # switched off, so arrows arrive as keys and not escape sequences


class _KeyEvent(ctypes.Structure):
    _fields_ = [("down", wintypes.BOOL), ("repeat", wintypes.WORD), ("vk", wintypes.WORD),
                ("scan", wintypes.WORD), ("char", ctypes.c_wchar), ("modifiers", wintypes.DWORD)]


class _InputRecord(ctypes.Structure):
    # The real record is a union, but no event in it is larger than the key event.
    _fields_ = [("type", wintypes.WORD), ("key", _KeyEvent)]


class ConsoleKeys:
    def __init__(self) -> None:
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.GetStdHandle.restype = wintypes.HANDLE
        k.GetConsoleMode.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        k.SetConsoleMode.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k.ReadConsoleInputW.argtypes = [wintypes.HANDLE, ctypes.POINTER(_InputRecord), wintypes.DWORD,
                                        ctypes.POINTER(wintypes.DWORD)]
        self._kernel32 = k
        self._handle = k.GetStdHandle(STD_INPUT_HANDLE)
        self._mode = wintypes.DWORD()

    def open(self) -> None:
        if not self._kernel32.GetConsoleMode(self._handle, ctypes.byref(self._mode)):
            raise ctypes.WinError(ctypes.get_last_error())
        self._kernel32.SetConsoleMode(self._handle, self._mode.value & ~(PROCESSED_INPUT | VIRTUAL_TERMINAL_INPUT))

    def close(self) -> None:
        self._kernel32.SetConsoleMode(self._handle, self._mode.value)

    def next_key(self) -> tuple[int, str, int]:
        """Wait for a key press: its virtual key code, its character ("\\0" if none), its modifiers."""
        record, count = _InputRecord(), wintypes.DWORD()
        while True:
            if not self._kernel32.ReadConsoleInputW(self._handle, ctypes.byref(record), 1, ctypes.byref(count)):
                raise ctypes.WinError(ctypes.get_last_error())
            key = record.key
            # Typing a character code with Alt and the numpad delivers it when Alt comes up.
            if record.type == KEY_EVENT and (key.down or (key.vk == VK_ALT and key.char != "\0")):
                return key.vk, key.char, key.modifiers
