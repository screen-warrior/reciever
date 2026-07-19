"""macOS keystroke injection backend (Quartz ``CGEvent``).

Posts key events at the HID level (``kCGHIDEventTap``), so the OS and
applications see them arriving through the normal input path -- as close to a
real hardware keyboard as software injection gets on macOS. In a browser these
produce ``KeyboardEvent`` objects with ``isTrusted === true``.

Arbitrary characters (letters, symbols, unicode) are typed by attaching a
unicode string to a key event, which is layout-independent and needs no
per-character keycode mapping. Special keys (Return, Tab, Delete) use their
macOS virtual keycodes so editors and text fields behave correctly.

Requires the running process to have **Accessibility** permission
(System Settings -> Privacy & Security -> Accessibility). Selected by
``receiver.injector.get_injector()`` on macOS; import only on macOS.
"""

from __future__ import annotations

import time

import Quartz  # provided by pyobjc-framework-Quartz


# macOS virtual keycodes (from HIToolbox Events.h).
kVK_Return = 0x24
kVK_Tab = 0x30
kVK_Delete = 0x33  # Backspace


class MacInjector:
    backend_name = "mac-cgevent"

    def _post_keycode(self, keycode: int, down: bool) -> None:
        ev = Quartz.CGEventCreateKeyboardEvent(None, keycode, down)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, ev)

    def _tap_keycode(self, keycode: int, dwell: float) -> None:
        self._post_keycode(keycode, True)
        if dwell > 0:
            time.sleep(dwell)
        self._post_keycode(keycode, False)

    def _type_unicode(self, ch: str, dwell: float) -> None:
        down = Quartz.CGEventCreateKeyboardEvent(None, 0, True)
        Quartz.CGEventKeyboardSetUnicodeString(down, len(ch), ch)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
        if dwell > 0:
            time.sleep(dwell)
        up = Quartz.CGEventCreateKeyboardEvent(None, 0, False)
        Quartz.CGEventKeyboardSetUnicodeString(up, len(ch), ch)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)

    def type_char(self, ch: str, dwell: float = 0.0) -> None:
        if ch == "\n" or ch == "\r":
            self._tap_keycode(kVK_Return, dwell)
            return
        if ch == "\t":
            self._tap_keycode(kVK_Tab, dwell)
            return
        self._type_unicode(ch, dwell)

    def backspace(self, dwell: float = 0.0) -> None:
        self._tap_keycode(kVK_Delete, dwell)
