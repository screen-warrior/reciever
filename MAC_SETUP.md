# MacBook Receiver — Setup Guide

This is the **receiver** side, running on the MacBook. It listens for code sent
from the Windows sender and, on a hotkey (or a remote trigger from the sender),
types it into whatever window is focused — as human-like keystrokes.

It runs as a **background task** via a macOS LaunchAgent (starts at login, no
window). These steps take you from a fresh GitHub clone to a running background
service.

---

## 0. Prerequisites

- **macOS** (Apple Silicon or Intel).
- **Python 3.10+**. Check with `python3 --version`. If missing, install from
  <https://www.python.org/downloads/macos/> or via Homebrew: `brew install python`.
- **Git** (`git --version`; Xcode Command Line Tools provide it, or `brew install git`).
- **Tailscale** (recommended, for connecting to the Windows sender over the
  internet): install on the Mac AND the Windows PC, signed into the same
  account — <https://tailscale.com/download>.

---

## 1. Clone the project from GitHub

```bash
cd ~
git clone https://github.com/<your-username>/<your-repo>.git keyboard_project
cd keyboard_project
```

(Use the actual URL of the repo you pushed.)

## 2. Create a virtual environment and install receiver deps

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements-mac.txt
```

> Use `requirements-mac.txt` (not `requirements.txt`). The Mac only runs the
> receiver, so it needs FastAPI/uvicorn, `pynput`, and `pyobjc-framework-Quartz`
> — not the Windows-only bits.

## 3. First run in Terminal (to grant permissions)

Run it once in the foreground so macOS shows the permission prompts:

```bash
python -m receiver.main
```

macOS will (eventually) require two permissions for the app that runs Python —
i.e. **Terminal** (or iTerm) during this test:

1. **Accessibility** — needed to *inject* keystrokes.
   System Settings → Privacy & Security → **Accessibility** → enable your
   terminal app.
2. **Input Monitoring** — needed to *detect* the global hotkey (F9/Esc).
   System Settings → Privacy & Security → **Input Monitoring** → enable your
   terminal app.

Grant both, then quit (`Ctrl+C`) and run `python -m receiver.main` again.

You should see:

```
[receiver] listening on 0.0.0.0:8765
[receiver] point the sender at:  <your-LAN-IP>:8765
[hotkey] type='f9' (<f9>)  abort='esc' (<esc>)
[receiver] ready. ...
```

### Quick local typing test

Open **TextEdit**, click into a document, then press **F9**. If nothing was
sent yet it will say "no payload"; that's fine — it confirms the hotkey works.

> Function-key note: if F9 does nothing, macOS is likely using F-keys as media
> keys. Either enable *System Settings → Keyboard → "Use F1, F2, etc. as
> standard function keys"*, press **fn+F9**, or pick another hotkey (see §6).

## 4. Find the Mac's address (for the sender)

- **Tailscale (recommended):**
  ```bash
  tailscale ip -4
  ```
  Gives a `100.x.y.z` address that works from anywhere, encrypted.
- **Same Wi-Fi (LAN):** System Settings → Wi-Fi → Details → IP Address
  (e.g. `192.168.1.42`), or `ipconfig getifaddr en0`.

On the **Windows sender**, put that address in the connection bar (host), keep
port `8765`, set the same **token** on both sides, and click **Apply**.

## 5. Run as a background task (LaunchAgent)

1. Edit the template `deploy/com.keyboardproject.receiver.plist`:
   - Replace both `__ABSOLUTE_PATH__` with your real path. Get it with `pwd`
     (e.g. `/Users/you`), so the python path becomes
     `/Users/you/keyboard_project/.venv/bin/python`.
   - Set `KB_TOKEN` to a strong shared secret (match it on the sender).
2. Install and start it:

```bash
cp deploy/com.keyboardproject.receiver.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.keyboardproject.receiver.plist
```

3. Verify it's running:

```bash
launchctl list | grep keyboardproject
cat /tmp/keyboard_receiver.log
```

> **Important permissions note for background mode:** the process now runs under
> `/Users/you/keyboard_project/.venv/bin/python`, not Terminal. macOS ties
> Accessibility / Input Monitoring to that exact binary. If typing or the hotkey
> don't work in background mode, add that **python** binary to Accessibility and
> Input Monitoring (drag it in via the "+" using `Cmd+Shift+G` to type the
> path), then reload (see §7). Keeping the Terminal grant from §3 usually covers
> the interactive test; background mode may need the python binary granted too.

## 6. Confirm end-to-end

1. On Windows: paste code → **Type on Receiver** (or **Send**, then F9 on Mac).
2. On the Mac: focus TextEdit / VS Code / Chrome within the countdown.
3. Watch it type. Press **Esc** (or the sender's **Abort**) to stop.

## 7. Managing the background service

```bash
# Stop / unload
launchctl unload ~/Library/LaunchAgents/com.keyboardproject.receiver.plist

# Start / load
launchctl load ~/Library/LaunchAgents/com.keyboardproject.receiver.plist

# After editing the plist, unload then load again.
# Logs:
tail -f /tmp/keyboard_receiver.log /tmp/keyboard_receiver.err
```

### Change the hotkey
Edit the `KB_HOTKEY` value in the plist (e.g. `f8`, `cmd+shift+space`), then
unload + load. Supported format examples: `f9`, `esc`, `cmd+shift+v`,
`ctrl+alt+v`.

---

## Troubleshooting

- **Typing does nothing / permission error** → Accessibility not granted to the
  binary that's running (Terminal for §3, the venv `python` for §5).
- **Hotkey never fires** → Input Monitoring not granted, or F-key is acting as a
  media key (see §3 note).
- **Sender can't connect** → confirm the Mac shows `listening on 0.0.0.0:8765`,
  the sender points at the right IP/token, and (LAN) the Mac firewall allows the
  port. On public Wi-Fi, use Tailscale instead.
- **Wrong window gets typed into** → focus the intended window during the
  countdown; press Esc to abort.
