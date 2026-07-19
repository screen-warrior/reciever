"""Shared typing controller.

Owns the single TypingEngine instance and the background typing thread, so that
*both* the local global hotkey and the remote HTTP trigger (from the sender app)
drive the same typing logic and can't run two typing passes at once.
"""

from __future__ import annotations

import threading
from typing import Optional, Tuple

from shared.config import DEFAULT_PROFILE
from receiver.state import STATE
from receiver.typing_engine import TypingEngine


class TypingController:
    def __init__(self) -> None:
        self._engine = TypingEngine(profile=DEFAULT_PROFILE)
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def is_typing(self) -> bool:
        t = self._thread
        return t is not None and t.is_alive()

    def start(
        self,
        text: Optional[str] = None,
        start_delay: float = 0.0,
        ide_mode: bool = False,
    ) -> Tuple[bool, str]:
        """Begin typing on a background thread.

        If ``text`` is None, the most recently received payload is used. Returns
        (ok, message). Refuses to start if a typing pass is already running.
        """
        with self._lock:
            if self.is_typing():
                return False, "already typing"
            if text is None:
                payload = STATE.get()
                if payload is None:
                    return False, "no payload received yet"
                text = payload.text
            self._thread = threading.Thread(
                target=self._engine.type_text,
                args=(text,),
                kwargs={"start_delay": start_delay, "ide_mode": ide_mode},
                daemon=True,
            )
            self._thread.start()
            mode = " (IDE mode)" if ide_mode else ""
            return True, f"typing {len(text)} chars{mode}"

    def abort(self) -> bool:
        if self.is_typing():
            self._engine.abort()
            return True
        return False


# Single shared instance used across the receiver process.
CONTROLLER = TypingController()
