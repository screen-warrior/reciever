"""Windows global hotkey backend (``keyboard`` library).

Registers the type + abort hotkeys, both delegating to the shared
TypingController. Import only on Windows.
"""

from __future__ import annotations

import keyboard

from shared.config import ABORT_HOTKEY, LOCAL_HOTKEY_START_DELAY, TYPE_HOTKEY
from receiver.controller import CONTROLLER


class WinHotkeyController:
    def on_type_hotkey(self) -> None:
        ok, msg = CONTROLLER.start(start_delay=LOCAL_HOTKEY_START_DELAY)
        print(f"[hotkey] {msg}")

    def on_abort_hotkey(self) -> None:
        if CONTROLLER.abort():
            print("[hotkey] abort requested")

    def register(self) -> None:
        keyboard.add_hotkey(TYPE_HOTKEY, self.on_type_hotkey)
        keyboard.add_hotkey(ABORT_HOTKEY, self.on_abort_hotkey)
        print(f"[hotkey] type='{TYPE_HOTKEY}'  abort='{ABORT_HOTKEY}'")
