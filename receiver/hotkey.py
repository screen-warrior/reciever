"""Global hotkey factory.

Returns an OS-specific hotkey controller exposing ``register()``. Both backends
delegate to the shared TypingController, so the local hotkey and the remote
trigger from the sender app share one typing pass.

Platform-specific modules are imported lazily so this factory never pulls in
another OS's dependencies.
"""

from __future__ import annotations

import sys


def make_hotkey_controller():
    if sys.platform == "darwin":
        from receiver.hotkey_mac import MacHotkeyController

        return MacHotkeyController()
    if sys.platform.startswith("win"):
        from receiver.hotkey_win import WinHotkeyController

        return WinHotkeyController()
    raise RuntimeError(f"unsupported platform for hotkeys: {sys.platform}")
