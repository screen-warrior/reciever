"""macOS global hotkey backend (``pynput``).

Registers the type + abort hotkeys via a background ``GlobalHotKeys`` listener,
both delegating to the shared TypingController.

Requires **Accessibility** and **Input Monitoring** permission for the running
process (System Settings -> Privacy & Security). Import only on macOS.

Note on function keys: if macOS is set to use F1/F2/... as media keys (the
default), a bare ``F9`` press sends a media key rather than the function key. In
that case either enable "Use F1, F2, etc. keys as standard function keys" in
Keyboard settings, press fn+F9, or set a different hotkey via ``KB_HOTKEY``.
"""

from __future__ import annotations

from pynput import keyboard as pk

from shared.config import ABORT_HOTKEY, LOCAL_HOTKEY_START_DELAY, TYPE_HOTKEY
from receiver.controller import CONTROLLER


_MODIFIERS = {
    "ctrl": "<ctrl>",
    "control": "<ctrl>",
    "alt": "<alt>",
    "option": "<alt>",
    "opt": "<alt>",
    "cmd": "<cmd>",
    "command": "<cmd>",
    "win": "<cmd>",
    "super": "<cmd>",
    "shift": "<shift>",
}

_SPECIALS = {
    "esc": "<esc>",
    "escape": "<esc>",
    "enter": "<enter>",
    "return": "<enter>",
    "tab": "<tab>",
    "space": "<space>",
    "backspace": "<backspace>",
    "delete": "<delete>",
}


def to_pynput_hotkey(hotkey: str) -> str:
    """Translate a simple hotkey string (e.g. 'ctrl+alt+v', 'f9', 'esc') into
    the pynput GlobalHotKeys format (e.g. '<ctrl>+<alt>+v', '<f9>', '<esc>')."""
    parts = [p.strip().lower() for p in hotkey.split("+") if p.strip()]
    out = []
    for p in parts:
        if p in _MODIFIERS:
            out.append(_MODIFIERS[p])
        elif p in _SPECIALS:
            out.append(_SPECIALS[p])
        elif len(p) > 1 and p[0] == "f" and p[1:].isdigit():
            out.append(f"<{p}>")  # function keys: f1..f20
        else:
            out.append(p)
    return "+".join(out)


class MacHotkeyController:
    def __init__(self) -> None:
        self._listener: pk.GlobalHotKeys | None = None

    def _on_type(self) -> None:
        ok, msg = CONTROLLER.start(start_delay=LOCAL_HOTKEY_START_DELAY)
        print(f"[hotkey] {msg}")

    def _on_abort(self) -> None:
        if CONTROLLER.abort():
            print("[hotkey] abort requested")

    def register(self) -> None:
        type_hk = to_pynput_hotkey(TYPE_HOTKEY)
        abort_hk = to_pynput_hotkey(ABORT_HOTKEY)
        self._listener = pk.GlobalHotKeys(
            {type_hk: self._on_type, abort_hk: self._on_abort}
        )
        self._listener.start()
        print(f"[hotkey] type='{TYPE_HOTKEY}' ({type_hk})  abort='{ABORT_HOTKEY}' ({abort_hk})")
