"""Shared configuration for sender and receiver.

For the initial single-PC test everything runs on localhost. When moving to
two machines (Windows sender -> MacBook receiver) on the same LAN, change
RECEIVER_HOST on the sender side to the receiver's LAN IP address, and have the
receiver bind to 0.0.0.0 so it accepts connections from the network.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


# --------------------------------------------------------------------------
# Network
# --------------------------------------------------------------------------
# Receiver listens here. Bind host 0.0.0.0 to accept LAN connections later.
RECEIVER_BIND_HOST = os.environ.get("KB_BIND_HOST", "127.0.0.1")
RECEIVER_PORT = int(os.environ.get("KB_PORT", "8765"))

# Where the sender sends to. For single-PC testing this is localhost. For the
# two-machine setup, set KB_RECEIVER_HOST to the receiver's LAN IP.
RECEIVER_HOST = os.environ.get("KB_RECEIVER_HOST", "127.0.0.1")

# Optional shared secret so random devices on the LAN can't push text.
SHARED_TOKEN = os.environ.get("KB_TOKEN", "change-me-local-token")


# --------------------------------------------------------------------------
# Clipboard monitoring (receiver captures copies; sender polls the history)
# --------------------------------------------------------------------------
CLIPBOARD_MONITOR_ENABLED = os.environ.get("KB_CLIPBOARD", "1") not in (
    "0",
    "false",
    "False",
    "no",
)
CLIPBOARD_INTERVAL = float(os.environ.get("KB_CLIPBOARD_INTERVAL", "3.0"))


def receiver_url() -> str:
    return f"http://{RECEIVER_HOST}:{RECEIVER_PORT}"


# --------------------------------------------------------------------------
# Hotkey (receiver)
# --------------------------------------------------------------------------
# The global hotkey that starts typing out the last received text.
# Format follows the `keyboard` library (e.g. "ctrl+alt+v").
TYPE_HOTKEY = os.environ.get("KB_HOTKEY", "f9")

# A panic hotkey to immediately abort an in-progress typing run.
ABORT_HOTKEY = os.environ.get("KB_ABORT_HOTKEY", "esc")

# Lead time before typing starts when triggered by the LOCAL hotkey. Just long
# enough to release the key chord so it doesn't contaminate the output.
LOCAL_HOTKEY_START_DELAY = float(os.environ.get("KB_LOCAL_DELAY", "0.6"))

# Lead time before typing starts when triggered REMOTELY from the sender app.
# Longer, because after clicking "Type" you need a moment to click into the
# target window on the receiver machine before typing begins.
REMOTE_START_DELAY = float(os.environ.get("KB_REMOTE_DELAY", "3.0"))


# --------------------------------------------------------------------------
# Human typing behavior
# --------------------------------------------------------------------------
@dataclass
class TypingProfile:
    """Tunable parameters that shape how 'human' the typing feels.

    All times are in seconds unless noted. These are starting points; we will
    tune them by trial-and-error while watching live typing.
    """

    # Typing speed. Instead of a fixed rate, the effective WPM smoothly drifts
    # up and down between these bounds over time, so the pace ebbs and flows
    # like a real typist rather than being metronome-steady.
    wpm_min: float = 50.0
    wpm_max: float = 65.0
    # How fast the speed oscillates: phase advance per character (radians).
    # Smaller = slower, longer waves; larger = quicker speed changes.
    wpm_drift_rate: float = 0.05
    # Small random nudge added to the drift each char so waves aren't perfectly
    # regular.
    wpm_drift_noise: float = 0.015

    # Assumed average characters per word (incl. following space) for WPM math.
    chars_per_word: float = 5.0

    # Per-key delay jitter: actual delay = base * lognormal-ish spread.
    # Lower = more robotic, higher = more erratic.
    delay_jitter: float = 0.35

    # How long a key is physically held down (keydown -> keyup).
    dwell_min: float = 0.03
    dwell_max: float = 0.09

    # Extra pauses (added on top of the normal inter-key delay).
    pause_after_punctuation: float = 0.18   # after . , ; : ! ?
    pause_after_newline: float = 0.28        # after pressing Enter
    pause_after_word_prob: float = 0.06      # chance of a brief think-pause
    pause_after_word_min: float = 0.25
    pause_after_word_max: float = 0.9

    # Occasional longer "thinking" pause anywhere.
    think_pause_prob: float = 0.015
    think_pause_min: float = 0.8
    think_pause_max: float = 2.5

    # Indentation: convert leading-space indentation into real Tab key
    # presses where a full indent level fits. Makes indentation look like a
    # human hitting Tab rather than tapping space many times. Any remainder
    # (partial indent) is still typed as spaces.
    convert_indent_to_tabs: bool = True
    tab_width: int = 4

    # Typos: probability per character of fat-fingering an adjacent key,
    # then noticing and correcting it with backspace.
    typo_prob: float = 0.02
    # After making a typo, how long before noticing/correcting.
    typo_notice_min: float = 0.12
    typo_notice_max: float = 0.5
    # Sometimes type a couple extra wrong chars before catching it.
    typo_burst_max: int = 2

    def delay_for_wpm(self, wpm: float) -> float:
        """Base inter-key delay (seconds) for a given words-per-minute."""
        cps = (wpm * self.chars_per_word) / 60.0
        return 1.0 / max(cps, 0.1)

    def wpm_mid(self) -> float:
        return (self.wpm_min + self.wpm_max) / 2.0

    def wpm_amplitude(self) -> float:
        return (self.wpm_max - self.wpm_min) / 2.0


DEFAULT_PROFILE = TypingProfile()


# --------------------------------------------------------------------------
# IDE mode (for smart editors like CodeSignal that auto-indent)
# --------------------------------------------------------------------------
# When typing into an editor that auto-indents, our own indentation would stack
# on top of the editor's. IDE mode resets each new line to column 0 and types
# the exact indentation itself. Default for the LOCAL hotkey; the sender can
# override per request via its "IDE mode" checkbox.
IDE_MODE_DEFAULT = os.environ.get("KB_IDE_MODE", "0") not in ("0", "false", "False", "no")

# In IDE mode, press Esc right before each Enter to dismiss any autocomplete
# popup so Enter always inserts a newline instead of accepting a suggestion.
IDE_ESC_BEFORE_ENTER = os.environ.get("KB_IDE_ESC", "1") not in ("0", "false", "False", "no")
