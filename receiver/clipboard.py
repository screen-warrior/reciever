"""Clipboard monitoring + history for the receiver.

A background thread polls the OS clipboard every N seconds. When the text
content changes, it is appended to an in-memory, append-only history (older
entries are never overwritten by newer ones). The sender polls
``/clipboard/history`` to pull new entries, show a notification, and keep its
own running history.

Cross-platform with no extra dependencies:
  * macOS   -> ``pbpaste`` (built in)
  * Windows -> Win32 clipboard via ctypes

Privacy note: this captures ALL copied text (which may include passwords). It is
an explicit feature; disable with ``KB_CLIPBOARD=0`` on the receiver.
"""

from __future__ import annotations

import sys
import threading
import time
from dataclasses import asdict, dataclass
from typing import List, Optional


@dataclass
class ClipEntry:
    id: int
    text: str
    ts: float


class ClipboardHistory:
    """Thread-safe, append-only clipboard history with monotonic ids."""

    def __init__(self, maxlen: int = 500) -> None:
        self._lock = threading.Lock()
        self._entries: List[ClipEntry] = []
        self._next_id = 1
        self._maxlen = maxlen

    def add(self, text: str) -> ClipEntry:
        with self._lock:
            entry = ClipEntry(id=self._next_id, text=text, ts=time.time())
            self._next_id += 1
            self._entries.append(entry)
            if len(self._entries) > self._maxlen:
                # Drop oldest, but ids keep increasing so the sender's "since"
                # cursor stays correct.
                self._entries = self._entries[-self._maxlen :]
            return entry

    def since(self, since_id: int) -> List[dict]:
        with self._lock:
            return [asdict(e) for e in self._entries if e.id > since_id]

    def last_id(self) -> int:
        with self._lock:
            return self._next_id - 1


CLIP_HISTORY = ClipboardHistory()


# ---------------------------------------------------------------------------
# OS clipboard readers
# ---------------------------------------------------------------------------
def _mac_read() -> Optional[str]:
    import subprocess

    try:
        out = subprocess.run(
            ["pbpaste"], capture_output=True, text=True, timeout=3
        )
        return out.stdout
    except Exception:
        return None


def _win_read() -> Optional[str]:
    import ctypes
    from ctypes import wintypes

    CF_UNICODETEXT = 13
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.IsClipboardFormatAvailable.argtypes = [wintypes.UINT]
    user32.IsClipboardFormatAvailable.restype = wintypes.BOOL
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.restype = wintypes.BOOL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

    if not user32.IsClipboardFormatAvailable(CF_UNICODETEXT):
        return None
    if not user32.OpenClipboard(None):
        return None
    try:
        handle = user32.GetClipboardData(CF_UNICODETEXT)
        if not handle:
            return None
        ptr = kernel32.GlobalLock(handle)
        if not ptr:
            return None
        try:
            return ctypes.c_wchar_p(ptr).value
        finally:
            kernel32.GlobalUnlock(handle)
    finally:
        user32.CloseClipboard()


def read_clipboard() -> Optional[str]:
    if sys.platform == "darwin":
        return _mac_read()
    if sys.platform.startswith("win"):
        return _win_read()
    return None


class ClipboardMonitor:
    def __init__(
        self, history: ClipboardHistory, interval: float = 3.0
    ) -> None:
        self._history = history
        self._interval = interval
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last: Optional[str] = None

    def start(self) -> None:
        # Seed with current clipboard so pre-existing content isn't reported as
        # a brand-new copy on startup.
        try:
            self._last = read_clipboard()
        except Exception:
            self._last = None
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                text = read_clipboard()
            except Exception:
                continue
            if text and text != self._last:
                self._last = text
                self._history.add(text)
