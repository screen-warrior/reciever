"""Persisted sender settings (receiver address + token).

Stored as JSON in the user's home directory so the chosen receiver address
survives restarts and works the same whether run from source or a packaged
executable. This is what lets you point the sender at a LAN IP or a Tailscale IP
without editing code or environment variables.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from shared.config import RECEIVER_HOST, RECEIVER_PORT, SHARED_TOKEN

SETTINGS_PATH = Path.home() / ".keyboard_sender.json"


def defaults() -> Dict[str, Any]:
    return {
        "host": RECEIVER_HOST,
        "port": RECEIVER_PORT,
        "token": SHARED_TOKEN,
        "ide_mode": False,
    }


def load() -> Dict[str, Any]:
    data = defaults()
    try:
        if SETTINGS_PATH.exists():
            saved = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                data.update(
                    {
                        k: saved[k]
                        for k in ("host", "port", "token", "ide_mode")
                        if k in saved
                    }
                )
    except Exception:
        # Corrupt/unreadable settings should never block startup.
        pass
    data["port"] = int(data["port"])
    data["ide_mode"] = bool(data["ide_mode"])
    return data


def save(host: str, port: int, token: str, ide_mode: bool = False) -> None:
    try:
        SETTINGS_PATH.write_text(
            json.dumps(
                {
                    "host": host,
                    "port": int(port),
                    "token": token,
                    "ide_mode": bool(ide_mode),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass
