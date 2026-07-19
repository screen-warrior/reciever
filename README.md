# Keyboard Project

Transfer code text from a **sender** machine to a **receiver** machine on the
same network, then have the receiver type it into the currently focused window
as **realistic, human-like keystrokes** (variable speed, pauses, and occasional
typos that get corrected) — triggered by a global hotkey.

The keystrokes are injected at the OS level (Win32 `SendInput` on Windows,
Quartz `CGEvent` on macOS), so in a browser they arrive as genuine
`KeyboardEvent`s (`isTrusted === true`) — not a clipboard paste. The realism
comes from the timing engine, not a fake event.

> Status: **sender = Windows** (PyQt6 GUI), **receiver = Windows or macOS**.
> For the MacBook receiver setup (background service, permissions, Tailscale),
> see **[MAC_SETUP.md](MAC_SETUP.md)**.

## Layout

```
shared/          config shared by both sides (network, hotkeys, timing profile)
receiver/
  injector.py       injector factory (picks OS backend)
  injector_win.py   Windows SendInput backend
  injector_mac.py   macOS Quartz CGEvent backend
  typing_engine.py  human-like timing / pauses / typos (OS-agnostic)
  controller.py     shared typing controller (hotkey + HTTP share one pass)
  server.py         FastAPI listener (/send /type /abort /latest /health /clipboard/history)
  clipboard.py      clipboard monitor + append-only history (cross-platform)
  hotkey.py         hotkey factory (picks OS backend)
  hotkey_win.py     Windows hotkeys (`keyboard`)
  hotkey_mac.py     macOS hotkeys (`pynput`)
  state.py          thread-safe shared payload
  main.py           receiver entry point (server + hotkeys), cross-platform
sender/
  client.py      posts text to the receiver (runtime-configurable endpoint)
  settings.py    persisted receiver address + token
  app.py         PyQt6 GUI: connection bar, Send / Type / Abort / View Received
type_demo.py     standalone typing-engine test (no networking)
deploy/          macOS LaunchAgent plist template
requirements.txt        Windows deps (sender + receiver)
requirements-mac.txt    macOS receiver deps
```

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> The `keyboard` library needs to register global hooks. If a hotkey isn't
> detected, run the terminal / receiver **as Administrator**.

## Try it

### 1. Test just the typing engine

```powershell
python type_demo.py
```

Focus Notepad or a Chrome textbox during the 5-second countdown and watch it
type. Press **ESC** to abort.

### 2. Full sender -> receiver loop (single PC)

Terminal A (receiver):

```powershell
python -m receiver.main
```

Terminal B (sender GUI):

```powershell
python -m sender.app
```

Paste code into the sender, click **Send**. Then focus your target window and
press the type hotkey (default **F9**). Press **ESC** to abort typing.

## Configuration

Set via environment variables (see `shared/config.py`):

| Variable            | Default            | Meaning                                  |
| ------------------- | ------------------ | ---------------------------------------- |
| `KB_BIND_HOST`      | `127.0.0.1`        | Receiver bind host (`0.0.0.0` for LAN)   |
| `KB_PORT`           | `8765`             | Receiver port                            |
| `KB_RECEIVER_HOST`  | `127.0.0.1`        | Where the sender sends (receiver LAN IP) |
| `KB_TOKEN`          | `change-me-local-token` | Shared secret for `/send`           |
| `KB_HOTKEY`         | `f9`               | Type-out hotkey                          |
| `KB_ABORT_HOTKEY`   | `esc`              | Abort hotkey                             |
| `KB_CLIPBOARD`      | `1`                | Receiver clipboard monitoring (`0` off)  |
| `KB_CLIPBOARD_INTERVAL` | `3.0`          | Clipboard poll interval (seconds)        |

Timing/typo behavior is tuned in `shared/config.py` (`TypingProfile`).

## Two-machine setup

The sender has a **connection bar** at the top: enter the receiver's host/IP,
port, and token, then click **Apply** (it's remembered across restarts in
`~/.keyboard_sender.json`). No code or env edits needed.

### Option A — same Wi-Fi (LAN)

1. On the **receiver**, start it listening on all interfaces:

```powershell
$env:KB_BIND_HOST="0.0.0.0"; .\.venv\Scripts\python.exe -m receiver.main
```

   It prints the address to point the sender at (its LAN IP + port).
2. Allow the port (8765) through the receiver's firewall.
3. In the **sender** connection bar, set the host to that LAN IP and Apply.

> Note: `127.0.0.1` / `localhost` only reaches the *same* machine. For two
> machines you must use the receiver's real IP, not localhost.
>
> Public/guest Wi-Fi often blocks device-to-device traffic ("client
> isolation"), so LAN may not work there — use Option B.

### Option B — over the internet via Tailscale (recommended)

Gives both machines a stable, **encrypted** private IP that works on any
network, without exposing anything publicly (important: this app injects
keystrokes, so it must never be on a public URL).

1. Install Tailscale on **both** machines and sign in to the same account:
   <https://tailscale.com/download>
2. On the **receiver**, start it on all interfaces (`KB_BIND_HOST=0.0.0.0`) and
   note its Tailscale IP (`100.x.y.z`, shown by `tailscale ip -4`).
3. In the **sender** connection bar, set the host to that Tailscale IP and Apply.
4. Set a strong shared token (`KB_TOKEN` on the receiver; matching value in the
   sender's Token field) — defense-in-depth even inside the tunnel.

The app still speaks plain HTTP; it simply rides inside Tailscale's encrypted
tunnel, so the code stays the same regardless of network.

> The **macOS receiver** is not built yet — the receiver currently runs on
> Windows only (Win32 `SendInput` + `keyboard`). Porting the receiver to the
> MacBook (Quartz keystroke injection + hotkeys + Accessibility permission) is a
> separate step; the networking above works today with a Windows receiver.

## Clipboard history (receiver -> sender)

The receiver monitors its own clipboard every 3s. Any newly copied text is added
to an **append-only history** (older items are never overwritten). The sender
polls every 3s, shows a **tray notification** ("Received new clipboard
information"), and keeps the full history.

- In the sender, click **Clipboard History** to open a live viewer (newest on
  top). The button shows an unread count when new items arrive while it's closed.
- Select any entry to see its full text; **Copy to my clipboard** copies it
  locally.
- Disable on the receiver with `KB_CLIPBOARD=0`. Note: this captures *all*
  copied text (which can include passwords) — enable only if you want that.

## Roadmap

- [ ] Tune the human-timing profile by trial.
- [ ] Package receiver + sender into background executables (PyInstaller `--noconsole`).
- [x] macOS receiver port (CGEvent injection + `pynput` hotkeys) — see
      [MAC_SETUP.md](MAC_SETUP.md).
- [ ] Optional: Interception-driver injector backend (defeats native OS-level
      injected-flag detection; not needed for web targets).
```
