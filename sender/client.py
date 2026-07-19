"""Sender-side network client: pushes code text to the receiver.

The target endpoint (host/port) and auth token are held in runtime-mutable
state so the GUI can repoint the sender at a different receiver (LAN IP,
Tailscale IP, etc.) without restarting or editing config.
"""

from __future__ import annotations

import requests

from shared.config import RECEIVER_HOST, RECEIVER_PORT, SHARED_TOKEN


_state = {"host": RECEIVER_HOST, "port": RECEIVER_PORT, "token": SHARED_TOKEN}


def set_endpoint(host: str, port: int, token: str | None = None) -> None:
    _state["host"] = host.strip()
    _state["port"] = int(port)
    if token is not None:
        _state["token"] = token


def get_endpoint() -> dict:
    return dict(_state)


def base_url() -> str:
    return f"http://{_state['host']}:{_state['port']}"


def _headers() -> dict:
    return {"x-token": _state["token"]}


def send_text(text: str, timeout: float = 5.0) -> dict:
    resp = requests.post(
        f"{base_url()}/send",
        json={"text": text},
        headers=_headers(),
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def trigger_type(
    text: str | None = None, start_delay: float | None = None, timeout: float = 5.0
) -> dict:
    """Ask the receiver to start typing. If ``text`` is given, it is stored and
    typed in one call (send + type); otherwise the last sent text is used."""
    body: dict = {}
    if text is not None:
        body["text"] = text
    if start_delay is not None:
        body["start_delay"] = start_delay
    resp = requests.post(
        f"{base_url()}/type",
        json=body,
        headers=_headers(),
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def abort_type(timeout: float = 5.0) -> dict:
    resp = requests.post(
        f"{base_url()}/abort",
        headers=_headers(),
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def get_latest(timeout: float = 5.0) -> dict:
    """Fetch the text the receiver currently holds (what it would type next)."""
    resp = requests.get(
        f"{base_url()}/latest",
        headers=_headers(),
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def get_clipboard_history(since: int = 0, timeout: float = 5.0) -> dict:
    """Pull clipboard entries newer than ``since`` from the receiver."""
    resp = requests.get(
        f"{base_url()}/clipboard/history",
        params={"since": since},
        headers=_headers(),
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def check_health(timeout: float = 3.0) -> dict:
    resp = requests.get(f"{base_url()}/health", timeout=timeout)
    resp.raise_for_status()
    return resp.json()
