"""Shared in-memory state for the receiver.

Holds the most recently received payload so the hotkey handler can type it out
on demand. Thread-safe because the HTTP server and hotkey listener run on
different threads.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ReceivedPayload:
    text: str
    received_at: float


class ReceiverState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._payload: Optional[ReceivedPayload] = None

    def set_text(self, text: str, received_at: float) -> None:
        with self._lock:
            self._payload = ReceivedPayload(text=text, received_at=received_at)

    def get(self) -> Optional[ReceivedPayload]:
        with self._lock:
            return self._payload


STATE = ReceiverState()
