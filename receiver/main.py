"""Receiver entry point.

Starts the HTTP listener (background thread) and registers the global hotkeys,
then blocks forever. Packaged with PyInstaller (--noconsole) this runs as a
silent background process.

Run in dev:
    python -m receiver.main
"""

from __future__ import annotations

import socket
import threading

import uvicorn

from shared.config import (
    CLIPBOARD_INTERVAL,
    CLIPBOARD_MONITOR_ENABLED,
    RECEIVER_BIND_HOST,
    RECEIVER_PORT,
)
from receiver.clipboard import CLIP_HISTORY, ClipboardMonitor
from receiver.hotkey import make_hotkey_controller
from receiver.server import app


def _serve() -> None:
    uvicorn.run(app, host=RECEIVER_BIND_HOST, port=RECEIVER_PORT, log_level="warning")


def _local_ip() -> str:
    """Best-effort primary LAN IP (the address a sender would point at)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "unknown"
    finally:
        s.close()


def main() -> None:
    server_thread = threading.Thread(target=_serve, daemon=True)
    server_thread.start()

    print(f"[receiver] listening on {RECEIVER_BIND_HOST}:{RECEIVER_PORT}")
    if RECEIVER_BIND_HOST in ("127.0.0.1", "localhost"):
        print("[receiver] bound to localhost only -> reachable from THIS machine.")
        print("[receiver] for another machine, restart with KB_BIND_HOST=0.0.0.0")
    else:
        print(f"[receiver] point the sender at:  {_local_ip()}:{RECEIVER_PORT}")
        print(f"[receiver] (or this machine's Tailscale IP):  <tailscale-ip>:{RECEIVER_PORT}")

    controller = make_hotkey_controller()
    controller.register()

    if CLIPBOARD_MONITOR_ENABLED:
        monitor = ClipboardMonitor(CLIP_HISTORY, CLIPBOARD_INTERVAL)
        monitor.start()
        print(f"[clipboard] monitoring every {CLIPBOARD_INTERVAL:g}s (KB_CLIPBOARD=0 to disable)")

    print("[receiver] ready. Send code from the sender, focus a window, trigger typing.")
    # Block the main thread forever; the hotkey backend runs its own listener
    # thread and the HTTP server runs on the server thread above.
    threading.Event().wait()


if __name__ == "__main__":
    main()
