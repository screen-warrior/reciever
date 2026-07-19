"""Keystroke injector factory.

Selects the OS-specific backend at runtime and returns an injector exposing a
stable interface used by the typing engine:

    type_char(ch, dwell)   -- type one character (handles \\n, \\t)
    backspace(dwell)       -- delete one character

Platform-specific modules are imported lazily so importing this factory never
pulls in another OS's dependencies (e.g. Windows ``user32`` or macOS Quartz).
"""

from __future__ import annotations

import sys


def get_injector():
    if sys.platform == "darwin":
        from receiver.injector_mac import MacInjector

        return MacInjector()
    if sys.platform.startswith("win"):
        from receiver.injector_win import Win32Injector

        return Win32Injector()
    raise RuntimeError(f"unsupported platform for keystroke injection: {sys.platform}")
