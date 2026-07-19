"""HTTP listener for the receiver.

Exposes a tiny API the sender pushes code text to. The payload is stored in
shared state; the global hotkey (see hotkey.py) is what actually types it out.
Keeping receive and type separate means you send now and trigger later, with
the target window focused.
"""

from __future__ import annotations

import time

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

from shared.config import IDE_MODE_DEFAULT, REMOTE_START_DELAY, SHARED_TOKEN
from receiver.clipboard import CLIP_HISTORY
from receiver.controller import CONTROLLER
from receiver.state import STATE


app = FastAPI(title="Keyboard Receiver", version="0.1.0")


class SendPayload(BaseModel):
    text: str


class TypeRequest(BaseModel):
    # Optional override; if omitted, uses the configured remote delay.
    start_delay: float | None = None
    # Optional: send + type in one call by including text here.
    text: str | None = None
    # Optional: type into a smart auto-indenting editor (e.g. CodeSignal).
    ide_mode: bool | None = None


def _check_token(token: str | None) -> None:
    if token != SHARED_TOKEN:
        raise HTTPException(status_code=401, detail="invalid token")


@app.get("/health")
def health() -> dict:
    payload = STATE.get()
    return {
        "status": "ok",
        "has_payload": payload is not None,
        "chars": len(payload.text) if payload else 0,
    }


@app.post("/send")
def send(payload: SendPayload, x_token: str | None = Header(default=None)) -> dict:
    _check_token(x_token)
    STATE.set_text(payload.text, time.time())
    return {"status": "stored", "chars": len(payload.text)}


@app.get("/latest")
def latest(x_token: str | None = Header(default=None)) -> dict:
    """Return the text the receiver currently holds (token-protected).

    Lets the sender confirm exactly what will be typed next.
    """
    _check_token(x_token)
    payload = STATE.get()
    if payload is None:
        return {"has_payload": False, "text": "", "chars": 0, "received_at": None}
    return {
        "has_payload": True,
        "text": payload.text,
        "chars": len(payload.text),
        "received_at": payload.received_at,
    }


@app.post("/type")
def type_now(
    req: TypeRequest | None = None, x_token: str | None = Header(default=None)
) -> dict:
    """Start typing the stored text into the receiver's focused window.

    Triggered remotely by the sender app. A start delay gives you time to focus
    the target window on the receiver before the first keystroke lands.
    """
    _check_token(x_token)
    req = req or TypeRequest()

    # Allow send+type in a single call.
    if req.text is not None:
        STATE.set_text(req.text, time.time())

    delay = req.start_delay if req.start_delay is not None else REMOTE_START_DELAY
    ide_mode = req.ide_mode if req.ide_mode is not None else IDE_MODE_DEFAULT
    ok, message = CONTROLLER.start(start_delay=delay, ide_mode=ide_mode)
    if not ok:
        raise HTTPException(status_code=409, detail=message)
    return {"status": "typing", "detail": message, "start_delay": delay, "ide_mode": ide_mode}


@app.post("/abort")
def abort(x_token: str | None = Header(default=None)) -> dict:
    _check_token(x_token)
    aborted = CONTROLLER.abort()
    return {"status": "aborted" if aborted else "idle"}


@app.get("/clipboard/history")
def clipboard_history(
    since: int = 0, x_token: str | None = Header(default=None)
) -> dict:
    """Return clipboard entries newer than ``since`` (append-only history).

    The sender polls this to pull new copies made on the receiver, show a
    notification, and keep its own running history.
    """
    _check_token(x_token)
    entries = CLIP_HISTORY.since(since)
    return {"entries": entries, "last_id": CLIP_HISTORY.last_id()}
