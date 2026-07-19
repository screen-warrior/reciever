"""Windows keystroke injection backend (Win32 ``SendInput``).

Delivers *real* key events through the normal input pipeline. In a browser
these produce ``KeyboardEvent`` objects with ``isTrusted === true`` and correct
``key`` / ``code`` values -- indistinguishable to page JavaScript from a
physical keyboard.

Selected by ``receiver.injector.get_injector()`` on Windows. This module must
only be imported on Windows (it loads user32 at import time).
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes


user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
KEYEVENTF_SCANCODE = 0x0008

MAPVK_VK_TO_VSC = 0

# Virtual key codes we care about.
VK_BACK = 0x08
VK_TAB = 0x09
VK_RETURN = 0x0D
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12  # Alt

ULONG_PTR = ctypes.POINTER(ctypes.c_ulong)


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUTunion(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUTunion)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT

user32.VkKeyScanW.argtypes = (wintypes.WCHAR,)
user32.VkKeyScanW.restype = wintypes.SHORT

user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
user32.MapVirtualKeyW.restype = wintypes.UINT


def _send(inp: INPUT) -> None:
    n = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    if n != 1:
        raise ctypes.WinError(ctypes.get_last_error())


def _scan_for_vk(vk: int) -> int:
    return user32.MapVirtualKeyW(vk, MAPVK_VK_TO_VSC)


class Win32Injector:
    """Concrete injector backed by SendInput.

    Public interface (kept stable across backends):
      - type_char(ch, dwell)   -> handles shift + unicode fallback
      - backspace(dwell)
    """

    backend_name = "win32-sendinput"

    def key_down(self, vk: int) -> None:
        scan = _scan_for_vk(vk)
        ki = KEYBDINPUT(wVk=vk, wScan=scan, dwFlags=0, time=0, dwExtraInfo=None)
        _send(INPUT(type=INPUT_KEYBOARD, union=_INPUTunion(ki=ki)))

    def key_up(self, vk: int) -> None:
        scan = _scan_for_vk(vk)
        ki = KEYBDINPUT(
            wVk=vk, wScan=scan, dwFlags=KEYEVENTF_KEYUP, time=0, dwExtraInfo=None
        )
        _send(INPUT(type=INPUT_KEYBOARD, union=_INPUTunion(ki=ki)))

    def _unicode_down_up(self, ch: str, dwell: float) -> None:
        code = ord(ch)
        down = KEYBDINPUT(
            wVk=0, wScan=code, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=None
        )
        up = KEYBDINPUT(
            wVk=0,
            wScan=code,
            dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP,
            time=0,
            dwExtraInfo=None,
        )
        _send(INPUT(type=INPUT_KEYBOARD, union=_INPUTunion(ki=down)))
        if dwell > 0:
            time.sleep(dwell)
        _send(INPUT(type=INPUT_KEYBOARD, union=_INPUTunion(ki=up)))

    def tap(self, vk: int, dwell: float = 0.0) -> None:
        self.key_down(vk)
        if dwell > 0:
            time.sleep(dwell)
        self.key_up(vk)

    def type_char(self, ch: str, dwell: float = 0.0) -> None:
        """Type a single character with correct shift handling.

        Uses VkKeyScanW to find the virtual key + shift state for the char.
        Falls back to Unicode injection for anything not on the layout.
        """
        if ch == "\n" or ch == "\r":
            self.tap(VK_RETURN, dwell)
            return
        if ch == "\t":
            self.tap(VK_TAB, dwell)
            return

        res = user32.VkKeyScanW(ch)
        if res == -1:
            self._unicode_down_up(ch, dwell)
            return

        vk = res & 0xFF
        shift_state = (res >> 8) & 0xFF
        need_shift = bool(shift_state & 1)
        need_ctrl = bool(shift_state & 2)
        need_alt = bool(shift_state & 4)

        if need_ctrl or need_alt:
            self._unicode_down_up(ch, dwell)
            return

        if need_shift:
            self.key_down(VK_SHIFT)
        self.key_down(vk)
        if dwell > 0:
            time.sleep(dwell)
        self.key_up(vk)
        if need_shift:
            self.key_up(VK_SHIFT)

    def backspace(self, dwell: float = 0.0) -> None:
        self.tap(VK_BACK, dwell)
